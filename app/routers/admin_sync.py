from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_admin_session
from ..models import Source, DiscoveryCandidate
from ..services.discovery_service import discover_urls
from ..services.sitemap_service import discover_urls_from_sitemap

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/rag/admin/sync", tags=["admin-sync"])


@router.get("", response_class=HTMLResponse)
def sync_page(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    sources = db.query(Source).order_by(Source.created_at.desc()).all()
    return templates.TemplateResponse(
        "admin_sync.html",
        {
            "request": request,
            "sources": sources,
        },
    )


@router.post("/source/{source_id}")
def sync_source(
    source_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source or not source.base_url:
        return RedirectResponse(url="/rag/admin/sync", status_code=303)

    cfg = source.discovery_config_json or {}
    items = discover_urls(
        base_url=source.base_url,
        allowed_prefixes=cfg.get("allowed_prefixes") or [],
        allowed_extensions=cfg.get("allowed_extensions") or ["html", "pdf"],
    )

    for item in items:
        exists = (
            db.query(DiscoveryCandidate)
            .filter(
                DiscoveryCandidate.source_id == source.id,
                DiscoveryCandidate.url == item["url"],
            )
            .first()
        )
        if not exists:
            db.add(DiscoveryCandidate(
                source_id=source.id,
                url=item["url"],
                title=item.get("title"),
                kind=item.get("kind"),
                metadata_json={},
            ))

    db.commit()
    return RedirectResponse(url="/rag/admin/candidates", status_code=303)


@router.post("/sitemap")
def sync_sitemap(
    sitemap_url: str = Form(...),
    source_id: int = Form(...),
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    urls = discover_urls_from_sitemap(sitemap_url)
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        return RedirectResponse(url="/rag/admin/sync", status_code=303)

    for url in urls:
        exists = (
            db.query(DiscoveryCandidate)
            .filter(
                DiscoveryCandidate.source_id == source.id,
                DiscoveryCandidate.url == url,
            )
            .first()
        )
        if not exists:
            kind = "pdf" if url.lower().endswith(".pdf") else "html"
            db.add(DiscoveryCandidate(
                source_id=source.id,
                url=url,
                title=None,
                kind=kind,
                metadata_json={"origin": "sitemap"},
            ))

    db.commit()
    return RedirectResponse(url="/rag/admin/candidates", status_code=303)