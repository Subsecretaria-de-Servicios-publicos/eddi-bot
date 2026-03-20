from pathlib import Path

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db import get_db
from ..models import Source
from ..schemas import SourceCreate
from ..services.job_service import create_job, mark_job_done

from ..deps import require_admin_session

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/rag/admin/sources", tags=["admin-sources"])


def check_admin(auth: str | None):
    expected = f"Bearer {settings.ADMIN_TOKEN}"
    if auth != expected:
        raise HTTPException(status_code=401, detail="No autorizado")


@router.get("", response_class=HTMLResponse)
def list_sources_page(request: Request, db: Session = Depends(get_db)):
    items = db.query(Source).order_by(Source.created_at.desc()).all()
    return templates.TemplateResponse(
        "admin_sources.html",
        {
            "request": request,
            "sources": items,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_source_page(request: Request):
    return templates.TemplateResponse(
        "admin_source_new.html",
        {"request": request},
    )


@router.post("/new")
def create_source_page(
    name: str = Form(...),
    base_url: str = Form(""),
    source_kind: str = Form("website"),
    is_active: str = Form("true"),
    discovery_config_json: str = Form("{}"),
    db: Session = Depends(get_db),
):
    active = str(is_active).lower() in {"true", "1", "on", "yes", "si"}

    try:
        import json
        config = json.loads(discovery_config_json or "{}")
    except Exception:
        config = {}

    s = Source(
        name=name.strip(),
        base_url=base_url.strip() or None,
        source_kind=source_kind.strip() or "website",
        is_active=active,
        discovery_config_json=config,
    )
    db.add(s)
    db.commit()
    db.refresh(s)

    return RedirectResponse(url="/rag/admin/sources", status_code=303)


@router.post("/{source_id}/toggle")
def toggle_source(source_id: int, db: Session = Depends(get_db)):
    s = db.query(Source).filter(Source.id == source_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Fuente no encontrada")

    s.is_active = not s.is_active
    db.commit()
    return RedirectResponse(url="/rag/admin/sources", status_code=303)


@router.get("/api/list")
def list_sources_api(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    check_admin(authorization)
    items = db.query(Source).order_by(Source.id.desc()).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "base_url": s.base_url,
            "source_kind": s.source_kind,
            "is_active": s.is_active,
            "discovery_config_json": s.discovery_config_json or {},
        }
        for s in items
    ]