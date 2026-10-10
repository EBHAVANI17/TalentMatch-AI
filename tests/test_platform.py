"""Platform-level checks: configuration safety, migrations, and API surface."""
import pytest
from fastapi.testclient import TestClient

from app.core.config import DEV_JWT_SECRET, Settings
from app.main import app

client = TestClient(app)


def test_production_refuses_insecure_defaults():
    unsafe = Settings(environment="production", jwt_secret_key=DEV_JWT_SECRET, demo_mode=True, cors_origins="*")
    with pytest.raises(RuntimeError) as exc:
        unsafe.validate_for_runtime()
    message = str(exc.value)
    assert "JWT_SECRET_KEY" in message
    assert "DATA_ENCRYPTION_KEYS" in message
    assert "DEMO_MODE" in message
    assert "CORS_ORIGINS" in message


def test_production_accepts_safe_config():
    Settings(
        environment="production",
        jwt_secret_key="x" * 48,
        data_encryption_keys="k" * 44,
        demo_mode=False,
        cors_origins="https://app.example.com",
    ).validate_for_runtime()


def test_cors_origins_parsed_from_csv():
    s = Settings(cors_origins="https://a.example.com, https://b.example.com")
    assert s.cors_origin_list == ["https://a.example.com", "https://b.example.com"]


def test_openapi_lists_each_route_once_under_api_prefix():
    paths = client.get("/openapi.json").json()["paths"]
    api_paths = [p for p in paths if p not in ("/health",)]
    assert api_paths, "expected API routes in the schema"
    assert all(p.startswith("/api/v1/") for p in api_paths)


def test_legacy_unprefixed_route_still_works():
    assert client.get("/jobs").status_code == 200


def test_database_is_at_latest_migration():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import text

    from app.core.config import BACKEND_DIR
    from app.core.database import owner_engine as engine  # alembic_version belongs to the owner

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert current == head


def test_production_requires_separate_database_roles():
    pg = Settings(environment="production", jwt_secret_key="x" * 48, data_encryption_keys="k" * 44, demo_mode=False,
                  cors_origins="https://app.example.com", database_url="postgresql+psycopg://talentmatch_app@db/tm",
                  database_owner_url="", database_admin_url="", database_worker_url="")
    with pytest.raises(RuntimeError) as exc:
        pg.validate_for_runtime()
    for name in ("DATABASE_OWNER_URL", "DATABASE_ADMIN_URL", "DATABASE_WORKER_URL"):
        assert name in str(exc.value)


def test_rls_switched_off_is_logged_loudly(monkeypatch, caplog):
    import logging

    from app.core import database

    monkeypatch.setattr(database, "IS_SQLITE", False)
    monkeypatch.setattr(database.settings, "rls_enforced", False)
    with caplog.at_level(logging.CRITICAL, logger="app.core.database"):
        database.check_database_roles()
    assert any("RLS_ENFORCED=false" in r.getMessage() for r in caplog.records)
