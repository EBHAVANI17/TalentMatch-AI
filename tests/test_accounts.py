"""Account lifecycle: sessions, email verification, password reset, invitations."""
import re
import uuid

import pytest

from app.adapters.email import get_email_sender
from app.core import security
from app.core.database import SessionLocal
from app.models.db_models import Organization, User


def _outbox():
    return get_email_sender().outbox


def _token_from_last_email(to: str, tag: str) -> str:
    message = next(m for m in reversed(_outbox()) if m.to == to and tag in m.tags)
    return re.search(r"token=([A-Za-z0-9_\-]+)", message.text).group(1)


def _unique_email(prefix: str) -> str:
    return f"{prefix}.{uuid.uuid4().hex[:8]}@example.com"


def _register_employer(client, email=None, password="correct-horse-1"):
    email = email or _unique_email("founder")
    res = client.post("/api/v1/auth/register/employer", json={
        "email": email, "password": password, "full_name": "Founder Person",
        "company_name": f"Acme {uuid.uuid4().hex[:4]}", "company_domain": f"{uuid.uuid4().hex[:8]}.example.com",
    })
    assert res.status_code == 200, res.text
    return email, res.json()


def _login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


# ---------------------------------------------------------------- sessions
def test_login_returns_refresh_token_that_rotates(client):
    res = _login(client, "elena@cmu.edu", "elena123").json()
    assert res["refresh_token"] and res["expires_in"] > 0

    first = res["refresh_token"]
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert rotated.status_code == 200
    second = rotated.json()["refresh_token"]
    assert second != first
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {rotated.json()['access_token']}"}).status_code == 200


def test_refresh_token_replay_revokes_the_session(client):
    first = _login(client, "elena@cmu.edu", "elena123").json()["refresh_token"]
    second = client.post("/api/v1/auth/refresh", json={"refresh_token": first}).json()["refresh_token"]

    # Re-using the already-rotated token is treated as theft...
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first}).status_code == 401
    # ...so the legitimate newer token is revoked too.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": second}).status_code == 401


def test_logout_revokes_refresh_tokens(client):
    session = _login(client, "elena@cmu.edu", "elena123").json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": session["refresh_token"]}).status_code == 401


def test_garbage_refresh_token_is_rejected(client):
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": "nope"}).status_code == 401


# ---------------------------------------------------------------- passwords
def test_legacy_password_hash_is_upgraded_on_login(client):
    email = _unique_email("legacy")
    legacy_hash = "abcd1234$" + security._pbkdf2("legacy-pass-1", "abcd1234", security.LEGACY_ITERATIONS)
    with SessionLocal() as db:
        db.add(User(id=f"usr_{uuid.uuid4().hex[:8]}", email=email, hashed_password=legacy_hash,
                    full_name="Legacy User", role="CANDIDATE"))
        db.commit()

    assert _login(client, email, "legacy-pass-1").status_code == 200
    with SessionLocal() as db:
        stored = db.query(User).filter(User.email == email).one().hashed_password
    assert stored.startswith("pbkdf2_sha256$")
    assert security.verify_password("legacy-pass-1", stored)
    assert _login(client, email, "legacy-pass-1").status_code == 200


def test_short_passwords_are_rejected(client):
    res = client.post("/api/v1/auth/register/candidate", json={
        "email": _unique_email("short"), "password": "abc", "full_name": "Shorty",
    })
    assert res.status_code == 422


# ---------------------------------------------------------------- sign-up & verification
def test_employer_signup_starts_on_free_plan_and_unverified(client):
    email, body = _register_employer(client)
    assert body["user"]["email_verified"] is False
    with SessionLocal() as db:
        org = db.get(Organization, body["user"]["organization_id"])
        assert org.plan_tier == "Free Starter"
        assert org.max_recruiter_seats == 1

    token = _token_from_last_email(email, "email_verify")
    verified = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verified.status_code == 200 and verified.json()["email_verified"] is True
    # single use
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400


def test_duplicate_company_domain_is_rejected(client):
    domain = f"{uuid.uuid4().hex[:8]}.example.com"
    payload = {"password": "correct-horse-1", "full_name": "A", "company_name": "Dup", "company_domain": domain}
    assert client.post("/api/v1/auth/register/employer", json={**payload, "email": _unique_email("a")}).status_code == 200
    assert client.post("/api/v1/auth/register/employer", json={**payload, "email": _unique_email("b")}).status_code == 400


def test_unverified_login_blocked_when_verification_required(client, monkeypatch):
    email, _ = _register_employer(client)
    monkeypatch.setattr("app.api.auth.settings.require_email_verification", True)
    assert _login(client, email, "correct-horse-1").status_code == 403


# ---------------------------------------------------------------- password reset
def test_forgot_password_does_not_reveal_accounts(client):
    sent_before = len(_outbox())
    known = client.post("/api/v1/auth/forgot-password", json={"email": "marcus@berkeley.edu"})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert len(_outbox()) == sent_before + 1


def test_password_reset_flow(client):
    email, _ = _register_employer(client, password="original-pass-1")
    old_refresh = _login(client, email, "original-pass-1").json()["refresh_token"]

    client.post("/api/v1/auth/forgot-password", json={"email": email})
    token = _token_from_last_email(email, "password_reset")
    assert client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "x"}).status_code == 422
    assert client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "brand-new-pass-2"}).status_code == 200

    assert _login(client, email, "original-pass-1").status_code == 401
    assert _login(client, email, "brand-new-pass-2").status_code == 200
    # token is single-use and old sessions are gone
    assert client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "again-pass-3"}).status_code == 400
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh}).status_code == 401


# ---------------------------------------------------------------- invitations
def test_invitation_flow(client, auth):
    admin = auth("anthropic")
    email = _unique_email("teammate")
    res = client.post("/api/v1/organizations/org_anthropic/invitations", headers=admin,
                      json={"email": email, "role": "RECRUITER"})
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "pending"

    token = _token_from_last_email(email, "invitation")
    accepted = client.post("/api/v1/auth/accept-invitation",
                           json={"token": token, "full_name": "New Recruiter", "password": "welcome-aboard-1"})
    assert accepted.status_code == 200
    user = accepted.json()["user"]
    assert user["organization_id"] == "org_anthropic" and user["role"] == "RECRUITER"
    assert user["email_verified"] is True

    # The new recruiter works inside their org...
    recruiter = {"Authorization": f"Bearer {accepted.json()['access_token']}"}
    jobs = client.get("/api/v1/jobs", headers=recruiter).json()
    assert jobs and {j["organization_id"] for j in jobs} == {"org_anthropic"}
    # ...but is not an org admin, so cannot invite others
    assert client.post("/api/v1/organizations/org_anthropic/invitations", headers=recruiter,
                       json={"email": _unique_email("x"), "role": "RECRUITER"}).status_code == 403
    # and the link cannot be reused
    assert client.post("/api/v1/auth/accept-invitation",
                       json={"token": token, "full_name": "Again", "password": "welcome-aboard-1"}).status_code == 400


def test_invitation_rules(client, auth):
    admin = auth("anthropic")
    url = "/api/v1/organizations/org_anthropic/invitations"
    assert client.post(url, headers=admin, json={"email": _unique_email("r"), "role": "SUPER_ADMIN"}).status_code == 422
    assert client.post(url, headers=admin, json={"email": "elena@cmu.edu", "role": "RECRUITER"}).status_code == 409
    # Other organizations cannot see or create invitations here
    assert client.get(url, headers=auth("stripe")).status_code == 404
    assert client.post(url, headers=auth("stripe"), json={"email": _unique_email("s"), "role": "RECRUITER"}).status_code == 404


def test_revoked_invitation_cannot_be_accepted(client, auth):
    admin = auth("anthropic")
    email = _unique_email("revoked")
    inv = client.post("/api/v1/organizations/org_anthropic/invitations", headers=admin,
                      json={"email": email, "role": "HIRING_MANAGER"}).json()
    token = _token_from_last_email(email, "invitation")
    assert client.delete(f"/api/v1/organizations/org_anthropic/invitations/{inv['id']}", headers=admin).json()["status"] == "revoked"
    assert client.post("/api/v1/auth/accept-invitation",
                       json={"token": token, "full_name": "Late", "password": "too-late-pass-1"}).status_code == 400


def test_seat_limit_blocks_invites(client):
    # Free plan = 1 seat, already used by the founder
    _, body = _register_employer(client)
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    org_id = body["user"]["organization_id"]
    res = client.post(f"/api/v1/organizations/{org_id}/invitations", headers=headers,
                      json={"email": _unique_email("blocked"), "role": "RECRUITER"})
    assert res.status_code == 402


# ---------------------------------------------------------------- public config
def test_public_config(client):
    res = client.get("/api/v1/config/public")
    assert res.status_code == 200
    body = res.json()
    assert body["demo_mode"] is True
    assert "jwt" not in str(body).lower() and "secret" not in str(body).lower()
