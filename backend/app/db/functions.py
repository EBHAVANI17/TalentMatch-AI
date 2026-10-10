"""Calls to the SECURITY DEFINER functions created by alembic 0012, with plain-SQL equivalents
for SQLite (no row-level security there) and for platform-admin sessions (BYPASSRLS).

Use these instead of querying users/user_tokens/invitations by email or token hash, reading
password hashes, or changing another user's default-organization mirror.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import uses_admin_role


def _rls(db: Session) -> bool:
    """True when the session is subject to row-level security (PostgreSQL, request/worker role)."""
    return db.get_bind().dialect.name == "postgresql" and not uses_admin_role(db)


def _pg(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _row(db: Session, sql: str, params: dict) -> Optional[dict]:
    row = db.execute(text(sql), params).mappings().first()
    if not row:
        return None
    out = dict(row)
    for key in ("expires_at", "used_at"):  # SQLite returns raw SQL timestamps as text
        if isinstance(out.get(key), str):
            out[key] = datetime.fromisoformat(out[key])
    return out


# ---------------------------------------------------------------------------
# Lookups before anyone is signed in
# ---------------------------------------------------------------------------
def user_by_email(db: Session, email: str) -> Optional[dict]:
    """{id, hashed_password, is_active, email_verified} or None."""
    if _pg(db):
        return _row(db, "SELECT * FROM auth_user_by_email(:e)", {"e": email})
    return _row(db, "SELECT id, hashed_password, is_active, email_verified FROM users WHERE email = :e", {"e": email})


def account_by_email(db: Session, email: str) -> Optional[dict]:
    """{id, role, is_active} for adding an existing account to an organization (no secrets)."""
    if _pg(db):
        return _row(db, "SELECT * FROM auth_account_by_email(:e)", {"e": email})
    return _row(db, "SELECT id, role, is_active FROM users WHERE email = :e", {"e": email})


def email_exists(db: Session, email: str) -> bool:
    if _pg(db):
        return bool(db.execute(text("SELECT auth_email_exists(:e)"), {"e": email}).scalar())
    return db.execute(text("SELECT 1 FROM users WHERE email = :e"), {"e": email}).first() is not None


def domain_exists(db: Session, domain: str) -> bool:
    if _pg(db):
        return bool(db.execute(text("SELECT auth_domain_exists(:d)"), {"d": domain}).scalar())
    return db.execute(text("SELECT 1 FROM organizations WHERE domain = :d"), {"d": domain}).first() is not None


def token_owner(db: Session, token_hash: str, purpose: str) -> Optional[dict]:
    """{id, user_id, expires_at, used_at, organization_id} or None."""
    if _pg(db):
        return _row(db, "SELECT * FROM auth_token_owner(:h, :p)", {"h": token_hash, "p": purpose})
    return _row(db, "SELECT id, user_id, expires_at, used_at, organization_id FROM user_tokens "
                    "WHERE token_hash = :h AND purpose = :p", {"h": token_hash, "p": purpose})


def invitation_by_hash(db: Session, token_hash: str) -> Optional[dict]:
    """{id, organization_id, email, role, status, expires_at} or None."""
    if _pg(db):
        return _row(db, "SELECT * FROM auth_invitation(:h)", {"h": token_hash})
    return _row(db, "SELECT id, organization_id, email, role, status, expires_at FROM invitations "
                    "WHERE token_hash = :h", {"h": token_hash})


# ---------------------------------------------------------------------------
# Narrow writes
# ---------------------------------------------------------------------------
def set_password_hash(db: Session, user_id: str, hashed: str) -> None:
    """Only for the current user (app.user_id) under RLS."""
    if _rls(db):
        db.execute(text("SELECT tm_set_password_hash(:u, :h)"), {"u": user_id, "h": hashed})
    else:
        db.execute(text("UPDATE users SET hashed_password = :h WHERE id = :u"), {"u": user_id, "h": hashed})


def create_staff_user(db: Session, *, id: str, email: str, hashed_password: str, full_name: str, role: str,
                      organization_id: str, email_verified: bool, avatar_url: str = "") -> None:
    """Staff accounts can't be inserted directly under RLS (only candidate rows can)."""
    if _rls(db):
        db.execute(text("SELECT tm_create_staff_user(:i, :e, :h, :n, :r, :o, :v, :a)"), {
            "i": id, "e": email, "h": hashed_password, "n": full_name, "r": role, "o": organization_id,
            "v": email_verified, "a": avatar_url})
    else:
        db.execute(text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, organization_id, avatar_url, status, "
            "is_active, email_verified, created_at, updated_at) VALUES (:i, :e, :h, :n, :r, :o, :a, 'Active', :t, :v, :now, :now)"),
            {"i": id, "e": email, "h": hashed_password, "n": full_name, "r": role, "o": organization_id,
             "a": avatar_url, "t": True, "v": email_verified, "now": datetime.utcnow()})


def sync_default_org(db: Session, user_id: str) -> bool:
    """Recompute another user's default-organization mirror in the database. Returns False when the
    caller should do it in Python instead (SQLite, platform-admin sessions)."""
    if not _rls(db):
        return False
    db.flush()
    db.execute(text("SELECT tm_sync_default_org(:u)"), {"u": user_id})
    return True


def revoke_org_sessions(db: Session, user_id: str, org_id: str) -> bool:
    if not _rls(db):
        return False
    db.execute(text("SELECT tm_revoke_org_sessions(:u, :o)"), {"u": user_id, "o": org_id})
    return True


def refresh_applicants_count(db: Session, job_id: str) -> None:
    db.flush()
    if _rls(db):
        db.execute(text("SELECT tm_refresh_applicants_count(:j)"), {"j": job_id})
    else:
        db.execute(text("UPDATE jobs SET applicants_count = (SELECT COUNT(*) FROM applications WHERE job_id = :j) "
                        "WHERE id = :j"), {"j": job_id})


def user_ai_usage_today(db: Session, user_id: str) -> int:
    if _rls(db):
        return int(db.execute(text("SELECT tm_user_ai_usage_today(:u)"), {"u": user_id}).scalar() or 0)
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return int(db.execute(text("SELECT COUNT(*) FROM ai_requests WHERE user_id = :u AND status = 'success' "
                               "AND created_at >= :s"), {"u": user_id, "s": start}).scalar() or 0)


def org_matching_weights(db: Session, org_id: str) -> str:
    """An organization's matching weights JSON, for scoring a candidate against its job."""
    if _rls(db):
        return db.execute(text("SELECT tm_org_matching_weights(:o)"), {"o": org_id}).scalar() or ""
    return db.execute(text("SELECT matching_weights_json FROM organizations WHERE id = :o"), {"o": org_id}).scalar() or ""


def notification_exists(db: Session, event_id: str, user_id: str) -> bool:
    """Dedupe across retries; the recipient's notifications aren't visible to the sender under RLS."""
    if _rls(db):
        return bool(db.execute(text("SELECT tm_notification_exists(:e, :u)"), {"e": event_id, "u": user_id}).scalar())
    return db.execute(text("SELECT 1 FROM notifications WHERE event_id = :e AND user_id = :u"),
                      {"e": event_id, "u": user_id}).first() is not None


def document_for_signed_download(db: Session, document_id: str) -> Optional[dict]:
    """{storage_key, content_type, filename}. Call ONLY after verifying the link's signature."""
    if _pg(db):
        return _row(db, "SELECT * FROM tm_document_for_signed_download(:d)", {"d": document_id})
    return _row(db, "SELECT storage_key, content_type, filename FROM documents WHERE id = :d", {"d": document_id})
