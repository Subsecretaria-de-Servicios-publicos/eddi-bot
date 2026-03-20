"""add document_images

Revision ID: 9f2d7c1a6b11
Revises: 5785847ec70c
Create Date: 2026-03-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

try:
    from pgvector.sqlalchemy import Vector
    VECTOR_TYPE = Vector(1536)
except Exception:
    VECTOR_TYPE = sa.JSON()


revision: str = "9f2d7c1a6b11"
down_revision: Union[str, Sequence[str], None] = "5785847ec70c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_images",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("image_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("image_path", sa.String(length=1200), nullable=False),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=True),
        sa.Column("score_boost", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("embedding", VECTOR_TYPE, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("document_id", "page_number", "image_index", name="uq_doc_image_page_idx"),
    )
    op.create_index("ix_document_images_document_id", "document_images", ["document_id"], unique=False)
    op.create_index("ix_document_images_page_number", "document_images", ["page_number"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_document_images_page_number", table_name="document_images")
    op.drop_index("ix_document_images_document_id", table_name="document_images")
    op.drop_table("document_images")