from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db import get_db
from ..models import Document, DocumentChunk
from ..services.ingestion import (
    ingest_document_text,
    ingest_document_from_url,
    ingest_document_from_pdf_bytes,
    reindex_document_embeddings,
    reingest_existing_document_from_url,
    update_document_text,
)
from ..deps import require_admin_session

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/rag/admin/docs", tags=["admin-docs"])


def check_admin(auth: str | None):
    expected = f"Bearer {settings.ADMIN_TOKEN}"
    if auth != expected:
        raise HTTPException(status_code=401, detail="No autorizado")


@router.get("", response_class=HTMLResponse)
def admin_docs_page(
    request: Request,
    q: str = "",
    document_type: str = "",
    published: str = "",
    needs_ocr: str = "",
    has_images: str = "",
    embedded_pdf: str = "",
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    query = db.query(Document)

    if q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Document.title.ilike(term),
                Document.url.ilike(term),
                Document.organism.ilike(term),
                Document.topic.ilike(term),
                Document.document_type.ilike(term),
            )
        )

    if document_type.strip():
        query = query.filter(Document.document_type == document_type.strip())

    if published == "yes":
        query = query.filter(Document.is_published.is_(True))
    elif published == "no":
        query = query.filter(Document.is_published.is_(False))

    if needs_ocr == "yes":
        query = query.filter(Document.metadata_json["low_text_pdf"].astext == "true")
    elif needs_ocr == "no":
        query = query.filter(
            or_(
                Document.metadata_json["low_text_pdf"].astext == "false",
                Document.metadata_json["low_text_pdf"].astext.is_(None),
            )
        )

    if has_images == "yes":
        query = query.filter(Document.metadata_json["pdf_has_images"].astext == "true")
    elif has_images == "no":
        query = query.filter(
            or_(
                Document.metadata_json["pdf_has_images"].astext == "false",
                Document.metadata_json["pdf_has_images"].astext.is_(None),
            )
        )

    if embedded_pdf == "yes":
        query = query.filter(Document.metadata_json["embedded_from_html"].astext == "true")
    elif embedded_pdf == "no":
        query = query.filter(
            or_(
                Document.metadata_json["embedded_from_html"].astext == "false",
                Document.metadata_json["embedded_from_html"].astext.is_(None),
            )
        )

    docs = query.order_by(Document.created_at.desc()).limit(300).all()

    all_types = (
        db.query(Document.document_type)
        .filter(Document.document_type.isnot(None))
        .distinct()
        .order_by(Document.document_type.asc())
        .all()
    )
    all_types = [x[0] for x in all_types if x[0]]

    return templates.TemplateResponse(
        "admin_docs.html",
        {
            "request": request,
            "docs": docs,
            "q": q,
            "document_type": document_type,
            "published": published,
            "needs_ocr": needs_ocr,
            "has_images": has_images,
            "embedded_pdf": embedded_pdf,
            "all_types": all_types,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def admin_docs_new(request: Request):
    return templates.TemplateResponse("admin_doc_new.html", {"request": request})


@router.post("/new")
def admin_docs_create(
    title: str = Form(...),
    url: str = Form(""),
    document_type: str = Form(""),
    organism: str = Form(""),
    topic: str = Form(""),
    summary: str = Form(""),
    content_text: str = Form(...),
    is_published: str = Form("true"),
    db: Session = Depends(get_db),
):
    publish = str(is_published).lower() in {"true", "1", "on", "yes", "si"}

    doc = ingest_document_text(
        db,
        title=title,
        text=content_text,
        url=url or None,
        document_type=document_type or None,
        organism=organism or None,
        topic=topic or None,
        summary=summary or None,
        publish=publish,
    )
    return RedirectResponse(url=f"/rag/admin/docs/{doc.id}", status_code=303)


@router.get("/ingest", response_class=HTMLResponse)
def admin_docs_ingest_page(request: Request):
    return templates.TemplateResponse("admin_ingest.html", {"request": request})


@router.post("/ingest/url")
def admin_docs_ingest_url(
    url: str = Form(...),
    title: str = Form(""),
    document_type: str = Form(""),
    organism: str = Form(""),
    topic: str = Form(""),
    summary: str = Form(""),
    is_published: str = Form("true"),
    db: Session = Depends(get_db),
):
    publish = str(is_published).lower() in {"true", "1", "on", "yes", "si"}

    doc = ingest_document_from_url(
        db,
        url=url,
        title=title or None,
        document_type=document_type or None,
        organism=organism or None,
        topic=topic or None,
        summary=summary or None,
        publish=publish,
    )
    return RedirectResponse(url=f"/rag/admin/docs/{doc.id}", status_code=303)


@router.post("/ingest/pdf")
async def admin_docs_ingest_pdf(
    pdf_file: UploadFile = File(...),
    title: str = Form(""),
    url: str = Form(""),
    document_type: str = Form(""),
    organism: str = Form(""),
    topic: str = Form(""),
    summary: str = Form(""),
    is_published: str = Form("true"),
    db: Session = Depends(get_db),
):
    publish = str(is_published).lower() in {"true", "1", "on", "yes", "si"}
    data = await pdf_file.read()

    doc = ingest_document_from_pdf_bytes(
        db,
        data=data,
        filename=pdf_file.filename,
        title=title or None,
        url=url or None,
        document_type=document_type or None,
        organism=organism or None,
        topic=topic or None,
        summary=summary or None,
        publish=publish,
    )
    return RedirectResponse(url=f"/rag/admin/docs/{doc.id}", status_code=303)


@router.get("/{doc_id}", response_class=HTMLResponse)
def admin_doc_detail(
    request: Request,
    doc_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == doc.id)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )

    return templates.TemplateResponse(
        "admin_doc_detail.html",
        {
            "request": request,
            "doc": doc,
            "chunks": chunks,
        },
    )


@router.get("/{doc_id}/edit", response_class=HTMLResponse)
def admin_doc_edit(
    request: Request,
    doc_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    return templates.TemplateResponse(
        "admin_doc_edit.html",
        {
            "request": request,
            "doc": doc,
        },
    )


@router.post("/{doc_id}/edit")
def admin_doc_edit_save(
    doc_id: int,
    title: str = Form(...),
    url: str = Form(""),
    document_type: str = Form(""),
    organism: str = Form(""),
    topic: str = Form(""),
    summary: str = Form(""),
    content_text: str = Form(...),
    is_published: str = Form("true"),
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    publish = str(is_published).lower() in {"true", "1", "on", "yes", "si"}

    update_document_text(
        db,
        doc=doc,
        title=title,
        text=content_text,
        url=url or None,
        document_type=document_type or None,
        organism=organism or None,
        topic=topic or None,
        summary=summary or None,
        publish=publish,
        metadata_json=doc.metadata_json or {},
    )
    return RedirectResponse(url=f"/rag/admin/docs/{doc_id}", status_code=303)


@router.post("/{doc_id}/reingest")
def admin_doc_reingest(
    doc_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    if not (doc.url or "").strip():
        raise HTTPException(status_code=400, detail="El documento no tiene URL para reingestar")

    reingest_existing_document_from_url(db, doc=doc)
    return RedirectResponse(url=f"/rag/admin/docs/{doc_id}", status_code=303)


@router.post("/{doc_id}/delete")
def admin_doc_delete(
    doc_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    db.delete(doc)
    db.commit()
    return RedirectResponse(url="/rag/admin/docs", status_code=303)


@router.post("/{doc_id}/publish")
def admin_doc_publish(
    doc_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    d = db.query(Document).filter(Document.id == doc_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    d.is_published = True
    db.commit()
    return RedirectResponse(url=f"/rag/admin/docs/{doc_id}", status_code=303)


@router.post("/{doc_id}/unpublish")
def admin_doc_unpublish(
    doc_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    d = db.query(Document).filter(Document.id == doc_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    d.is_published = False
    db.commit()
    return RedirectResponse(url=f"/rag/admin/docs/{doc_id}", status_code=303)


@router.post("/{doc_id}/reindex")
def admin_doc_reindex(
    doc_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    d = db.query(Document).filter(Document.id == doc_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    reindex_document_embeddings(db, doc_id)
    return RedirectResponse(url=f"/rag/admin/docs/{doc_id}", status_code=303)


@router.get("/api/list")
def admin_docs_list_api(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    check_admin(authorization)
    docs = db.query(Document).order_by(Document.created_at.desc()).limit(200).all()
    return [
        {
            "id": d.id,
            "title": d.title,
            "status": d.status,
            "is_published": d.is_published,
            "document_type": d.document_type,
            "url": d.url,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


@router.get("/api/{doc_id}")
def admin_doc_detail_api(
    doc_id: int,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    check_admin(authorization)

    d = db.query(Document).filter(Document.id == doc_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    return {
        "id": d.id,
        "source_id": d.source_id,
        "title": d.title,
        "slug": d.slug,
        "url": d.url,
        "document_type": d.document_type,
        "organism": d.organism,
        "topic": d.topic,
        "summary": d.summary,
        "content_text": d.content_text,
        "status": d.status,
        "is_published": d.is_published,
        "content_hash": d.content_hash,
        "metadata_json": d.metadata_json or {},
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }