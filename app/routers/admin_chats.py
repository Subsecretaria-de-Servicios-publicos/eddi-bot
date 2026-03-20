from pathlib import Path

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ChatSession, ChatMessage

from ..deps import require_admin_session

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/rag/admin/chats", tags=["admin-chats"])


@router.get("", response_class=HTMLResponse)
def chat_sessions_page(request: Request, db: Session = Depends(get_db)):
    sessions = db.query(ChatSession).order_by(ChatSession.created_at.desc()).limit(200).all()
    return templates.TemplateResponse(
        "admin_chats.html",
        {
            "request": request,
            "sessions": sessions,
        },
    )


@router.get("/{session_key}", response_class=HTMLResponse)
def chat_session_detail(request: Request, session_key: str, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.session_key == session_key).first()
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    return templates.TemplateResponse(
        "admin_chat_detail.html",
        {
            "request": request,
            "session": session,
            "messages": messages,
        },
    )