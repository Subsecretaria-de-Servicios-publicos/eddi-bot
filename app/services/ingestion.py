import hashlib

import httpx
from sqlalchemy.orm import Session

from ..models import Document, DocumentChunk, DocumentImage, DocumentStatus
from .normalizer import slugify, normalize_text
from .chunker import chunk_text
from .embedder import embed_document
from .extractor import extract_text_from_url, extract_text_from_pdf_bytes
from .pdf_image_extractor import extract_visual_pages_from_pdf_bytes, delete_visual_assets_for_document


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def find_existing_document(
    db: Session,
    *,
    url: str | None = None,
    content_hash: str | None = None,
) -> Document | None:
    if url:
        doc = db.query(Document).filter(Document.url == url).first()
        if doc:
            return doc

    if content_hash:
        doc = db.query(Document).filter(Document.content_hash == content_hash).first()
        if doc:
            return doc

    return None


def _download_bytes(url: str, timeout: int = 30) -> bytes:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content


def create_document_record(
    db: Session,
    *,
    title: str,
    text: str,
    url: str | None = None,
    source_id: int | None = None,
    document_type: str | None = None,
    organism: str | None = None,
    topic: str | None = None,
    summary: str | None = None,
    publish: bool = True,
    metadata_json: dict | None = None,
) -> Document:
    cleaned = normalize_text(text)
    digest = sha256_text(cleaned)

    existing = find_existing_document(db, url=url, content_hash=digest)
    if existing:
        existing.title = title.strip()
        existing.slug = slugify(title)
        existing.url = (url or "").strip() or None
        existing.source_id = source_id
        existing.document_type = (document_type or "").strip() or None
        existing.organism = (organism or "").strip() or None
        existing.topic = (topic or "").strip() or None
        existing.summary = (summary or "").strip() or None
        existing.content_text = cleaned
        existing.content_hash = digest
        existing.status = DocumentStatus.READY.value
        existing.is_published = publish
        existing.metadata_json = metadata_json or {}
        db.flush()
        return existing

    doc = Document(
        source_id=source_id,
        title=title.strip(),
        slug=slugify(title),
        url=(url or "").strip() or None,
        document_type=(document_type or "").strip() or None,
        organism=(organism or "").strip() or None,
        topic=(topic or "").strip() or None,
        summary=(summary or "").strip() or None,
        content_text=cleaned,
        content_hash=digest,
        status=DocumentStatus.READY.value,
        is_published=publish,
        metadata_json=metadata_json or {},
    )
    db.add(doc)
    db.flush()
    return doc


def clear_document_chunks(db: Session, doc_id: int):
    db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
    db.flush()


def clear_document_images(db: Session, doc_id: int):
    db.query(DocumentImage).filter(DocumentImage.document_id == doc_id).delete()
    db.flush()
    delete_visual_assets_for_document(doc_id)


def create_chunks_for_document(
    db: Session,
    doc: Document,
    text: str,
    with_embeddings: bool = True,
) -> int:
    chunks = chunk_text(text)
    total = 0

    for ch in chunks:
        chunk_text_value = ch["chunk_text"]
        emb = embed_document(chunk_text_value) if with_embeddings else None

        row = DocumentChunk(
            document_id=doc.id,
            chunk_index=ch["chunk_index"],
            heading=ch["heading"],
            chunk_text=chunk_text_value,
            char_count=ch["char_count"],
            token_count=None,
            embedding=emb,
            metadata_json={},
        )
        db.add(row)
        total += 1

    return total


def create_visual_rows_for_document(
    db: Session,
    *,
    doc: Document,
    pdf_bytes: bytes,
    ocr_lang: str = "spa",
) -> int:
    items = extract_visual_pages_from_pdf_bytes(data=pdf_bytes, doc_id=doc.id, ocr_lang=ocr_lang)
    total = 0

    for item in items:
        ocr_text = normalize_text(item.get("ocr_text") or "")
        #emb = embed_document(ocr_text) if len(ocr_text) >= 30 else None
        emb = None

        row = DocumentImage(
            document_id=doc.id,
            page_number=item["page_number"],
            image_index=item["image_index"],
            image_path=item["image_path"],
            ocr_text=ocr_text or None,
            caption=item.get("caption"),
            char_count=item.get("char_count"),
            score_boost=1.05,
            metadata_json=item.get("metadata_json") or {},
            embedding=emb,
        )
        db.add(row)
        total += 1

    meta = dict(doc.metadata_json or {})
    meta["visual_pages_count"] = total
    meta["visual_ocr_items"] = total
    meta["visual_ocr_ready"] = True
    meta["visual_ocr_error"] = None
    doc.metadata_json = meta
    db.flush()
    return total


def ingest_document_text(
    db: Session,
    *,
    title: str,
    text: str,
    url: str | None = None,
    source_id: int | None = None,
    document_type: str | None = None,
    organism: str | None = None,
    topic: str | None = None,
    summary: str | None = None,
    publish: bool = True,
    metadata_json: dict | None = None,
):
    cleaned = normalize_text(text)

    doc = create_document_record(
        db,
        title=title,
        text=cleaned,
        url=url,
        source_id=source_id,
        document_type=document_type,
        organism=organism,
        topic=topic,
        summary=summary,
        publish=publish,
        metadata_json=metadata_json,
    )

    clear_document_chunks(db, doc.id)
    create_chunks_for_document(db, doc, cleaned, with_embeddings=True)

    db.commit()
    db.refresh(doc)
    return doc


def update_document_text(
    db: Session,
    *,
    doc: Document,
    title: str,
    text: str,
    url: str | None = None,
    document_type: str | None = None,
    organism: str | None = None,
    topic: str | None = None,
    summary: str | None = None,
    publish: bool = True,
    metadata_json: dict | None = None,
):
    cleaned = normalize_text(text)
    digest = sha256_text(cleaned)

    doc.title = title.strip()
    doc.slug = slugify(title)
    doc.url = (url or "").strip() or None
    doc.document_type = (document_type or "").strip() or None
    doc.organism = (organism or "").strip() or None
    doc.topic = (topic or "").strip() or None
    doc.summary = (summary or "").strip() or None
    doc.content_text = cleaned
    doc.content_hash = digest
    doc.status = DocumentStatus.READY.value
    doc.is_published = publish
    doc.metadata_json = metadata_json or {}

    clear_document_chunks(db, doc.id)
    create_chunks_for_document(db, doc, cleaned, with_embeddings=True)

    db.commit()
    db.refresh(doc)
    return doc


def sync_visual_ocr_for_document(
    db: Session,
    *,
    doc: Document,
    pdf_bytes: bytes,
):
    clear_document_images(db, doc.id)

    meta = dict(doc.metadata_json or {})
    meta["visual_ocr_ready"] = False
    meta["visual_ocr_error"] = None
    meta["visual_pages_count"] = 0
    meta["visual_ocr_items"] = 0
    doc.metadata_json = meta
    db.flush()

    try:
        total = create_visual_rows_for_document(db, doc=doc, pdf_bytes=pdf_bytes, ocr_lang="spa")
        meta = dict(doc.metadata_json or {})
        meta["visual_ocr_ready"] = True
        meta["visual_ocr_error"] = None
        meta["visual_pages_count"] = total
        meta["visual_ocr_items"] = total
        doc.metadata_json = meta
    except Exception as e:
        db.rollback()

        fresh_doc = db.query(Document).filter(Document.id == doc.id).first()
        if fresh_doc is None:
            raise

        meta = dict(fresh_doc.metadata_json or {})
        meta["visual_ocr_ready"] = False
        meta["visual_ocr_error"] = str(e)
        meta["visual_pages_count"] = 0
        meta["visual_ocr_items"] = 0
        fresh_doc.metadata_json = meta

        db.commit()
        db.refresh(fresh_doc)
        return fresh_doc

    db.commit()
    db.refresh(doc)
    return doc


def ingest_document_from_url(
    db: Session,
    *,
    url: str,
    title: str | None = None,
    source_id: int | None = None,
    document_type: str | None = None,
    organism: str | None = None,
    topic: str | None = None,
    summary: str | None = None,
    publish: bool = True,
):
    extracted = extract_text_from_url(url)

    detected_title = title or extracted.get("title") or "Documento desde URL"
    content_text = extracted.get("content_text") or ""
    final_url = extracted.get("url") or url
    metadata_json = extracted.get("metadata") or {}
    landing_url = extracted.get("landing_url")
    embedded_pdf_url = extracted.get("embedded_pdf_url")

    if landing_url:
        metadata_json["landing_url"] = landing_url
    if embedded_pdf_url:
        metadata_json["embedded_pdf_url"] = embedded_pdf_url

    doc = ingest_document_text(
        db,
        title=detected_title,
        text=content_text,
        url=final_url,
        source_id=source_id,
        document_type=document_type,
        organism=organism,
        topic=topic,
        summary=summary,
        publish=publish,
        metadata_json=metadata_json,
    )

    pdf_url = embedded_pdf_url or (final_url if extracted.get("content_type") == "application/pdf" else None)
    if pdf_url:
        pdf_bytes = _download_bytes(pdf_url)
        sync_visual_ocr_for_document(db, doc=doc, pdf_bytes=pdf_bytes)

    return doc


def ingest_document_from_pdf_bytes(
    db: Session,
    *,
    data: bytes,
    filename: str | None = None,
    title: str | None = None,
    url: str | None = None,
    source_id: int | None = None,
    document_type: str | None = None,
    organism: str | None = None,
    topic: str | None = None,
    summary: str | None = None,
    publish: bool = True,
):
    extracted = extract_text_from_pdf_bytes(data, source_url=url, filename=filename)

    detected_title = title or extracted.get("title") or "Documento PDF"
    content_text = extracted.get("content_text") or ""
    metadata_json = extracted.get("metadata") or {}

    doc = ingest_document_text(
        db,
        title=detected_title,
        text=content_text,
        url=url,
        source_id=source_id,
        document_type=document_type,
        organism=organism,
        topic=topic,
        summary=summary,
        publish=publish,
        metadata_json=metadata_json,
    )

    sync_visual_ocr_for_document(db, doc=doc, pdf_bytes=data)
    return doc


def reingest_existing_document_from_url(db: Session, *, doc: Document) -> Document:
    if not (doc.url or "").strip():
        raise ValueError("El documento no tiene URL para reingestar")

    extracted = extract_text_from_url(doc.url.strip())

    detected_title = extracted.get("title") or doc.title or "Documento desde URL"
    content_text = extracted.get("content_text") or ""
    final_url = extracted.get("url") or doc.url
    metadata_json = extracted.get("metadata") or {}
    landing_url = extracted.get("landing_url")
    embedded_pdf_url = extracted.get("embedded_pdf_url")

    if landing_url:
        metadata_json["landing_url"] = landing_url
    if embedded_pdf_url:
        metadata_json["embedded_pdf_url"] = embedded_pdf_url

    updated = update_document_text(
        db,
        doc=doc,
        title=detected_title,
        text=content_text,
        url=final_url,
        document_type=doc.document_type,
        organism=doc.organism,
        topic=doc.topic,
        summary=doc.summary,
        publish=doc.is_published,
        metadata_json=metadata_json,
    )

    pdf_url = embedded_pdf_url or (final_url if extracted.get("content_type") == "application/pdf" else None)
    if pdf_url:
        pdf_bytes = _download_bytes(pdf_url)
        sync_visual_ocr_for_document(db, doc=updated, pdf_bytes=pdf_bytes)
    else:
        clear_document_images(db, updated.id)
        meta = dict(updated.metadata_json or {})
        meta["visual_ocr_ready"] = False
        meta["visual_ocr_error"] = None
        meta["visual_pages_count"] = 0
        meta["visual_ocr_items"] = 0
        updated.metadata_json = meta
        db.commit()
        db.refresh(updated)

    return updated


def reindex_document_embeddings(db: Session, doc_id: int) -> int:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        return 0

    clear_document_chunks(db, doc.id)
    total = create_chunks_for_document(db, doc, doc.content_text or "", with_embeddings=True)

    visual_rows = db.query(DocumentImage).filter(DocumentImage.document_id == doc.id).all()
    for row in visual_rows:
        text_value = normalize_text(row.ocr_text or "")
        row.char_count = len(text_value) if text_value else 0
        row.embedding = embed_document(text_value) if len(text_value) >= 30 else None

    db.commit()
    return total