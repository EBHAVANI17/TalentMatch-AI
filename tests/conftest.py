"""Shared pytest setup.

Tests run against a throwaway database so they never touch the developer's
local data. Set TEST_DATABASE_URL to run the suite against Postgres instead,
e.g. TEST_DATABASE_URL=postgresql+psycopg://talentmatch:talentmatch@localhost:5432/talentmatch_test
"""
import os
import sys
import tempfile

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, BACKEND_DIR)

# Must be set before anything imports app.core.database / app.core.config.
_tmp_dir = tempfile.mkdtemp(prefix="talentmatch_test_")
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", f"sqlite:///{os.path.join(_tmp_dir, 'test.db')}"
)
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DEMO_MODE", "true")


@pytest.fixture(scope="session", autouse=True)
def _seeded_database():
    from sqlalchemy import text

    from app.core.database import Base, engine
    from app.db.seed import init_db

    if engine.dialect.name != "sqlite":
        # Start every Postgres run from an empty schema.
        Base.metadata.drop_all(bind=engine)
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    init_db()  # runs migrations, then seeds demo data (DEMO_MODE=true)
    yield
    engine.dispose()
