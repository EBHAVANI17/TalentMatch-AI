"""Cross-tenant isolation and role checks.

Seed facts used here (app/db/seed.py):
  org_anthropic owns job_001; app_001 = cand_001 (Aarav) -> job_001
  org_stripe    owns job_003; app_003 = cand_003 (Marcus) -> job_003
  org_vercel    owns job_002; app_002 = cand_002 (Elena)  -> job_002
"""
import contextlib
import json

import pytest

from app.core.database import AdminSessionLocal as SessionLocal  # test setup bypasses RLS
from app.models.db_models import CandidateProfile, Job, Notification, Organization, User


@contextlib.contextmanager
def changed(model, pk, **values):
    """Temporarily change columns on a row, restoring them afterwards."""
    with SessionLocal() as db:
        row = db.get(model, pk)
        original = {k: getattr(row, k) for k in values}
        for k, v in values.items():
            setattr(row, k, v)
        db.commit()
    try:
        yield
    finally:
        with SessionLocal() as db:
            row = db.get(model, pk)
            for k, v in original.items():
                setattr(row, k, v)
            db.commit()


@pytest.fixture
def anthropic_draft_job():
    with SessionLocal() as db:
        db.add(Job(
            id="job_draft_anthropic", organization_id="org_anthropic", title="Confidential Draft",
            description="Not yet published", status="Draft",
        ))
        db.commit()
    yield "job_draft_anthropic"
    with SessionLocal() as db:
        db.query(Job).filter(Job.id == "job_draft_anthropic").delete()
        db.commit()


# ---------------------------------------------------------------- anonymous
@pytest.mark.parametrize("method,path", [
    ("get", "/api/v1/candidates"),
    ("get", "/api/v1/candidates/cand_001"),
    ("get", "/api/v1/applications"),
    ("get", "/api/v1/notifications"),
    ("get", "/api/v1/organizations"),
    ("get", "/api/v1/users"),
    ("get", "/api/v1/admin/stats"),
    ("get", "/api/v1/admin/audit-logs"),
    ("get", "/api/v1/analytics/overview"),
    ("get", "/api/v1/recommendations/candidates-for-job/job_001"),
    ("post", "/api/v1/ai/generate-job-spec"),
    ("patch", "/api/v1/users/usr_cand_aarav/status"),
    ("patch", "/api/v1/organizations/org_anthropic"),
])
def test_anonymous_requests_are_rejected(client, method, path):
    res = getattr(client, method)(path, **({} if method == "get" else {"json": {}}))
    assert res.status_code == 401, (path, res.status_code)


def test_anonymous_sees_only_public_job_board(client, anthropic_draft_job):
    jobs = client.get("/api/v1/jobs", params={"status": "all"}).json()
    assert jobs and all(j["status"] == "Active" for j in jobs)
    assert client.get(f"/api/v1/jobs/{anthropic_draft_job}").status_code == 404


# ---------------------------------------------------------------- candidates
def test_candidate_sees_only_own_profile_and_applications(client, auth):
    h = auth("aarav")
    candidates = client.get("/api/v1/candidates", headers=h).json()
    assert [c["id"] for c in candidates] == ["cand_001"]

    apps = client.get("/api/v1/applications", headers=h).json()
    assert apps and {a["candidate_id"] for a in apps} == {"cand_001"}


def test_candidate_cannot_read_other_candidates(client, auth):
    h = auth("aarav")
    assert client.get("/api/v1/candidates/cand_002", headers=h).status_code == 404
    assert client.get("/api/v1/candidates/cand_002/dossier", headers=h).status_code == 404
    assert client.get("/api/v1/resumes/candidate/cand_002", headers=h).status_code == 404
    assert client.get("/api/v1/recommendations/jobs-for-candidate/cand_002", headers=h).status_code == 404
    assert client.get("/api/v1/applications/app_002/history", headers=h).status_code == 404


def test_candidate_cannot_apply_or_edit_as_someone_else(client, auth):
    h = auth("aarav")
    res = client.post("/api/v1/applications", headers=h, json={"job_id": "job_003", "candidate_id": "cand_002"})
    assert res.status_code == 403
    res = client.patch("/api/v1/candidates/cand_002", headers=h, json={"title": "Hacked"})
    assert res.status_code == 404
    res = client.post(
        "/api/v1/resumes/upload", headers=h,
        files={"file": ("cv.txt", b"x" * 50, "text/plain")}, data={"candidate_id": "cand_002"},
    )
    assert res.status_code == 404


def test_candidate_cannot_use_hiring_or_admin_endpoints(client, auth):
    h = auth("aarav")
    assert client.patch("/api/v1/applications/app_001/stage", headers=h, json={"stage": "Hired"}).status_code == 403
    assert client.post("/api/v1/jobs", headers=h, json={"title": "x", "description": "y"}).status_code in (403, 422)
    assert client.get("/api/v1/admin/stats", headers=h).status_code == 403
    assert client.get("/api/v1/users", headers=h).status_code == 403
    assert client.post("/api/v1/ai/autonomous-sourcing", headers=h, json={"job_id": "job_001"}).status_code == 403


def test_notifications_are_private(client, auth):
    with SessionLocal() as db:
        aarav_notif = db.query(Notification).filter(Notification.user_id == "usr_cand_aarav").first().id
    elena = auth("elena")
    assert all(n["id"] != aarav_notif for n in client.get("/api/v1/notifications", headers=elena).json())
    assert client.patch(f"/api/v1/notifications/{aarav_notif}/read", headers=elena).status_code == 404


# ---------------------------------------------------------------- organizations
def test_org_member_sees_only_own_jobs_and_applications(client, auth, anthropic_draft_job):
    h = auth("stripe")
    jobs = client.get("/api/v1/jobs", headers=h, params={"status": "all"}).json()
    assert jobs and {j["organization_id"] for j in jobs} == {"org_stripe"}
    assert client.get(f"/api/v1/jobs/{anthropic_draft_job}", headers=h).status_code == 404

    apps = client.get("/api/v1/applications", headers=h).json()
    assert apps and {a["job_id"] for a in apps} <= {"job_003"}


def test_org_member_can_see_own_draft_job(client, auth, anthropic_draft_job):
    h = auth("anthropic")
    assert client.get(f"/api/v1/jobs/{anthropic_draft_job}", headers=h).status_code == 200
    ids = [j["id"] for j in client.get("/api/v1/jobs", headers=h, params={"status": "all"}).json()]
    assert anthropic_draft_job in ids


def test_org_member_cannot_act_on_other_org_records(client, auth):
    h = auth("stripe")
    assert client.patch("/api/v1/applications/app_001/stage", headers=h, json={"stage": "Rejected"}).status_code == 404
    assert client.get("/api/v1/applications/app_001/history", headers=h).status_code == 404
    assert client.post("/api/v1/ai/auto-screen-application/app_001", headers=h).status_code == 404
    assert client.get("/api/v1/recommendations/candidates-for-job/job_001", headers=h).status_code == 404
    assert client.post(
        "/api/v1/ai/generate-outreach", headers=h, json={"candidate_id": "cand_001", "job_id": "job_001"}
    ).status_code == 404
    assert client.post("/api/v1/ai/autonomous-sourcing", headers=h, json={"job_id": "job_001"}).status_code == 404
    # Adding a candidate to another org's job is refused too
    assert client.post(
        "/api/v1/applications", headers=h, json={"job_id": "job_001", "candidate_id": "cand_004"}
    ).status_code == 404


def test_org_member_cannot_read_other_orgs_or_their_users(client, auth):
    h = auth("stripe")
    assert [o["id"] for o in client.get("/api/v1/organizations", headers=h).json()] == ["org_stripe"]
    assert client.get("/api/v1/organizations/org_anthropic", headers=h).status_code == 404
    assert client.get("/api/v1/organizations/org_anthropic/users", headers=h).status_code == 404
    assert client.get("/api/v1/users/usr_rec_anthropic", headers=h).status_code == 404
    users = client.get("/api/v1/users", headers=h, params={"organization_id": "org_anthropic"}).json()
    assert users == []


def test_org_admin_cannot_change_platform_controlled_fields(client, auth):
    h = auth("stripe")
    assert client.patch("/api/v1/organizations/org_stripe", headers=h, json={"plan_tier": "Enterprise Ultra"}).status_code == 403
    assert client.patch("/api/v1/organizations/org_stripe", headers=h, json={"monthly_ai_credits": 10**9}).status_code == 403
    assert client.patch("/api/v1/organizations/org_anthropic", headers=h, json={"name": "Pwned"}).status_code == 404
    with changed(Organization, "org_stripe", name="Stripe"):
        res = client.patch("/api/v1/organizations/org_stripe", headers=h, json={"name": "Stripe, Inc."})
        assert res.status_code == 200 and res.json()["name"] == "Stripe, Inc."


def test_role_escalation_is_blocked(client, auth):
    h = auth("stripe")
    # Not yourself, not other orgs, never SUPER_ADMIN
    assert client.patch("/api/v1/users/usr_rec_stripe/status", headers=h, json={"status": "Active", "role": "SUPER_ADMIN"}).status_code == 403
    assert client.patch("/api/v1/users/usr_rec_anthropic/status", headers=h, json={"status": "Suspended"}).status_code == 404
    assert client.patch("/api/v1/users/usr_cand_aarav/status", headers=h, json={"status": "Suspended"}).status_code == 404


def test_candidate_visibility_respects_searchable_flag(client, auth):
    # cand_004 (Sophia) has no applications to Stripe; hide her from search.
    with changed(CandidateProfile, "cand_004", is_searchable=False):
        h = auth("stripe")
        ids = [c["id"] for c in client.get("/api/v1/candidates", headers=h).json()]
        assert "cand_004" not in ids
        assert client.get("/api/v1/candidates/cand_004", headers=h).status_code == 404
        # ...but a super admin still sees her
        assert client.get("/api/v1/candidates/cand_004", headers=auth("admin")).status_code == 200


def test_applicants_remain_visible_to_their_employer_when_not_searchable(client, auth):
    # cand_003 applied to Stripe's job_003
    with changed(CandidateProfile, "cand_003", is_searchable=False):
        assert client.get("/api/v1/candidates/cand_003", headers=auth("stripe")).status_code == 200
        assert client.get("/api/v1/candidates/cand_003", headers=auth("anthropic")).status_code == 404


def test_suspended_organization_is_locked_out(client, auth):
    h = auth("stripe")
    with changed(Organization, "org_stripe", is_active=False, status="Suspended"):
        assert client.get("/api/v1/applications", headers=h).status_code == 403


def test_job_is_created_in_callers_org(client, auth):
    res = client.post("/api/v1/jobs", headers=auth("stripe"), json={
        "title": "Payments SRE", "department": "Infrastructure", "description": "Keep money moving.",
        "required_skills": ["Go"], "preferred_skills": [], "min_experience_years": 3,
        "location": "Remote", "workplace_type": "Remote", "salary_min": 1, "salary_max": 2,
        "equity": "", "required_education": "Bachelor's", "urgency": "High",
        "key_responsibilities": [], "benefits": [],
    })
    assert res.status_code == 200
    assert res.json()["organization_id"] == "org_stripe"
    with SessionLocal() as db:
        db.query(Job).filter(Job.id == res.json()["id"]).delete()
        db.commit()


def test_upload_filename_cannot_escape_storage(client, auth):
    res = client.post(
        "/api/v1/resumes/upload", headers=auth("aarav"),
        files={"file": ("../../../evil.txt", b"Python engineer with 5 years experience " * 3, "text/plain")},
        data={"candidate_id": "cand_001"},
    )
    assert res.status_code == 200
    assert res.json()["original_filename"] == "evil.txt"


def test_super_admin_sees_across_tenants(client, auth):
    h = auth("admin")
    orgs = {o["id"] for o in client.get("/api/v1/organizations", headers=h).json()}
    assert {"org_anthropic", "org_stripe"} <= orgs
    apps = {a["job_id"] for a in client.get("/api/v1/applications", headers=h).json()}
    assert {"job_001", "job_003"} <= apps
