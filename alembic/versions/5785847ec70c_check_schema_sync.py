"""check schema sync

Revision ID: 5785847ec70c
Revises: 2f856b223131
Create Date: 2026-03-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5785847ec70c"
down_revision: Union[str, Sequence[str], None] = "2f856b223131"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    cols = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in cols)


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    idxs = inspector.get_indexes(table_name)
    return any(idx["name"] == index_name for idx in idxs)


def _has_unique_constraint(inspector, table_name: str, constraint_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    uqs = inspector.get_unique_constraints(table_name)
    return any(uq["name"] == constraint_name for uq in uqs)


def _has_duplicate_non_null_values(bind, table_name: str, column_name: str) -> bool:
    sql = sa.text(f"""
        SELECT 1
        FROM "{table_name}"
        WHERE "{column_name}" IS NOT NULL
        GROUP BY "{column_name}"
        HAVING COUNT(*) > 1
        LIMIT 1
    """)
    row = bind.execute(sql).first()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # documents.source_id index
    if _has_column(inspector, "documents", "source_id") and not _has_index(inspector, "documents", "ix_documents_source_id"):
        op.create_index("ix_documents_source_id", "documents", ["source_id"], unique=False)

    # documents.url unique constraint
    if _has_column(inspector, "documents", "url") and not _has_unique_constraint(inspector, "documents", "uq_documents_url"):
        if _has_duplicate_non_null_values(bind, "documents", "url"):
            raise RuntimeError(
                "No se pudo crear uq_documents_url porque hay valores duplicados en documents.url (no nulos)."
            )
        op.create_unique_constraint("uq_documents_url", "documents", ["url"])

    # ingestion_jobs.source_id index
    if _has_column(inspector, "ingestion_jobs", "source_id") and not _has_index(inspector, "ingestion_jobs", "ix_ingestion_jobs_source_id"):
        op.create_index("ix_ingestion_jobs_source_id", "ingestion_jobs", ["source_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_index(inspector, "ingestion_jobs", "ix_ingestion_jobs_source_id"):
        op.drop_index("ix_ingestion_jobs_source_id", table_name="ingestion_jobs")

    if _has_unique_constraint(inspector, "documents", "uq_documents_url"):
        op.drop_constraint("uq_documents_url", "documents", type_="unique")

    if _has_index(inspector, "documents", "ix_documents_source_id"):
        op.drop_index("ix_documents_source_id", table_name="documents")