"""Step 1: multi-company memberships, active organization, org hierarchy, parent/client management."""
import importlib.util
import json
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.database import AdminSessionLocal as SessionLocal, admin_engine as engine  # test setup bypasses RLS
from app.core.security import hash_password
from app.events import handlers
from app.models.db_models import AuditLog, Membership, Organization, User
from app.services import membership_service

PASSWORD = "pw-membership-1"


# ---------------------------------------------------------------- helpers

def _org(org_type="standalone", parent_id=None, seats=10, **extra) -> str:
    org_id = f"org_t{uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        db.add(Organization(id=org_id, name=f"Test {org_id}", domain=f"{org_id}.example.com", org_type=org_type,
                            parent_id=parent_id, allow_parent_access=parent_id is not None,
                            max_recruiter_seats=seats, **extra))
        db.commit()
    return org_id


def _staff(org_id, role="RECRUITER", verified=True) -> dict:
    email = f"staff.{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as db:
        user = membership_service.create_org_user(
            db, org=db.get(Organization, org_id), role=role, check_seats=False,
            email=email, hashed_password=hash_password(PASSWORD), full_name="Test Staff",
            email_verified=verified, is_active=True)
        db.commit()
        return {"id": user.id, "email": email}


def _join(user_id, org_id, role="RECRUITER", status="active"):
    with SessionLocal() as db:
        m = membership_service.add_member(db, org=db.get(Organization, org_id), user=db.get(User, user_id),
                                          role=role, actor=None, check_seats=False)
        if status != "active":
            m.status = status
        db.commit()
        return m.id


def _login(client, email) -> dict:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    return res.json()


def _h(session, org_header=None) -> dict:
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    if org_header:
        headers["X-Org-Id"] = org_header
    return headers


def _switch(client, session, org_id):
    return client.post("/api/v1/auth/switch-org", json={"organization_id": org_id}, headers=_h(session))


def _membership_of(user_id, org_id) -> Membership:
    with SessionLocal() as db:
        m = db.query(Membership).filter(Membership.user_id == user_id, Membership.organization_id == org_id).one()
        db.expunge(m)
        return m


# ---------------------------------------------------------------- active organization

def test_user_in_two_orgs_sees_only_the_active_orgs_data(client):
    person = _staff("org_anthropic")
    _join(person["id"], "org_stripe")
    a = _login(client, person["email"])
    assert a["user"]["organization_id"] == "org_anthropic" and a["user"]["memberships_count"] == 2

    jobs = client.get("/api/v1/jobs", headers=_h(a)).json()
    assert {j["organization_id"] for j in jobs} == {"org_anthropic"}
    assert client.get("/api/v1/matching/jobs/job_001/candidates", headers=_h(a)).status_code == 200
    assert client.get("/api/v1/matching/jobs/job_003/candidates", headers=_h(a)).status_code == 404
    conv = client.post("/api/v1/copilot/messages", json={"message": "List my jobs"}, headers=_h(a)).json()["conversation_id"]

    b = _switch(client, a, "org_stripe")
    assert b.status_code == 200 and b.json()["user"]["organization_id"] == "org_stripe"
    b = b.json()
    assert {j["organization_id"] for j in client.get("/api/v1/jobs", headers=_h(b)).json()} == {"org_stripe"}
    assert client.get("/api/v1/matching/jobs/job_001/candidates", headers=_h(b)).status_code == 404
    assert client.get("/api/v1/matching/jobs/job_003/candidates", headers=_h(b)).status_code == 200
    assert client.get(f"/api/v1/copilot/conversations/{conv}", headers=_h(b)).status_code == 404

    mine = client.get("/api/v1/me/organizations", headers=_h(b)).json()
    assert {o["organization_id"]: o["is_current"] for o in mine} == {"org_anthropic": False, "org_stripe": True}


def test_switching_needs_an_active_membership_in_an_active_org(client):
    person = _staff("org_anthropic")
    suspended_org = _org()
    _join(person["id"], suspended_org)
    vercel_suspended = _join(person["id"], "org_vercel", status="suspended")
    session = _login(client, person["email"])
    assert _switch(client, session, "org_stripe").status_code == 403          # no membership
    assert _switch(client, session, "org_vercel").status_code == 403          # suspended membership
    with SessionLocal() as db:
        db.get(Organization, suspended_org).is_active = False
        db.commit()
    assert _switch(client, session, suspended_org).status_code == 403         # suspended organization
    assert vercel_suspended


def test_revoking_the_active_membership_blocks_the_next_request(client):
    person = _staff("org_anthropic")
    second = _org()
    _join(person["id"], second)
    session = _switch(client, _login(client, person["email"]), second).json()
    assert client.get("/api/v1/jobs", headers=_h(session)).status_code == 200
    with SessionLocal() as db:
        m = db.query(Membership).filter(Membership.user_id == person["id"], Membership.organization_id == second).one()
        membership_service.set_status(db, m, "suspended", actor=None)
        db.commit()
    assert client.get("/api/v1/jobs", headers=_h(session)).status_code == 403
    # and its refresh token no longer works
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": session["refresh_token"]}).status_code == 401


def test_refresh_keeps_the_active_organization(client):
    person = _staff("org_anthropic")
    _join(person["id"], "org_stripe")
    session = _switch(client, _login(client, person["email"]), "org_stripe").json()
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": session["refresh_token"]}).json()
    assert refreshed["user"]["organization_id"] == "org_stripe"
    assert client.get("/api/v1/auth/me", headers=_h(refreshed)).json()["active_organization_id"] == "org_stripe"


def test_writes_from_a_tab_showing_another_org_are_rejected(client):
    person = _staff("org_anthropic")
    _join(person["id"], "org_stripe")
    session = _switch(client, _login(client, person["email"]), "org_stripe").json()
    stale = _h(session, org_header="org_anthropic")
    assert client.get("/api/v1/jobs", headers=stale).status_code == 200  # reads are fine
    res = client.post("/api/v1/copilot/messages", json={"message": "List my jobs"}, headers=stale)
    assert res.status_code == 409 and "another tab" in res.json()["detail"]
    ok = client.post("/api/v1/copilot/messages", json={"message": "List my jobs"}, headers=_h(session, "org_stripe"))
    assert ok.status_code == 200


# ---------------------------------------------------------------- parent and client organizations

def test_parent_admin_manages_clients_but_cannot_read_their_data(client):
    parent = _org("parent")
    parent_admin = _staff(parent, role="ORG_ADMIN")
    p = _login(client, parent_admin["email"])

    created = client.post(f"/api/v1/organizations/{parent}/clients", headers=_h(p),
                          json={"name": "Client Co", "domain": f"{uuid.uuid4().hex[:8]}.client.example.com"})
    assert created.status_code == 201, created.text
    client_org = created.json()["id"]
    assert created.json()["org_type"] == "client" and created.json()["allow_parent_access"] is True
    assert [c["id"] for c in client.get(f"/api/v1/organizations/{parent}/clients", headers=_h(p)).json()] == [client_org]

    # The parent admin adds a client admin, who sources a candidate
    client_admin = _staff("org_anthropic", role="ORG_ADMIN")  # an existing account elsewhere
    add = client.post(f"/api/v1/organizations/{client_org}/memberships", headers=_h(p),
                      json={"email": client_admin["email"], "role": "ORG_ADMIN"})
    assert add.status_code == 201, add.text
    c = _switch(client, _login(client, client_admin["email"]), client_org).json()
    cand = client.post("/api/v1/candidates", headers=_h(c), json={
        "full_name": "Client Secret", "email": f"{uuid.uuid4().hex[:8]}@example.com", "title": "Engineer"})
    assert cand.status_code == 201, cand.text
    cand_id = cand.json()["id"]

    # Managing members is not data access
    assert client.get(f"/api/v1/candidates/{cand_id}", headers=_h(p)).status_code == 404
    assert _switch(client, p, client_org).status_code == 403

    # Adding themselves is allowed (and audited); then they can switch in
    me = client.post(f"/api/v1/organizations/{client_org}/memberships", headers=_h(p),
                     json={"email": parent_admin["email"], "role": "RECRUITER"})
    assert me.status_code == 201
    with SessionLocal() as db:
        audit = db.query(AuditLog).filter(AuditLog.entity_id == me.json()["id"], AuditLog.action == "MEMBERSHIP_CREATED").one()
        details = json.loads(audit.details_json)
        assert details["via_parent"] is True and details["self_added"] is True and audit.user_id == parent_admin["id"]
    inside = _switch(client, p, client_org)
    assert inside.status_code == 200
    assert client.get(f"/api/v1/candidates/{cand_id}", headers=_h(inside.json())).status_code == 200


def test_client_can_turn_off_parent_access(client):
    parent = _org("parent")
    client_org = _org("client", parent_id=parent)
    parent_admin = _staff(parent, role="ORG_ADMIN")
    client_admin = _staff(client_org, role="ORG_ADMIN")
    p, c = _login(client, parent_admin["email"]), _login(client, client_admin["email"])
    url = f"/api/v1/organizations/{client_org}"

    # Only the client (or a platform admin) controls the setting
    assert client.patch(url, headers=_h(p), json={"allow_parent_access": True}).status_code == 404
    assert client.patch(url, headers=_h(c), json={"allow_parent_access": False}).status_code == 200
    res = client.get(f"{url}/memberships", headers=_h(p))
    assert res.status_code == 403 and "doesn't allow" in res.json()["detail"]
    assert client.get(f"{url}/memberships", headers=_h(c)).status_code == 200


def test_parent_admin_audit_covers_changes_and_removals(client):
    parent = _org("parent")
    client_org = _org("client", parent_id=parent)
    _staff(client_org, role="ORG_ADMIN")
    worker = _staff(client_org, role="RECRUITER")
    p = _login(client, _staff(parent, role="ORG_ADMIN")["email"])
    m_id = _membership_of(worker["id"], client_org).id
    url = f"/api/v1/organizations/{client_org}/memberships/{m_id}"
    assert client.patch(url, headers=_h(p), json={"role": "HIRING_MANAGER"}).status_code == 200
    assert client.delete(url, headers=_h(p)).status_code == 204
    with SessionLocal() as db:
        actions = {a.action: json.loads(a.details_json) for a in db.query(AuditLog).filter(AuditLog.entity_id == m_id)}
    assert actions["MEMBERSHIP_ROLE_CHANGED"]["via_parent"] is True
    assert actions["MEMBERSHIP_REMOVED"]["via_parent"] is True


def test_non_parent_admins_cannot_manage_clients(client):
    parent = _org("parent")
    client_org = _org("client", parent_id=parent)
    recruiter = _login(client, _staff(parent, role="RECRUITER")["email"])
    assert client.get(f"/api/v1/organizations/{parent}/clients", headers=_h(recruiter)).status_code == 403
    assert client.get(f"/api/v1/organizations/{client_org}/memberships", headers=_h(recruiter)).status_code == 404
    # A client's admin can't manage the parent or a sibling
    sibling = _org("client", parent_id=parent)
    c = _login(client, _staff(client_org, role="ORG_ADMIN")["email"])
    assert client.get(f"/api/v1/organizations/{parent}/memberships", headers=_h(c)).status_code == 404
    assert client.get(f"/api/v1/organizations/{sibling}/memberships", headers=_h(c)).status_code == 404


def test_hierarchy_is_one_level_deep(client):
    standalone = _org()
    parent = _org("parent")
    client_org = _org("client", parent_id=parent)
    s_admin = _login(client, _staff(standalone, role="ORG_ADMIN")["email"])
    c_admin = _login(client, _staff(client_org, role="ORG_ADMIN")["email"])
    body = {"name": "Nope", "domain": f"{uuid.uuid4().hex[:8]}.example.com"}
    assert client.post(f"/api/v1/organizations/{standalone}/clients", headers=_h(s_admin), json=body).status_code == 403
    assert client.post(f"/api/v1/organizations/{client_org}/clients", headers=_h(c_admin), json=body).status_code == 403
    with SessionLocal() as db:
        with pytest.raises(Exception) as exc:
            membership_service.create_client_org(db, parent=db.get(Organization, client_org),
                                                 actor=db.get(User, "usr_admin_root") or User(id="x", email="x"),
                                                 name="Deep", domain=f"{uuid.uuid4().hex[:8]}.example.com")
        assert getattr(exc.value, "status_code", None) == 409
        with pytest.raises(Exception) as exc:
            membership_service.set_org_type(db, db.get(Organization, client_org), "parent")
        assert getattr(exc.value, "status_code", None) == 409


# ---------------------------------------------------------------- membership rules

def test_last_active_admin_cannot_be_removed_suspended_or_demoted(client):
    org = _org()
    admin = _staff(org, role="ORG_ADMIN")
    a = _login(client, admin["email"])
    m_id = _membership_of(admin["id"], org).id
    url = f"/api/v1/organizations/{org}/memberships/{m_id}"
    for res in (client.patch(url, headers=_h(a), json={"role": "RECRUITER"}),
                client.patch(url, headers=_h(a), json={"status": "suspended"}),
                client.delete(url, headers=_h(a))):
        assert res.status_code == 409 and "last active admin" in res.json()["detail"]
    # With a second admin, the first can step down
    second = _staff("org_anthropic", role="ORG_ADMIN")
    assert client.post(f"/api/v1/organizations/{org}/memberships", headers=_h(a),
                       json={"email": second["email"], "role": "ORG_ADMIN"}).status_code == 201
    assert client.patch(url, headers=_h(a), json={"role": "RECRUITER"}).status_code == 200


def test_seats_are_per_organization(client):
    org = _org(seats=2)
    admin = _staff(org, role="ORG_ADMIN")
    a = _login(client, admin["email"])
    url = f"/api/v1/organizations/{org}/memberships"
    assert client.post(url, headers=_h(a), json={"email": _staff("org_anthropic")["email"], "role": "RECRUITER"}).status_code == 201
    full = client.post(url, headers=_h(a), json={"email": _staff("org_anthropic")["email"], "role": "RECRUITER"})
    assert full.status_code == 402
    with SessionLocal() as db:
        assert membership_service.seats_in_use(db, org) == 2


def test_default_org_moves_to_the_oldest_active_membership(client):
    person = _staff("org_anthropic")
    _join(person["id"], "org_stripe")
    _join(person["id"], "org_vercel")
    with SessionLocal() as db:
        m = db.query(Membership).filter(Membership.user_id == person["id"], Membership.organization_id == "org_anthropic").one()
        membership_service.set_status(db, m, "suspended", actor=None)
        db.commit()
        assert db.get(User, person["id"]).organization_id == "org_stripe"
    assert _login(client, person["email"])["user"]["organization_id"] == "org_stripe"


def test_platform_accounts_cannot_join_organizations(client, auth):
    res = client.post("/api/v1/organizations/org_anthropic/memberships", headers=auth("anthropic"),
                      json={"email": "aarav@stanford.edu", "role": "RECRUITER"})
    assert res.status_code == 409


# ---------------------------------------------------------------- invitations for existing accounts

def _invite(client, auth, email):
    from app.adapters.email import get_email_sender
    import re
    assert client.post("/api/v1/organizations/org_anthropic/invitations", headers=auth("anthropic"),
                       json={"email": email, "role": "RECRUITER"}).status_code == 201
    message = next(m for m in reversed(get_email_sender().outbox) if m.to == email)
    return re.search(r"token=([A-Za-z0-9_\-]+)", message.text).group(1)


def test_existing_account_accepts_invitation_while_signed_in(client, auth):
    person = _staff(_org())
    token = _invite(client, auth, person["email"])
    assert client.post("/api/v1/auth/accept-invitation", json={"token": token}).status_code == 401
    other = _login(client, _staff(_org())["email"])
    assert client.post("/api/v1/auth/accept-invitation", json={"token": token}, headers=_h(other)).status_code == 403
    me = _login(client, person["email"])
    accepted = client.post("/api/v1/auth/accept-invitation", json={"token": token}, headers=_h(me))
    assert accepted.status_code == 200 and accepted.json()["user"]["organization_id"] == "org_anthropic"
    assert client.post("/api/v1/auth/accept-invitation", json={"token": token}, headers=_h(me)).status_code == 400


def test_unverified_account_cannot_accept_invitation(client, auth):
    person = _staff(_org(), verified=False)
    token = _invite(client, auth, person["email"])
    res = client.post("/api/v1/auth/accept-invitation", json={"token": token}, headers=_h(_login(client, person["email"])))
    assert res.status_code == 403 and "Verify" in res.json()["detail"]


# ---------------------------------------------------------------- events, deletion, migration

def test_event_recipients_come_from_active_memberships():
    org = _org()
    active = _staff(org)
    suspended = _staff(org)
    with SessionLocal() as db:
        m = db.query(Membership).filter(Membership.user_id == suspended["id"]).one()
        m.status = "suspended"
        db.commit()
        ids = {u.id for u in handlers._hiring_team(db, org, None)}
    assert active["id"] in ids and suspended["id"] not in ids


def test_soft_deleted_org_keeps_memberships_and_blocks_access(client, auth):
    org = _org()
    person = _staff(org)
    _join(person["id"], "org_anthropic")
    assert client.delete(f"/api/v1/organizations/{org}", headers=auth("admin")).status_code == 200
    with SessionLocal() as db:
        assert db.get(Organization, org).status == "deleted"
        assert db.query(Membership).filter(Membership.organization_id == org).count() == 1
        assert db.get(User, person["id"]).organization_id == "org_anthropic"
    session = _login(client, person["email"])
    assert _switch(client, session, org).status_code == 403


@pytest.mark.skipif(engine.dialect.name == "sqlite", reason="SQLite doesn't enforce foreign keys")
def test_organizations_with_memberships_cannot_be_hard_deleted():
    org = _org()
    _staff(org)
    with engine.connect() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": org})
        conn.rollback()


def test_membership_backfill_is_idempotent():
    path = os.path.join(os.path.dirname(__file__), "..", "backend", "alembic", "versions",
                        "20261007_0010_memberships_and_org_hierarchy.py")
    spec = importlib.util.spec_from_file_location("m0010", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as conn:
        module.backfill_memberships(conn)
        assert module.backfill_memberships(conn) == 0


def test_client_creation_counts_against_the_parents_plan(client):
    parent = _org("parent", max_client_orgs=2)
    p = _login(client, _staff(parent, role="ORG_ADMIN")["email"])
    url = f"/api/v1/organizations/{parent}/clients"
    new = lambda: {"name": "C", "domain": f"{uuid.uuid4().hex[:8]}.example.com"}  # noqa: E731
    assert client.post(url, headers=_h(p), json=new()).status_code == 201
    second = client.post(url, headers=_h(p), json=new())
    assert second.status_code == 201
    full = client.post(url, headers=_h(p), json=new())
    assert full.status_code == 409 and "limit reached (2)" in full.json()["detail"]
    # A deleted client frees its slot; parents can't raise their own limit
    assert client.patch(f"/api/v1/organizations/{parent}", headers=_h(p), json={"max_client_orgs": 50}).status_code == 403
    with SessionLocal() as db:
        db.get(Organization, second.json()["id"]).status = "deleted"
        db.commit()
    assert client.post(url, headers=_h(p), json=new()).status_code == 201


def test_demo_data_has_a_person_in_two_organizations(client):
    session = _switch(client, client.post("/api/v1/auth/login", json={"email": "priya@talentmatch.ai", "password": "priya123"}).json(),
                      "org_stripe")
    assert session.status_code == 200 and session.json()["user"]["role"] == "HIRING_MANAGER"
