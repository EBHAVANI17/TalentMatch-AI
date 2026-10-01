"""Domain events (outbox), notifications and the configurable hiring pipeline."""
import uuid

import pytest

from app.core.database import SessionLocal
from app.events import bus
from app.models.db_models import Application, ApplicationStageHistory, Notification, OutboxEvent, PipelineStage


def _new_candidate(client):
    email = f"cand.{uuid.uuid4().hex[:8]}@example.com"
    res = client.post("/api/v1/auth/register/candidate", json={
        "email": email, "password": "candidate-pass-1", "full_name": "Pat Candidate", "skills": ["Python", "AWS"],
    })
    assert res.status_code == 200, res.text
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


def _apply(client, headers, job_id="job_001"):
    res = client.post("/api/v1/applications", headers=headers, json={"job_id": job_id})
    assert res.status_code == 200, res.text
    return res.json()


def _notifications(user_id):
    with SessionLocal() as db:
        return db.query(Notification).filter(Notification.user_id == user_id).all()


# ---------------------------------------------------------------- events & notifications
def test_application_emits_event_and_notifies_both_sides(client):
    headers, user_id = _new_candidate(client)
    app = _apply(client, headers)

    with SessionLocal() as db:
        event = db.query(OutboxEvent).filter(OutboxEvent.type == "application.created").order_by(OutboxEvent.created_at.desc()).first()
        assert event.payload["application_id"] == app["id"]
        assert event.organization_id == "org_anthropic"
        assert event.dispatched_at is not None and event.attempts == 1

    mine = _notifications(user_id)
    assert any(n.title == "Application sent: " + app["job_title"] and n.event_id == event.id for n in mine)
    team = _notifications("usr_rec_anthropic")
    assert any(n.event_id == event.id and n.title.startswith("New candidate for") for n in team)


def test_redelivering_an_event_does_not_duplicate_notifications(client):
    headers, user_id = _new_candidate(client)
    app = _apply(client, headers)
    with SessionLocal() as db:
        event = db.query(OutboxEvent).filter(OutboxEvent.type == "application.created").order_by(OutboxEvent.created_at.desc()).first()
        assert event.payload["application_id"] == app["id"]
        event.dispatched_at = None  # simulate a crash after delivery but before marking it done
        db.commit()
        event_id = event.id
    bus.dispatch_ids([event_id])
    assert len([n for n in _notifications(user_id) if n.event_id == event_id]) == 1


def test_failing_handler_is_recorded_and_retried():
    calls = {"n": 0}

    @bus.on("test.flaky")
    def flaky(db, event):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("temporary outage")

    with SessionLocal() as db:
        record = bus.emit(db, "test.flaky", payload={"x": 1})
        db.commit()  # inline delivery: first attempt fails
        event_id = record.id
    with SessionLocal() as db:
        record = db.get(OutboxEvent, event_id)
        assert record.dispatched_at is None
        assert record.attempts == 1 and "temporary outage" in record.last_error

    bus.dispatch_pending()  # what the worker does
    with SessionLocal() as db:
        record = db.get(OutboxEvent, event_id)
        assert record.dispatched_at is not None and record.attempts == 2
    bus._handlers["test.flaky"].remove(flaky)


def test_worker_mode_defers_delivery(client, monkeypatch):
    monkeypatch.setattr(bus.settings, "event_dispatch_mode", "worker")
    headers, user_id = _new_candidate(client)
    _apply(client, headers)
    assert _notifications(user_id) == []

    bus.dispatch_pending()
    assert len(_notifications(user_id)) == 1


def test_rolled_back_events_are_never_delivered():
    with SessionLocal() as db:
        record = bus.emit(db, "test.never", payload={})
        event_id = record.id
        db.rollback()
    with SessionLocal() as db:
        assert db.get(OutboxEvent, event_id) is None


# ---------------------------------------------------------------- pipeline
def test_stage_moves_accept_aliases_and_notify(client, auth):
    headers, user_id = _new_candidate(client)
    app = _apply(client, headers)
    recruiter = auth("anthropic")

    res = client.patch(f"/api/v1/applications/{app['id']}/stage", headers=recruiter, json={"stage": "AI Screened"})
    assert res.status_code == 200 and res.json()["stage"] == "Screening"
    res = client.patch(f"/api/v1/applications/{app['id']}/stage", headers=recruiter, json={"stage": "shortlisted"})
    assert res.json()["stage"] == "Shortlisted"
    assert any(n.title.startswith("You've been shortlisted") for n in _notifications(user_id))

    # unknown stage -> 422; same stage -> no new history
    assert client.patch(f"/api/v1/applications/{app['id']}/stage", headers=recruiter, json={"stage": "Teleported"}).status_code == 422
    client.patch(f"/api/v1/applications/{app['id']}/stage", headers=recruiter, json={"stage": "Shortlisted"})
    with SessionLocal() as db:
        history = db.query(ApplicationStageHistory).filter(ApplicationStageHistory.application_id == app["id"]).all()
        assert [h.to_stage for h in sorted(history, key=lambda h: h.created_at)] == ["Screening", "Shortlisted"]
        assert all(h.changed_by_user_id == "usr_rec_anthropic" for h in history)


def test_default_pipeline_is_returned(client, auth):
    stages = client.get("/api/v1/pipeline/stages", headers=auth("stripe")).json()
    assert [s["name"] for s in stages] == ["Applied", "Screening", "Shortlisted", "Interview", "Selected", "Hired", "Rejected"]


@pytest.fixture
def reset_stripe_pipeline():
    yield
    with SessionLocal() as db:
        db.query(PipelineStage).filter(PipelineStage.organization_id == "org_stripe").delete()
        db.commit()


def test_org_admin_can_customize_pipeline(client, auth, reset_stripe_pipeline):
    admin = auth("stripe")
    custom = [
        {"name": "Applied", "kind": "active"}, {"name": "Phone Screen", "kind": "active"},
        {"name": "Shortlisted", "kind": "active"}, {"name": "Screening", "kind": "active"},
        {"name": "Interview", "kind": "active"}, {"name": "Onsite", "kind": "active"},
        {"name": "Hired", "kind": "hired"}, {"name": "Rejected", "kind": "rejected"},
    ]
    res = client.put("/api/v1/pipeline/stages", headers=admin, json={"stages": custom})
    assert res.status_code == 200, res.text
    assert "Onsite" in [s["name"] for s in client.get("/api/v1/pipeline/stages", headers=admin).json()]

    # Stripe's applications can now use the custom stage; Anthropic's cannot
    with SessionLocal() as db:
        stripe_app = db.query(Application).filter(Application.organization_id == "org_stripe").first().id
    assert client.patch(f"/api/v1/applications/{stripe_app}/stage", headers=admin, json={"stage": "Onsite"}).json()["stage"] == "Onsite"
    with SessionLocal() as db:
        anthropic_app = db.query(Application).filter(Application.organization_id == "org_anthropic").first().id
    assert client.patch(f"/api/v1/applications/{anthropic_app}/stage", headers=auth("anthropic"), json={"stage": "Onsite"}).status_code == 422

    # A stage that still holds applications can't be removed
    without_onsite = [s for s in custom if s["name"] != "Onsite"]
    assert client.put("/api/v1/pipeline/stages", headers=admin, json={"stages": without_onsite}).status_code == 409
    client.patch(f"/api/v1/applications/{stripe_app}/stage", headers=admin, json={"stage": "Interview"})


def test_pipeline_rules(client, auth):
    admin = auth("stripe")
    two_hired = [{"name": "A", "kind": "active"}, {"name": "B", "kind": "hired"}, {"name": "C", "kind": "hired"}, {"name": "R", "kind": "rejected"}]
    assert client.put("/api/v1/pipeline/stages", headers=admin, json={"stages": two_hired}).status_code == 422
    dupes = [{"name": "A", "kind": "active"}, {"name": "a", "kind": "active"}, {"name": "H", "kind": "hired"}, {"name": "R", "kind": "rejected"}]
    assert client.put("/api/v1/pipeline/stages", headers=admin, json={"stages": dupes}).status_code == 422
    # Candidates can read stage names but not change them
    headers, _ = _new_candidate(client)
    assert client.put("/api/v1/pipeline/stages", headers=headers, json={"stages": two_hired}).status_code == 403
