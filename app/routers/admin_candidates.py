from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_admin_session
from ..models import DiscoveryCandidate, Document
from ..services.ingestion import ingest_document_from_url

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/rag/admin/candidates", tags=["admin-candidates"])


@router.get("", response_class=HTMLResponse)
def list_candidates_page(
    request: Request,
    status: str = "",
    q: str = "",
    source_id: str = "",
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    query = db.query(DiscoveryCandidate)

    if status == "ignored":
        query = query.filter(DiscoveryCandidate.status == "ignored")
    elif status == "ingested":
        query = query.filter(DiscoveryCandidate.status == "ingested")
    elif status == "all":
        pass
    else:
        query = query.filter(DiscoveryCandidate.status == "new")

    if q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                DiscoveryCandidate.title.ilike(term),
                DiscoveryCandidate.url.ilike(term),
            )
        )

    if source_id.strip():
        try:
            source_id_int = int(source_id.strip())
            query = query.filter(DiscoveryCandidate.source_id == source_id_int)
        except ValueError:
            query = query.filter(DiscoveryCandidate.id == -1)

    items = query.order_by(DiscoveryCandidate.created_at.desc(), DiscoveryCandidate.id.desc()).all()

    source_ids = (
        db.query(DiscoveryCandidate.source_id)
        .filter(DiscoveryCandidate.source_id.isnot(None))
        .distinct()
        .order_by(DiscoveryCandidate.source_id.asc())
        .all()
    )
    source_ids = [str(x[0]) for x in source_ids if x[0] is not None]

    return templates.TemplateResponse(
        "admin_candidates.html",
        {
            "request": request,
            "items": items,
            "status": status,
            "q": q,
            "source_id": source_id,
            "source_ids": source_ids,
        },
    )


@router.post("/{candidate_id}/ignore")
def ignore_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    c = db.query(DiscoveryCandidate).filter(DiscoveryCandidate.id == candidate_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate no encontrado")

    c.status = "ignored"
    db.commit()
    return RedirectResponse(url="/rag/admin/candidates", status_code=303)


@router.post("/{candidate_id}/delete")
def delete_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    c = db.query(DiscoveryCandidate).filter(DiscoveryCandidate.id == candidate_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate no encontrado")

    db.delete(c)
    db.commit()
    return RedirectResponse(url="/rag/admin/candidates", status_code=303)


@router.post("/{candidate_id}/promote")
def promote_candidate(
    candidate_id: int,
    document_type: str = Form(""),
    organism: str = Form(""),
    topic: str = Form(""),
    summary: str = Form(""),
    is_published: str = Form("true"),
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    c = db.query(DiscoveryCandidate).filter(DiscoveryCandidate.id == candidate_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate no encontrado")

    publish = str(is_published).lower() in {"true", "1", "on", "yes", "si"}

    existing = db.query(Document).filter(Document.url == c.url).first()
    if existing:
        c.status = "ingested"
        db.commit()
        return RedirectResponse(url=f"/rag/admin/docs/{existing.id}", status_code=303)

    doc = ingest_document_from_url(
        db,
        url=c.url,
        title=c.title or None,
        source_id=c.source_id,
        document_type=document_type or c.kind or None,
        organism=organism or None,
        topic=topic or None,
        summary=summary or "Promovido desde discovery candidate",
        publish=publish,
    )

    c.status = "ingested"
    db.commit()
    return RedirectResponse(url=f"/rag/admin/docs/{doc.id}", status_code=303)