from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import IngestionJob

from ..deps import require_admin_session

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/rag/admin/jobs", tags=["admin-jobs"])


@router.get("", response_class=HTMLResponse)
def jobs_page(request: Request, db: Session = Depends(get_db)):
    jobs = db.query(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(200).all()
    return templates.TemplateResponse(
        "admin_jobs.html",
        {
            "request": request,
            "jobs": jobs,
        },
    )