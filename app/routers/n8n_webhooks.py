from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db import get_db
from ..models import Source, DiscoveryCandidate
from ..schemas import DiscoverySaveRequest, RawIngestRequest
from ..services.discovery_service import discover_urls
from ..services.ingestion import ingest_document_text

router = APIRouter(prefix="/rag/webhook", tags=["n8n-webhooks"])


def check_admin(auth: str | None):
    expected = f"Bearer {settings.ADMIN_TOKEN}"
    if auth != expected:
        raise HTTPException(status_code=401, detail="No autorizado")


@router.post("/discover/source/{source_id}")
def webhook_discover_source(
    source_id: int,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    check_admin(authorization)

    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Fuente no encontrada")
    if not source.base_url:
        raise HTTPException(status_code=400, detail="La fuente no tiene base_url")

    cfg = source.discovery_config_json or {}
    items = discover_urls(
        base_url=source.base_url,
        allowed_prefixes=cfg.get("allowed_prefixes") or [],
        allowed_extensions=cfg.get("allowed_extensions") or ["html", "pdf"],
    )

    created = 0
    updated = 0

    for item in items:
        existing = (
            db.query(DiscoveryCandidate)
            .filter(
                DiscoveryCandidate.source_id == source.id,
                DiscoveryCandidate.url == item["url"],
            )
            .first()
        )
        if existing:
            existing.title = item.get("title") or existing.title
            existing.kind = item.get("kind") or existing.kind
            updated += 1
        else:
            db.add(DiscoveryCandidate(
                source_id=source.id,
                url=item["url"],
                title=item.get("title"),
                kind=item.get("kind"),
                metadata_json={},
            ))
            created += 1

    db.commit()

    return {
        "ok": True,
        "source_id": source.id,
        "base_url": source.base_url,
        "items_found": len(items),
        "created": created,
        "updated": updated,
        "items": items,
    }


@router.post("/ingest/raw")
def webhook_ingest_raw(
    payload: RawIngestRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    check_admin(authorization)

    doc = ingest_document_text(
        db,
        title=payload.title,
        text=payload.content_text,
        url=payload.url,
        source_id=payload.source_id,
        document_type=payload.document_type,
        organism=payload.organism,
        topic=payload.topic,
        summary=payload.summary,
        publish=payload.is_published,
    )
    return {
        "ok": True,
        "document_id": doc.id,
        "title": doc.title,
    }


@router.post("/discover/save")
def webhook_discover_save(
    payload: DiscoverySaveRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    check_admin(authorization)

    source = db.query(Source).filter(Source.id == payload.source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Fuente no encontrada")

    created = 0
    updated = 0

    for item in payload.items:
        existing = (
            db.query(DiscoveryCandidate)
            .filter(
                DiscoveryCandidate.source_id == source.id,
                DiscoveryCandidate.url == item.url,
            )
            .first()
        )
        if existing:
            existing.title = item.title or existing.title
            existing.kind = item.kind or existing.kind
            updated += 1
        else:
            db.add(DiscoveryCandidate(
                source_id=source.id,
                url=item.url,
                title=item.title,
                kind=item.kind,
                metadata_json={},
            ))
            created += 1

    db.commit()

    return {
        "ok": True,
        "source_id": source.id,
        "created": created,
        "updated": updated,
    }