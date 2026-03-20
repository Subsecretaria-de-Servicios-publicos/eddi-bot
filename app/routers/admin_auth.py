from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..core.config import settings

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["admin-auth"])


@router.get("/rag/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return templates.TemplateResponse(
        "admin_login.html",
        {"request": request, "error": None},
    )


@router.post("/rag/admin/login", response_class=HTMLResponse)
def admin_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if username == settings.ADMIN_USERNAME and password == settings.ADMIN_PASSWORD:
        request.session["is_admin"] = True
        request.session["admin_username"] = username
        return RedirectResponse(url="/rag/admin", status_code=303)

    return templates.TemplateResponse(
        "admin_login.html",
        {
            "request": request,
            "error": "Credenciales inválidas",
        },
        status_code=401,
    )


@router.post("/rag/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/rag/admin/login", status_code=303)