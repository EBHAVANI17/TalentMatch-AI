"""Recruiter dashboard figures are real, tenant-scoped and consistent with the underlying records."""
from app.core.database import AdminSessionLocal as SessionLocal  # test setup bypasses RLS
from app.models.db_models import Application, Job


def test_dashboard_matches_database(client, auth):
    res = client.get("/api/v1/dashboard/recruiter", headers=auth("anthropic"))
    assert res.status_code == 200, res.text
    d = res.json()

    with SessionLocal() as db:
        jobs = db.query(Job).filter(Job.organization_id == "org_anthropic").all()
        apps = db.query(Application).filter(Application.organization_id == "org_anthropic").all()

    assert d["jobs"]["total"] == len(jobs)
    assert d["jobs"]["active"] == sum(j.status == "Active" for j in jobs)
    assert d["applications_total"] == len(apps)
    assert sum(s["count"] for s in d["funnel"]) == len(apps)
    assert [s["stage"] for s in d["funnel"]][:2] == ["Applied", "Screening"]
    assert d["average_match_score"] == round(sum(a.match_score for a in apps) / len(apps), 1)
    assert len(d["applications_by_day"]) == 31
    assert sum(day["count"] for day in d["applications_by_day"]) <= len(apps)
    # Everything shown belongs to Anthropic
    assert all(a["organization_id"] == "org_anthropic" for a in d["recent_applications"] + d["top_matches"])
    scores = [a["match_score"] for a in d["top_matches"]]
    assert scores == sorted(scores, reverse=True)


def test_dashboard_is_tenant_scoped(client, auth):
    stripe = client.get("/api/v1/dashboard/recruiter", headers=auth("stripe")).json()
    assert all(a["organization_id"] == "org_stripe" for a in stripe["recent_applications"])
    # Filtering by another organization's job is refused
    assert client.get("/api/v1/dashboard/recruiter", headers=auth("stripe"), params={"job_id": "job_001"}).status_code == 404
    # Candidates don't get the hiring dashboard
    assert client.get("/api/v1/dashboard/recruiter", headers=auth("aarav")).status_code == 403


def test_dashboard_job_filter_and_period(client, auth):
    d = client.get("/api/v1/dashboard/recruiter", headers=auth("anthropic"), params={"job_id": "job_001", "days": 7}).json()
    assert d["period_days"] == 7 and len(d["applications_by_day"]) == 8
    assert all(a["job_id"] == "job_001" for a in d["recent_applications"])
    assert d["jobs"]["total"] == 1


def test_super_admin_sees_platform_totals(client, auth):
    d = client.get("/api/v1/dashboard/recruiter", headers=auth("admin")).json()
    with SessionLocal() as db:
        assert d["applications_total"] == db.query(Application).count()
