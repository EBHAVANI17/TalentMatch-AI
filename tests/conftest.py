"""Shared pytest setup.

Tests run against a throwaway database so they never touch the developer's
local data. Set TEST_DATABASE_URL to run the suite against Postgres instead,
e.g. TEST_DATABASE_URL=postgresql+psycopg://talentmatch:talentmatch@localhost:5433/talentmatch_test
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
# The whole suite runs from one client IP; rate limits get their own focused tests.
os.environ.setdefault("RATE_LIMIT_DEFAULT", "100000/minute")
os.environ.setdefault("RATE_LIMIT_AUTH", "100000/minute")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("PASSWORD_HASH_ITERATIONS", "1000")  # production default is 600k
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("EMBEDDING_PROVIDER", "hashing")  # deterministic and offline; one test exercises fastembed
os.environ.setdefault("STORAGE_LOCAL_DIR", os.path.join(_tmp_dir, "documents"))


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


# Demo personas from app/db/seed.py
PERSONAS = {
    "admin": ("admin@talentmatch.ai", "admin123"),              # SUPER_ADMIN
    "anthropic": ("recruiter@anthropic.com", "anthropic123"),   # EMPLOYER_ADMIN, org_anthropic (job_001)
    "stripe": ("recruiter@stripe.com", "stripe123"),            # EMPLOYER_ADMIN, org_stripe (job_003)
    "aarav": ("aarav@stanford.edu", "aarav123"),                # CANDIDATE, cand_001
    "elena": ("elena@cmu.edu", "elena123"),                     # CANDIDATE, cand_002
}

_token_cache = {}


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


@pytest.fixture(scope="session")
def auth(client):
    """auth("anthropic") -> Authorization headers for that demo persona."""
    def headers_for(persona: str) -> dict:
        if persona not in _token_cache:
            email, password = PERSONAS[persona]
            res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
            assert res.status_code == 200, res.text
            _token_cache[persona] = res.json()["access_token"]
        return {"Authorization": f"Bearer {_token_cache[persona]}"}
    return headers_for
