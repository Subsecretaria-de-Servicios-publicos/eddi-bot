import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Document
from ..services.export_service import export_documents_json, export_documents_csv

router = APIRouter(prefix="/rag/admin/exports", tags=["admin-exports"])


def _serialize_docs(docs: list[Document]) -> list[dict]:
    return [
        {
            "id": d.id,
            "source_id": d.source_id,
            "title": d.title,
            "url": d.url,
            "document_type": d.document_type,
            "organism": d.organism,
            "topic": d.topic,
            "summary": d.summary,
            "status": d.status,
            "is_published": d.is_published,
            "content_hash": d.content_hash,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        }
        for d in docs
    ]


@router.get("/documents.json")
def export_docs_json(
    published_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    q = db.query(Document).order_by(Document.created_at.desc())
    if published_only:
        q = q.filter(Document.is_published.is_(True))
    docs = q.all()

    payload = export_documents_json(_serialize_docs(docs))
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=documents.json"},
    )


@router.get("/documents.csv")
def export_docs_csv(
    published_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    q = db.query(Document).order_by(Document.created_at.desc())
    if published_only:
        q = q.filter(Document.is_published.is_(True))
    docs = q.all()

    payload = export_documents_csv(_serialize_docs(docs))
    return Response(
        content=payload,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=documents.csv"},
    )