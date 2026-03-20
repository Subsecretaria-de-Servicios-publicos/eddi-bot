from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from alembic import context

from app.core.config import settings
from app.db import Base
from app import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def is_legacy_table_name(table_name: str | None) -> bool:
    if not table_name:
        return False
    return table_name.startswith("rag_") or table_name in {
        "admin_user",
        "admin_session",
    }


def include_object(object_, name, type_, reflected, compare_to):
    table_name = None

    if type_ == "table":
        table_name = name
    else:
        table_name = getattr(object_, "table", None)
        table_name = getattr(table_name, "name", None)

    # Ignorar tablas legacy reflejadas desde la base que no existen en metadata actual
    if reflected and compare_to is None and is_legacy_table_name(table_name):
        return False

    return True


def run_migrations_offline() -> None:
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()