from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db import get_db
from ..models import Source, IngestionJob, DiscoveryCandidate, CandidateStatus
from ..schemas import RawIngestRequest, DiscoverySaveRequest
from ..services.ingestion import ingest_document_text, ingest_document_from_url
from ..services.job_service import create_job, mark_job_running, mark_job_done, mark_job_error

router = APIRouter(prefix="/rag/admin/ingest", tags=["admin-ingest"])


def check_admin(auth: str | None):
    expected = f"Bearer {settings.ADMIN_TOKEN}"
    if auth != expected:
        raise HTTPException(status_code=401, detail="No autorizado")


@router.post("/raw")
def ingest_raw(
    payload: RawIngestRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    check_admin(authorization)

    job = create_job(
        db,
        source_id=payload.source_id,
        job_type="raw_ingest",
        stats_json={"title": payload.title},
    )
    db.commit()

    try:
        mark_job_running(db, job)
        db.commit()

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

        mark_job_done(
            db,
            job,
            stats_json={
                "document_id": doc.id,
                "title": doc.title,
                "mode": "raw",
            },
        )
        db.commit()

        return {
            "ok": True,
            "job_id": job.id,
            "document_id": doc.id,
            "title": doc.title,
        }

    except Exception as e:
        mark_job_error(db, job, error_text=str(e))
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/discover/save")
def discover_save(
    payload: DiscoverySaveRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    check_admin(authorization)

    source = db.query(Source).filter(Source.id == payload.source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Fuente no encontrada")

    job = create_job(
        db,
        source_id=source.id,
        job_type="discover_save",
        stats_json={"items_received": len(payload.items)},
    )
    db.commit()

    try:
        mark_job_running(db, job)
        db.commit()

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
                existing.metadata_json = existing.metadata_json or {}
                updated += 1
            else:
                row = DiscoveryCandidate(
                    source_id=source.id,
                    url=item.url,
                    title=item.title,
                    kind=item.kind,
                    status=CandidateStatus.NEW.value,
                    metadata_json={},
                )
                db.add(row)
                created += 1

        discovered = source.discovery_config_json or {}
        discovered["items_count"] = len(payload.items)
        source.discovery_config_json = discovered

        mark_job_done(
            db,
            job,
            stats_json={
                "items_received": len(payload.items),
                "created": created,
                "updated": updated,
                "source_id": source.id,
            },
        )
        db.commit()

        return {
            "ok": True,
            "job_id": job.id,
            "source_id": source.id,
            "items_received": len(payload.items),
            "created": created,
            "updated": updated,
        }
    except Exception as e:
        mark_job_error(db, job, error_text=str(e))
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run/source/{source_id}")
def run_ingest_from_source(
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

    job = create_job(
        db,
        source_id=source.id,
        job_type="source_ingest",
        stats_json={"base_url": source.base_url},
    )
    db.commit()

    try:
        mark_job_running(db, job)
        db.commit()

        doc = ingest_document_from_url(
            db,
            url=source.base_url,
            title=source.name,
            source_id=source.id,
            document_type=source.source_kind,
            organism=source.name,
            topic="ingesta_desde_fuente",
            summary=f"Ingesta automática desde fuente {source.name}",
            publish=True,
        )

        mark_job_done(
            db,
            job,
            stats_json={
                "document_id": doc.id,
                "source_id": source.id,
                "title": doc.title,
            },
        )
        db.commit()

        return {
            "ok": True,
            "job_id": job.id,
            "source_id": source.id,
            "document_id": doc.id,
        }

    except Exception as e:
        mark_job_error(db, job, error_text=str(e))
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs")
def list_jobs(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    check_admin(authorization)

    jobs = db.query(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(200).all()

    return [
        {
            "id": j.id,
            "source_id": j.source_id,
            "job_type": j.job_type,
            "status": j.status,
            "stats_json": j.stats_json or {},
            "error_text": j.error_text,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]