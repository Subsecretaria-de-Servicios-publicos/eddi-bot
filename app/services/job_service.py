from datetime import datetime

from sqlalchemy.orm import Session

from ..models import IngestionJob, IngestionStatus


def create_job(db: Session, *, source_id: int | None, job_type: str, stats_json: dict | None = None) -> IngestionJob:
    job = IngestionJob(
        source_id=source_id,
        job_type=job_type,
        status=IngestionStatus.PENDING.value,
        stats_json=stats_json or {},
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.flush()
    return job


def mark_job_running(db: Session, job: IngestionJob):
    job.status = IngestionStatus.RUNNING.value
    job.started_at = datetime.utcnow()
    db.flush()


def mark_job_done(db: Session, job: IngestionJob, *, stats_json: dict | None = None):
    job.status = IngestionStatus.DONE.value
    job.finished_at = datetime.utcnow()
    if stats_json is not None:
      job.stats_json = stats_json
    db.flush()


def mark_job_error(db: Session, job: IngestionJob, *, error_text: str, stats_json: dict | None = None):
    job.status = IngestionStatus.ERROR.value
    job.finished_at = datetime.utcnow()
    job.error_text = error_text
    if stats_json is not None:
        job.stats_json = stats_json
    db.flush()