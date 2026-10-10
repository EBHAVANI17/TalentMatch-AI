"""Alembic environment: uses the app's engine settings and model metadata."""
from logging.config import fileConfig

from alembic import context
import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool
from sqlalchemy.types import TypeDecorator

from app.core.config import settings
from app.core.database import Base
import app.models.db_models  # noqa: F401  (registers all tables on Base.metadata)

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

# Migrations (CLI included) run as the table owner
config.set_main_option("sqlalchemy.url", (settings.database_owner_url or settings.database_url).replace("%", "%%"))
target_metadata = Base.metadata

# Indexes created with raw SQL in migrations (e.g. pgvector HNSW) that the models can't express.
MANUAL_INDEXES = {"ix_embeddings_vector_hnsw"}
VIEWS = {"public_org_profiles"}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and (getattr(obj, "info", {}).get("is_view") or name in VIEWS):
        return False  # views are created with raw SQL in migrations
    return not (type_ == "index" and name in MANUAL_INDEXES)


def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    """Compare encrypted columns (TypeDecorators) by their storage type, e.g. EncryptedString(256) vs VARCHAR(256)."""
    if isinstance(metadata_type, TypeDecorator):
        impl = metadata_type.impl_instance
        if isinstance(impl, sa.String) and isinstance(inspected_type, sa.String):
            # Text vs Text, or String(n) vs VARCHAR(n): differ only if the length differs
            same_kind = isinstance(impl, sa.Text) == isinstance(inspected_type, sa.Text)
            return not (same_kind and impl.length == inspected_type.length)
        return None
    return None  # default comparison


def _is_sqlite() -> bool:
    return settings.database_url.startswith("sqlite")


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=_is_sqlite(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is None:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            _run(connection)
    else:
        _run(connection)


def _run(connection) -> None:
    # SQLite can't ALTER most things; batch mode rebuilds tables safely.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=compare_type,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
