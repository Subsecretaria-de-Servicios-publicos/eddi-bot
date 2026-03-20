from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_admin_session
from ..models import Document, Source, IngestionJob, DiscoveryCandidate, ChatSession, ChatMessage

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/rag/admin", tags=["admin-dashboard"])


@router.get("", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_session),
):
    total_documents = db.query(func.count(Document.id)).scalar() or 0
    published_documents = db.query(func.count(Document.id)).filter(Document.is_published.is_(True)).scalar() or 0
    total_sources = db.query(func.count(Source.id)).scalar() or 0
    active_sources = db.query(func.count(Source.id)).filter(Source.is_active.is_(True)).scalar() or 0
    total_jobs = db.query(func.count(IngestionJob.id)).scalar() or 0
    total_candidates = db.query(func.count(DiscoveryCandidate.id)).scalar() or 0
    total_sessions = db.query(func.count(ChatSession.id)).scalar() or 0
    total_messages = db.query(func.count(ChatMessage.id)).scalar() or 0

    recent_documents = db.query(Document).order_by(Document.created_at.desc()).limit(10).all()
    recent_jobs = db.query(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(10).all()

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "total_documents": total_documents,
            "published_documents": published_documents,
            "total_sources": total_sources,
            "active_sources": active_sources,
            "total_jobs": total_jobs,
            "total_candidates": total_candidates,
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "recent_documents": recent_documents,
            "recent_jobs": recent_jobs,
        },
    )