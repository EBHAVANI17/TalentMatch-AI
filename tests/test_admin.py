"""Super-admin user/organization management rules."""
import uuid

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.db_models import User


def _make_user(role="RECRUITER", org_id="org_stripe", password="pw-12345678") -> tuple:
    user_id = f"usr_adm_{uuid.uuid4().hex[:8]}"
    email = f"{user_id}@example.com"
    with SessionLocal() as db:
        db.add(User(id=user_id, email=email, full_name="Admin Test", role=role, organization_id=org_id,
                    hashed_password=hash_password(password), is_active=True, status="Active"))
        db.commit()
    return user_id, email, password


def _admin_id(client, auth) -> str:
    return client.get("/api/v1/auth/me", headers=auth("admin")).json()["id"]


def test_role_must_be_known(client, auth):
    user_id, _, _ = _make_user()
    res = client.patch(f"/api/v1/admin/users/{user_id}", json={"role": "GOD_MODE"}, headers=auth("admin"))
    assert res.status_code == 400 and "Unknown role" in res.json()["detail"]


def test_org_roles_need_an_organization_and_candidates_have_none(client, auth):
    user_id, _, _ = _make_user()
    no_org = client.patch(f"/api/v1/admin/users/{user_id}", json={"organization_id": "none"}, headers=auth("admin"))
    assert no_org.status_code == 400
    candidate_in_org = client.patch(f"/api/v1/admin/users/{user_id}", json={"role": "CANDIDATE"}, headers=auth("admin"))
    assert candidate_in_org.status_code == 400
    ok = client.patch(f"/api/v1/admin/users/{user_id}", json={"role": "HIRING_MANAGER"}, headers=auth("admin"))
    assert ok.status_code == 200 and ok.json()["role"] == "HIRING_MANAGER"


def test_admin_cannot_demote_or_suspend_themselves(client, auth):
    me = _admin_id(client, auth)
    demote = client.patch(f"/api/v1/admin/users/{me}", json={"role": "RECRUITER", "organization_id": "org_stripe"},
                          headers=auth("admin"))
    assert demote.status_code == 400
    suspend = client.patch(f"/api/v1/admin/users/{me}", json={"status": "Suspended"}, headers=auth("admin"))
    assert suspend.status_code == 400
    same_role = client.patch(f"/api/v1/admin/users/{me}", json={"role": "SUPER_ADMIN", "status": "Active"},
                             headers=auth("admin"))
    assert same_role.status_code == 200  # the legacy edit form always resends the current role


def test_suspending_a_user_ends_their_sessions(client, auth):
    user_id, email, password = _make_user()
    session = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()
    res = client.post(f"/api/v1/admin/users/{user_id}/toggle-status", headers=auth("admin"))
    assert res.status_code == 200 and res.json()["is_active"] is False
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": session["refresh_token"]})
    assert refreshed.status_code == 401
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {session['access_token']}"})
    assert me.status_code == 401


def test_admin_endpoints_require_super_admin(client, auth):
    assert client.get("/api/v1/admin/users", headers=auth("anthropic")).status_code == 403
    assert client.get("/api/v1/admin/organizations", headers=auth("anthropic")).status_code == 403


def test_org_admin_cannot_change_platform_controlled_org_fields(client, auth):
    for field, value in (("is_active", False), ("domain", "hijack.example.com"), ("status", "Suspended")):
        res = client.patch("/api/v1/organizations/org_anthropic", json={field: value}, headers=auth("anthropic"))
        assert res.status_code == 403, field
    ok = client.patch("/api/v1/organizations/org_anthropic", json={"industry": "AI Research"}, headers=auth("anthropic"))
    assert ok.status_code == 200
