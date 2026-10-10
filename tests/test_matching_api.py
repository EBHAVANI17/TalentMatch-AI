"""Talent Match API: ranking, explanations, decisions, weights, candidate job matches, discovery."""
import uuid

from app.core.database import AdminSessionLocal as SessionLocal  # test setup bypasses RLS
from app.models.db_models import Application, Match, Notification, OutboxEvent

URL = "/api/v1/matching/jobs/job_001/candidates"


def test_ranked_explained_and_scoped(client, auth):
    res = client.get(URL, headers=auth("anthropic"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert "not a measure of a person's quality" in body["disclaimer"]
    scores = [i["match"]["score"] for i in body["items"]]
    assert scores == sorted(scores, reverse=True) and scores
    assert body["summary"]["considered"] >= len(body["items"])
    assert body["summary"]["potential"] == sum(1 for s in scores if s >= 60)

    item = body["items"][0]
    factors = item["match"]["factors"]
    assert abs(sum(f["weight"] for f in factors) - 1) < 1e-6
    assert round(100 * sum((f["score"] or 0) * f["weight"] for f in factors)) == item["match"]["score"]
    assert all(f["detail"] for f in factors)

    by_id = {i["candidate"]["id"]: i for i in body["items"]}
    assert by_id["cand_001"]["application"]["id"] == "app_001"       # applied -> contacts + resume visible
    assert by_id["cand_001"]["candidate"]["email"] == "aarav@stanford.edu"
    assert by_id["cand_002"]["candidate"]["email"] == ""             # talent pool -> no contacts
    assert by_id["cand_002"]["resume_document_id"] is None


def test_filters_and_sorting(client, auth):
    h = auth("anthropic")
    everyone = client.get(URL, headers=h).json()["items"]
    assert client.get(URL, headers=h, params={"min_score": 101}).status_code == 422
    high = client.get(URL, headers=h, params={"min_score": 90}).json()
    assert all(i["match"]["score"] >= 90 for i in high["items"])
    assert high["summary"]["considered"] >= len(everyone)  # the summary ignores display filters
    by_exp = client.get(URL, headers=h, params={"sort": "experience"}).json()["items"]
    years = [i["candidate"]["experience_years"] for i in by_exp]
    assert years == sorted(years, reverse=True)
    python_only = client.get(URL, headers=h, params={"skills": ["Python"]}).json()["items"]
    assert all(any(s.lower() == "python" for s in i["candidate"]["skills"]) for i in python_only)


def test_other_orgs_and_candidates_are_refused(client, auth):
    assert client.get(URL, headers=auth("stripe")).status_code == 404
    assert client.get(URL, headers=auth("aarav")).status_code == 403
    assert client.get(f"{URL}/cand_001", headers=auth("stripe")).status_code == 404


def test_shortlisting_adds_to_pipeline_once(client, auth):
    h = auth("anthropic")
    res = client.post(f"{URL}/cand_004/shortlist", headers=h)
    assert res.status_code == 200, res.text
    item = res.json()
    assert item["status"] == "shortlisted" and item["application"]["stage"] == "Shortlisted"
    client.post(f"{URL}/cand_004/shortlist", headers=h)
    with SessionLocal() as db:
        apps = db.query(Application).filter(Application.job_id == "job_001", Application.candidate_id == "cand_004").all()
        assert len(apps) == 1 and apps[0].source == "sourced"
        notes = db.query(Notification).filter(Notification.user_id == "usr_cand_sophia").all()
        assert any(n.title.startswith("You've been shortlisted") for n in notes)


def test_rejecting_a_non_applicant_only_hides_them(client, auth):
    h = auth("anthropic")
    with SessionLocal() as db:
        notes_before = db.query(Notification).filter(Notification.user_id == "usr_cand_marcus").count()
    res = client.post(f"{URL}/cand_003/reject", headers=h)
    assert res.status_code == 200 and res.json()["status"] == "dismissed" and res.json()["application"] is None
    with SessionLocal() as db:
        assert db.query(Notification).filter(Notification.user_id == "usr_cand_marcus").count() == notes_before
    assert "cand_003" not in [i["candidate"]["id"] for i in client.get(URL, headers=h).json()["items"]]
    assert "cand_003" in [i["candidate"]["id"] for i in client.get(URL, headers=h, params={"status": "dismissed"}).json()["items"]]
    assert client.post(f"{URL}/cand_003/restore", headers=h).json()["status"] == "new"


def test_rejecting_an_applicant_moves_them_to_rejected(client, auth):
    h = auth("stripe")
    res = client.post("/api/v1/matching/jobs/job_003/candidates/cand_003/reject", headers=h)
    assert res.status_code == 200
    assert res.json()["application"]["stage"] == "Rejected"
    # put them back for other tests
    client.patch(f"/api/v1/applications/{res.json()['application']['id']}/stage", headers=h, json={"stage": "Applied"})


def test_weights_permissions_and_effect(client, auth):
    h = auth("anthropic")
    assert client.get("/api/v1/matching/weights", headers=auth("aarav")).status_code == 403
    current = client.get("/api/v1/matching/weights", headers=h).json()
    assert current["weights"] == current["defaults"]

    assert client.put("/api/v1/matching/weights", headers=h, json={"weights": {"charm": 1}}).status_code == 422
    assert client.put("/api/v1/matching/weights", headers=h, json={"weights": {"skills": 0}}).status_code == 422
    before = client.get(f"{URL}/cand_002", headers=h).json()["match"]["score"]
    try:
        updated = client.put("/api/v1/matching/weights", headers=h, json={"weights": {"skills": 1.0, "semantic": 0}})
        assert updated.status_code == 200 and updated.json()["weights"]["skills"] == 1.0
        after = client.get(f"{URL}/cand_002", headers=h).json()
        assert after["match"]["score"] != before
        assert next(f for f in after["match"]["factors"] if f["key"] == "semantic")["weight"] == 0
    finally:
        client.put("/api/v1/matching/weights", headers=h, json={"weights": {}})


def test_matches_recompute_when_profile_changes(client, auth):
    h = auth("anthropic")
    client.get(f"{URL}/cand_002", headers=h)
    with SessionLocal() as db:
        before = db.query(Match).filter(Match.job_id == "job_001", Match.candidate_id == "cand_002").one().inputs_hash
    client.patch("/api/v1/candidates/me", headers=auth("elena"), json={"skills": ["TypeScript", "React", "PyTorch", "LLMs"]})
    client.get(f"{URL}/cand_002", headers=h)
    with SessionLocal() as db:
        after = db.query(Match).filter(Match.job_id == "job_001", Match.candidate_id == "cand_002").one().inputs_hash
    assert after != before


def test_candidate_sees_ranked_job_matches(client, auth):
    items = client.get("/api/v1/matching/me/jobs", headers=auth("aarav")).json()
    scores = [i["match"]["score"] for i in items]
    assert scores == sorted(scores, reverse=True)
    applied = {i["job"]["id"]: i for i in items}
    assert applied["job_001"]["applied"] is True
    assert client.get("/api/v1/matching/me/jobs", headers=auth("anthropic")).status_code == 403


def test_publishing_a_job_notifies_team_about_matching_talent(client, auth):
    h = auth("anthropic")
    res = client.post("/api/v1/jobs", headers=h, json={
        "title": f"ML Platform Engineer {uuid.uuid4().hex[:4]}", "description": "Serve PyTorch models at scale.",
        "required_skills": ["Python", "PyTorch", "Kubernetes"], "min_experience_years": 3, "location": "Remote",
        "workplace_type": "Remote",
    })
    assert res.status_code == 200
    with SessionLocal() as db:
        event = db.query(OutboxEvent).filter(OutboxEvent.type == "job.published", OutboxEvent.payload_json.like(f'%{res.json()["id"]}%')).one()
        team = db.query(Notification).filter(Notification.event_id == event.id, Notification.user_id == "usr_rec_anthropic").one()
        assert "potentially relevant candidates" in team.title
        assert db.query(Match).filter(Match.job_id == res.json()["id"]).count() >= 3


def test_both_batch_paths_agree_and_do_not_recompute_each_other(client, auth):
    """Recruiter view (job x many) and candidate view (candidate x many) share stored matches."""
    client.get(URL, headers=auth("anthropic"))
    with SessionLocal() as db:
        before = db.query(Match).filter(Match.job_id == "job_001", Match.candidate_id == "cand_001").one()
        stamp, score = before.computed_at, before.score
    items = {i["job"]["id"]: i for i in client.get("/api/v1/matching/me/jobs", headers=auth("aarav")).json()}
    assert items["job_001"]["match"]["score"] == score
    with SessionLocal() as db:
        assert db.query(Match).filter(Match.job_id == "job_001", Match.candidate_id == "cand_001").one().computed_at == stamp
