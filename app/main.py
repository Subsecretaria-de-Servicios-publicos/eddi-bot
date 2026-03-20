from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .core.config import settings
from .db import Base, engine
from .routers.health import router as health_router
from .routers.public_chat import router as public_chat_router
from .routers.public_pages import router as public_pages_router
from .routers.admin_auth import router as admin_auth_router
from .routers.admin_dashboard import router as admin_dashboard_router
from .routers.admin_docs import router as admin_docs_router
from .routers.admin_sources import router as admin_sources_router
from .routers.admin_ingest import router as admin_ingest_router
from .routers.admin_jobs import router as admin_jobs_router
from .routers.admin_candidates import router as admin_candidates_router
from .routers.admin_chats import router as admin_chats_router
from .routers.admin_exports import router as admin_exports_router
from .routers.admin_metrics import router as admin_metrics_router
from .routers.admin_sync import router as admin_sync_router
from .routers.n8n_webhooks import router as n8n_webhooks_router

# Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME)

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET_KEY)

origins = [x.strip() for x in settings.CORS_ORIGINS.split(",")] if settings.CORS_ORIGINS else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(public_pages_router)
app.include_router(public_chat_router)
app.include_router(admin_auth_router)
app.include_router(admin_dashboard_router)
app.include_router(admin_docs_router)
app.include_router(admin_sources_router)
app.include_router(admin_ingest_router)
app.include_router(admin_jobs_router)
app.include_router(admin_candidates_router)
app.include_router(admin_chats_router)
app.include_router(admin_exports_router)
app.include_router(admin_metrics_router)
app.include_router(admin_sync_router)
app.include_router(n8n_webhooks_router)