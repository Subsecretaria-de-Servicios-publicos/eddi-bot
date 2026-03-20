import enum
from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    Boolean,
    ForeignKey,
    Text,
    Float,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

try:
    from pgvector.sqlalchemy import Vector
    VECTOR_AVAILABLE = True
except Exception:
    VECTOR_AVAILABLE = False
    Vector = None


class SourceKind(str, enum.Enum):
    WEBSITE = "website"
    PDF = "pdf"
    FAQ = "faq"
    MANUAL = "manual"
    API = "api"


class DocumentStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    ERROR = "error"
    ARCHIVED = "archived"


class IngestionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class CandidateStatus(str, enum.Enum):
    NEW = "new"
    ACCEPTED = "accepted"
    IGNORED = "ignored"
    INGESTED = "ingested"
    ERROR = "error"


class ChatRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    base_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    source_kind: Mapped[str] = mapped_column(String(50), default=SourceKind.WEBSITE.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    discovery_config_json: Mapped[dict | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    documents = relationship("Document", back_populates="source")
    jobs = relationship("IngestionJob", back_populates="source")
    candidates = relationship("DiscoveryCandidate", back_populates="source")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("url", name="uq_documents_url"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True, index=True)

    external_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    slug: Mapped[str | None] = mapped_column(String(500), default=None, index=True)
    url: Mapped[str | None] = mapped_column(String(1200), default=None, index=True)

    document_type: Mapped[str | None] = mapped_column(String(120), default=None, index=True)
    organism: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    topic: Mapped[str | None] = mapped_column(String(255), default=None, index=True)

    summary: Mapped[str | None] = mapped_column(Text, default=None)
    content_text: Mapped[str | None] = mapped_column(Text, default=None)
    content_html: Mapped[str | None] = mapped_column(Text, default=None)

    language: Mapped[str | None] = mapped_column(String(20), default="es")
    status: Mapped[str] = mapped_column(String(50), default=DocumentStatus.DRAFT.value, index=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    content_hash: Mapped[str | None] = mapped_column(String(128), default=None, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, default=dict)

    published_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    source = relationship("Source", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    images = relationship("DocumentImage", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, index=True)
    heading: Mapped[str | None] = mapped_column(String(500), default=None)
    chunk_text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int | None] = mapped_column(Integer, default=None)
    char_count: Mapped[int | None] = mapped_column(Integer, default=None)
    score_boost: Mapped[float] = mapped_column(Float, default=1.0)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, default=dict)

    if VECTOR_AVAILABLE:
        embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    else:
        embedding: Mapped[list[float] | None] = mapped_column(JSON, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="chunks")

class DocumentImage(Base):
    __tablename__ = "document_images"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number", "image_index", name="uq_doc_image_page_idx"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, index=True)
    image_index: Mapped[int] = mapped_column(Integer, default=1)

    image_path: Mapped[str] = mapped_column(String(1200))
    ocr_text: Mapped[str | None] = mapped_column(Text, default=None)
    caption: Mapped[str | None] = mapped_column(Text, default=None)
    char_count: Mapped[int | None] = mapped_column(Integer, default=None)
    score_boost: Mapped[float] = mapped_column(Float, default=1.0)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, default=dict)

    if VECTOR_AVAILABLE:
        embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    else:
        embedding: Mapped[list[float] | None] = mapped_column(JSON, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="images")


class DiscoveryCandidate(Base):
    __tablename__ = "discovery_candidates"
    __table_args__ = (
        UniqueConstraint("source_id", "url", name="uq_candidate_source_url"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    url: Mapped[str] = mapped_column(String(1200), index=True)
    title: Mapped[str | None] = mapped_column(String(500), default=None)
    kind: Mapped[str | None] = mapped_column(String(100), default=None)
    status: Mapped[str] = mapped_column(String(50), default=CandidateStatus.NEW.value, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, default=dict)
    error_text: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    source = relationship("Source", back_populates="candidates")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(50), default=IngestionStatus.PENDING.value, index=True)
    stats_json: Mapped[dict | None] = mapped_column(JSON, default=dict)
    error_text: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    source = relationship("Source", back_populates="jobs")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    channel: Mapped[str | None] = mapped_column(String(100), default="web")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(50), index=True)
    message_text: Mapped[str] = mapped_column(Text)
    retrieval_json: Mapped[dict | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")