from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Document, Source, IngestionJob, DiscoveryCandidate, ChatSession, ChatMessage

router = APIRouter(prefix="/rag/admin/metrics", tags=["admin-metrics"])


@router.get("")
def metrics(db: Session = Depends(get_db)):
    return {
        "documents_total": db.query(func.count(Document.id)).scalar() or 0,
        "documents_published": db.query(func.count(Document.id)).filter(Document.is_published.is_(True)).scalar() or 0,
        "sources_total": db.query(func.count(Source.id)).scalar() or 0,
        "sources_active": db.query(func.count(Source.id)).filter(Source.is_active.is_(True)).scalar() or 0,
        "jobs_total": db.query(func.count(IngestionJob.id)).scalar() or 0,
        "candidates_total": db.query(func.count(DiscoveryCandidate.id)).scalar() or 0,
        "sessions_total": db.query(func.count(ChatSession.id)).scalar() or 0,
        "messages_total": db.query(func.count(ChatMessage.id)).scalar() or 0,
    }