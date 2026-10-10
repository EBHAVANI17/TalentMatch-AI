"""Database engines, sessions and the tenant context used by PostgreSQL row-level security.

Roles (PostgreSQL; created by alembic 0012):
  owner                 runs migrations; owns tables and SECURITY DEFINER helpers (BYPASSRLS)
  talentmatch_app       every API request (DATABASE_URL). No BYPASSRLS, not the owner.
  talentmatch_worker    outbox and background workers (DATABASE_WORKER_URL). Can claim any
                        org's events; everything else is filtered like the app role.
  talentmatch_admin     BYPASSRLS (DATABASE_ADMIN_URL). Used ONLY by: requests from a verified
                        platform admin, startup reference data, the demo seed, and maintenance
                        commands (key rotation, backfills).

Tenant context: app.org_id / app.user_id are set with set_config(..., true), i.e. SET LOCAL,
at the start of EVERY transaction (after_begin), from session.info["tenant"]. They end with the
transaction, so a pooled connection never carries one request's tenant into another's
(safe with PgBouncer / RDS Proxy transaction pooling). Missing context = no tenant rows.
"""
import logging
from pathlib import Path
from typing import Optional

from fastapi import Request
from sqlalchemy import MetaData, create_engine, event, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

DATABASE_URL = settings.database_url
IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE and ":memory:" not in DATABASE_URL:
    # Make sure the folder for a file-based SQLite database exists.
    Path(DATABASE_URL.split("///", 1)[-1]).parent.mkdir(parents=True, exist_ok=True)


def _make_engine(url: str):
    return create_engine(
        url,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
        pool_pre_ping=not url.startswith("sqlite"),
    )


owner_engine = _make_engine(settings.database_owner_url or DATABASE_URL)
admin_engine = _make_engine(settings.database_admin_url or DATABASE_URL)
worker_engine = _make_engine(settings.database_worker_url or DATABASE_URL)
# Emergency switch: with RLS_ENFORCED=false, request sessions run as the admin role (app checks only)
engine = _make_engine(DATABASE_URL) if (settings.rls_enforced or IS_SQLITE) else admin_engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
WorkerSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=worker_engine)
AdminSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=admin_engine, info={"admin_engine": True})

# Named constraints: required for SQLite batch migrations and predictable downgrades.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))


# ---------------------------------------------------------------------------
# Tenant context (row-level security)
# ---------------------------------------------------------------------------
def _apply_context(session: Session, connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    tenant = session.info.get("tenant") or {}
    # Always set both keys (empty = none) so nothing is inherited, even within a session.
    connection.execute(
        text("SELECT set_config('app.org_id', :org, true), set_config('app.user_id', :usr, true)"),
        {"org": tenant.get("org_id") or "", "usr": tenant.get("user_id") or ""},
    )


@event.listens_for(Session, "after_begin")
def _after_begin(session, transaction, connection):
    _apply_context(session, connection)


def set_tenant(db: Session, *, org_id: Optional[str] = None, user_id: Optional[str] = None) -> None:
    """Scope this session to an organization and/or user, now and for every later transaction."""
    db.info["tenant"] = {"org_id": org_id or "", "user_id": user_id or ""}
    if db.in_transaction():
        _apply_context(db, db.connection())


def tenant_of(db: Session) -> dict:
    return dict(db.info.get("tenant") or {})


def uses_admin_role(db: Session) -> bool:
    return bool(db.info.get("admin_engine"))


# ---------------------------------------------------------------------------
# Request sessions
# ---------------------------------------------------------------------------
def _verified_platform_admin(request: Request) -> Optional[str]:
    """User id when the request carries a valid token for an active SUPER_ADMIN, else None."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    from app.core.security import decode_access_token  # local import: security imports this module

    payload = decode_access_token(auth.split(" ", 1)[1].strip())
    if not payload or payload.get("role") != "SUPER_ADMIN" or "sub" not in payload:
        return None
    with AdminSessionLocal() as check:
        row = check.execute(
            text("SELECT 1 FROM users WHERE id = :id AND role = 'SUPER_ADMIN' AND is_active"),
            {"id": payload["sub"]},
        ).first()
    return payload["sub"] if row else None


def _audit_admin_request(db: Session, user_id: str, request: Request) -> None:
    import json
    import uuid

    from app.models.db_models import AuditLog

    db.add(AuditLog(
        id=f"audit_{uuid.uuid4().hex[:10]}", user_id=user_id, user_email="", organization_id=None,
        action="ADMIN_ENGINE_REQUEST", module="Security", entity="Request", entity_id="",
        details_json=json.dumps({"method": request.method, "path": request.url.path}), ip_address="",
    ))
    db.commit()


def get_db(request: Request):
    admin_user = None if IS_SQLITE else _verified_platform_admin(request)
    if admin_user:
        db = AdminSessionLocal()
        db.info["admin_engine"] = True
        _audit_admin_request(db, admin_user, request)
    else:
        db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_roles() -> None:
    """Startup: the request role must not bypass RLS (production refuses to start if it does)."""
    if IS_SQLITE:
        return
    if not settings.rls_enforced:
        logger.critical("RLS_ENFORCED=false: row-level security is OFF; tenant isolation relies on app checks only")
        return
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )).first()
    if row and (row[0] or row[1]):
        message = "DATABASE_URL connects as a role that bypasses row-level security (superuser or BYPASSRLS)"
        if settings.is_production:
            raise RuntimeError(message)
        logger.warning("%s; tenant isolation is not enforced by the database in this environment", message)
