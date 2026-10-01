"""Job requisition management: create, edit, lifecycle, duplicate, limits, normalized skills."""
import contextlib
import uuid

from app.core.database import SessionLocal
from app.models.db_models import Job, JobSkill, Organization, OutboxEvent


def _job_payload(**overrides):
    payload = {
        "title": f"Platform Engineer {uuid.uuid4().hex[:4]}",
        "department": "Infrastructure",
        "description": "Build and run our platform.",
        "required_skills": ["Kubernetes", "Go", "kubernetes"],
        "preferred_skills": ["Terraform", "Go"],
        "min_experience_years": 4,
        "max_experience_years": 8,
        "location": "Remote",
        "workplace_type": "remote",
        "employment_type": "Full-time",
        "openings": 2,
        "salary_min": 150000,
        "salary_max": 190000,
    }
    payload.update(overrides)
    return payload


def _create(client, headers, **overrides):
    res = client.post("/api/v1/jobs", headers=headers, json=_job_payload(**overrides))
    assert res.status_code == 200, res.text
    return res.json()


@contextlib.contextmanager
def org_limit(org_id, max_active_jobs):
    with SessionLocal() as db:
        org = db.get(Organization, org_id)
        original, org.max_active_jobs = org.max_active_jobs, max_active_jobs
        db.commit()
    try:
        yield
    finally:
        with SessionLocal() as db:
            db.get(Organization, org_id).max_active_jobs = original
            db.commit()


def test_create_draft_normalizes_fields_and_skills(client, auth):
    job = _create(client, auth("stripe"), status="Draft")
    assert job["status"] == "Draft" and job["published_at"] is None
    assert job["workplace_type"] == "Remote"
    assert job["required_skills"] == ["Kubernetes", "Go"]          # de-duplicated, case-insensitive
    assert job["preferred_skills"] == ["Terraform"]                # required wins over preferred
    assert job["openings"] == 2 and job["max_experience_years"] == 8
    with SessionLocal() as db:
        links = db.query(JobSkill).filter(JobSkill.job_id == job["id"]).all()
        assert sorted((l.skill.name, l.importance) for l in links) == [
            ("Go", "required"), ("Kubernetes", "required"), ("Terraform", "preferred")]


def test_full_lifecycle(client, auth):
    h = auth("stripe")
    job = _create(client, h, status="Draft")
    url = f"/api/v1/jobs/{job['id']}"

    # Drafts are not on the public board
    assert client.get(url).status_code == 404

    assert client.post(f"{url}/publish", headers=h).json()["status"] == "Active"
    assert client.get(url).status_code == 200
    assert client.post(f"{url}/pause", headers=h).json()["status"] == "Paused"
    assert client.get(url).status_code == 404
    closed = client.post(f"{url}/close", headers=h).json()
    assert closed["status"] == "Closed" and closed["closed_at"]
    reopened = client.post(f"{url}/publish", headers=h).json()
    assert reopened["status"] == "Active" and reopened["closed_at"] is None

    # Active jobs must be closed before archiving
    res = client.post(f"{url}/archive", headers=h)
    assert res.status_code == 409 and "Close it first" in res.json()["detail"]
    client.post(f"{url}/close", headers=h)
    assert client.post(f"{url}/archive", headers=h).json()["status"] == "Archived"

    # Archived jobs are read-only and can't be republished
    assert client.patch(url, headers=h, json={"title": "Edited"}).status_code == 409
    assert client.post(f"{url}/publish", headers=h).status_code == 409

    with SessionLocal() as db:
        types = [e.type for e in db.query(OutboxEvent).filter(OutboxEvent.payload_json.like(f'%{job["id"]}%')).order_by(OutboxEvent.created_at)]
    assert types == ["job.created", "job.published", "job.paused", "job.closed", "job.published", "job.closed", "job.archived"]


def test_edit_is_partial_and_validated(client, auth):
    h = auth("stripe")
    job = _create(client, h)
    url = f"/api/v1/jobs/{job['id']}"

    res = client.patch(url, headers=h, json={"title": "Senior Platform Engineer", "required_skills": ["Rust"]})
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "Senior Platform Engineer"
    assert body["required_skills"] == ["Rust"]
    assert body["preferred_skills"] == ["Terraform"]  # untouched
    assert body["salary_max"] == 190000               # untouched

    assert client.patch(url, headers=h, json={"salary_min": 300000}).status_code == 422
    assert client.patch(url, headers=h, json={"workplace_type": "Moon"}).status_code == 422
    assert client.patch(url, headers=h, json={"openings": 0}).status_code == 422


def test_duplicate_creates_independent_draft(client, auth):
    h = auth("stripe")
    job = _create(client, h)
    res = client.post(f"/api/v1/jobs/{job['id']}/duplicate", headers=h)
    assert res.status_code == 201
    copy = res.json()
    assert copy["id"] != job["id"] and copy["status"] == "Draft"
    assert copy["title"].endswith("(copy)") and copy["applicants_count"] == 0
    assert copy["required_skills"] == job["required_skills"]


def test_active_job_limit_is_enforced(client, auth):
    h = auth("stripe")
    with SessionLocal() as db:
        active = db.query(Job).filter(Job.organization_id == "org_stripe", Job.status == "Active").count()
    with org_limit("org_stripe", active):
        res = client.post("/api/v1/jobs", headers=h, json=_job_payload())
        assert res.status_code == 402
        draft = _create(client, h, status="Draft")  # drafts don't count
        assert client.post(f"/api/v1/jobs/{draft['id']}/publish", headers=h).status_code == 402


def test_other_orgs_and_candidates_cannot_manage_jobs(client, auth):
    job = _create(client, auth("stripe"))
    url = f"/api/v1/jobs/{job['id']}"
    for persona in ("anthropic", "aarav"):
        h = auth(persona)
        assert client.patch(url, headers=h, json={"title": "Hijacked"}).status_code in (403, 404)
        assert client.post(f"{url}/close", headers=h).status_code in (403, 404)
        assert client.post(f"{url}/duplicate", headers=h).status_code in (403, 404)
    assert client.post(f"{url}/explode", headers=auth("stripe")).status_code == 422


def test_job_search_filters(client, auth):
    h = auth("stripe")
    marker = uuid.uuid4().hex[:6]
    _create(client, h, title=f"Searchable {marker} Engineer", department="Payments")
    found = client.get("/api/v1/jobs", headers=h, params={"q": marker}).json()
    assert [j["title"] for j in found] == [f"Searchable {marker} Engineer"]
    assert client.get("/api/v1/jobs", headers=h, params={"q": marker, "department": "Nope"}).json() == []
