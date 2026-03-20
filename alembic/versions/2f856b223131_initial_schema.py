"""initial schema

Revision ID: 2f856b223131
Revises:
Create Date: 2026-03-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

try:
    from pgvector.sqlalchemy import Vector
    VECTOR_TYPE = Vector(1536)
except Exception:
    VECTOR_TYPE = sa.JSON()


# revision identifiers, used by Alembic.
revision: str = "2f856b223131"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # sources
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("base_url", sa.String(length=1000), nullable=True),
        sa.Column("source_kind", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("discovery_config_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sources_name", "sources", ["name"], unique=False)

    # documents
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("slug", sa.String(length=500), nullable=True),
        sa.Column("url", sa.String(length=1200), nullable=True),
        sa.Column("document_type", sa.String(length=120), nullable=True),
        sa.Column("organism", sa.String(length=255), nullable=True),
        sa.Column("topic", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_html", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("url", name="uq_documents_url"),
    )
    op.create_index("ix_documents_source_id", "documents", ["source_id"], unique=False)
    op.create_index("ix_documents_external_id", "documents", ["external_id"], unique=False)
    op.create_index("ix_documents_title", "documents", ["title"], unique=False)
    op.create_index("ix_documents_slug", "documents", ["slug"], unique=False)
    op.create_index("ix_documents_url", "documents", ["url"], unique=False)
    op.create_index("ix_documents_document_type", "documents", ["document_type"], unique=False)
    op.create_index("ix_documents_organism", "documents", ["organism"], unique=False)
    op.create_index("ix_documents_topic", "documents", ["topic"], unique=False)
    op.create_index("ix_documents_status", "documents", ["status"], unique=False)
    op.create_index("ix_documents_is_published", "documents", ["is_published"], unique=False)
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"], unique=False)

    # document_chunks
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(length=500), nullable=True),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=True),
        sa.Column("score_boost", sa.Float(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("embedding", VECTOR_TYPE, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"], unique=False)
    op.create_index("ix_document_chunks_chunk_index", "document_chunks", ["chunk_index"], unique=False)

    # discovery_candidates
    op.create_table(
        "discovery_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("url", sa.String(length=1200), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("kind", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source_id", "url", name="uq_candidate_source_url"),
    )
    op.create_index("ix_discovery_candidates_source_id", "discovery_candidates", ["source_id"], unique=False)
    op.create_index("ix_discovery_candidates_url", "discovery_candidates", ["url"], unique=False)
    op.create_index("ix_discovery_candidates_status", "discovery_candidates", ["status"], unique=False)

    # ingestion_jobs
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("stats_json", sa.JSON(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ingestion_jobs_source_id", "ingestion_jobs", ["source_id"], unique=False)
    op.create_index("ix_ingestion_jobs_job_type", "ingestion_jobs", ["job_type"], unique=False)
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"], unique=False)

    # chat_sessions
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("session_key", sa.String(length=255), nullable=False),
        sa.Column("channel", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_sessions_session_key", "chat_sessions", ["session_key"], unique=True)

    # chat_messages
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id"), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("retrieval_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"], unique=False)
    op.create_index("ix_chat_messages_role", "chat_messages", ["role"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chat_messages_role", table_name="chat_messages")
    op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index("ix_chat_sessions_session_key", table_name="chat_sessions")
    op.drop_table("chat_sessions")

    op.drop_index("ix_ingestion_jobs_status", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_job_type", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_source_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")

    op.drop_index("ix_discovery_candidates_status", table_name="discovery_candidates")
    op.drop_index("ix_discovery_candidates_url", table_name="discovery_candidates")
    op.drop_index("ix_discovery_candidates_source_id", table_name="discovery_candidates")
    op.drop_table("discovery_candidates")

    op.drop_index("ix_document_chunks_chunk_index", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("ix_documents_content_hash", table_name="documents")
    op.drop_index("ix_documents_is_published", table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_topic", table_name="documents")
    op.drop_index("ix_documents_organism", table_name="documents")
    op.drop_index("ix_documents_document_type", table_name="documents")
    op.drop_index("ix_documents_url", table_name="documents")
    op.drop_index("ix_documents_slug", table_name="documents")
    op.drop_index("ix_documents_title", table_name="documents")
    op.drop_index("ix_documents_external_id", table_name="documents")
    op.drop_index("ix_documents_source_id", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_sources_name", table_name="sources")
    op.drop_table("sources")