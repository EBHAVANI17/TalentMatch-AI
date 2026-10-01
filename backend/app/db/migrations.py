"""Run Alembic migrations programmatically (used on startup and in tests).

CLI equivalent, from the backend/ folder:  python -m alembic upgrade head
"""
import logging

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.core.config import BACKEND_DIR
from app.core.database import engine

logger = logging.getLogger(__name__)

BASELINE_REVISION = "0001"


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["configure_logger"] = False
    return cfg


def run_migrations() -> None:
    cfg = _alembic_config()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        tables = set(inspect(connection).get_table_names())
        if "alembic_version" not in tables and "users" in tables:
            # Database was created by the old create_all() startup path; its schema
            # matches the baseline, so record that instead of recreating tables.
            logger.info("Existing pre-migration database detected; stamping baseline %s", BASELINE_REVISION)
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")
