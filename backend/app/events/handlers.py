"""Event handlers. Each must be idempotent (events can be retried)."""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.tenancy import ORG_ROLES
from app.events.bus import on
from app.models.db_models import Application, OutboxEvent, User
from app.services.notification_service import notify


def _hiring_team(db: Session, org_id: Optional[str], exclude_user_id: Optional[str]) -> List[User]:
    if not org_id:
        return []
    return (
        db.query(User)
        .filter(User.organization_id == org_id, User.role.in_(ORG_ROLES), User.is_active.is_(True))
        .filter(User.id != (exclude_user_id or ""))
        .all()
    )


def _application(db: Session, event: OutboxEvent) -> Optional[Application]:
    return db.get(Application, event.payload.get("application_id"))


@on("application.created")
def notify_application_created(db: Session, event: OutboxEvent) -> None:
    app = _application(db, event)
    if app is None or app.job is None or app.candidate is None:
        return
    job, candidate = app.job, app.candidate
    company = job.organization.name if job.organization else "the employer"

    if app.source == "applied":
        notify(db, candidate.user, kind="application", event_id=event.id, link="/applications",
               title=f"Application sent: {job.title}",
               message=f"Your application to {company} was received. You'll be notified as it moves through their process.")
    for member in _hiring_team(db, app.organization_id, event.actor_user_id):
        name = candidate.user.full_name if candidate.user else "A candidate"
        verb = "applied to" if app.source == "applied" else "was added to"
        notify(db, member, kind="application", event_id=event.id, link=f"/app/jobs/{job.id}",
               title=f"New candidate for {job.title}",
               message=f"{name} {verb} {job.title}. Match score: {app.match_score}%.")


@on("application.stage_changed")
def notify_stage_changed(db: Session, event: OutboxEvent) -> None:
    app = _application(db, event)
    if app is None or app.candidate is None:
        return
    job_title = app.job.title if app.job else "your application"
    to_stage = event.payload.get("to_stage", app.stage)
    if to_stage == "Shortlisted":
        title, message = f"You've been shortlisted for {job_title}", "The hiring team would like to move forward with your application."
    elif to_stage == "Rejected":
        title, message = f"Update on {job_title}", "The team has decided not to move forward this time. Thank you for your interest."
    else:
        title, message = f"Application update: {job_title}", f"Your application moved to {to_stage}."
    notify(db, app.candidate.user, kind="stage_change", event_id=event.id, link="/applications", title=title, message=message)


# ---------------------------------------------------------------------------
# Keep semantic vectors current
# ---------------------------------------------------------------------------
def _refresh_embedding(db: Session, entity_type: str, obj) -> None:
    from app.matching import embeddings

    if obj is not None:
        embeddings.refresh(db, entity_type, [obj])


@on("candidate.created")
@on("candidate.updated")
def embed_candidate(db: Session, event: OutboxEvent) -> None:
    from app.models.db_models import CandidateProfile

    _refresh_embedding(db, "candidate", db.get(CandidateProfile, event.payload.get("candidate_id")))


@on("job.created")
@on("job.updated")
@on("job.published")
def embed_job(db: Session, event: OutboxEvent) -> None:
    from app.models.db_models import Job

    _refresh_embedding(db, "job", db.get(Job, event.payload.get("job_id")))


# ---------------------------------------------------------------------------
# Candidate discovery when a job is published
# ---------------------------------------------------------------------------
STRONG_MATCH = 80


@on("job.published")
def discover_candidates(db: Session, event: OutboxEvent) -> None:
    """Score the talent pool for a newly published job; tell the hiring team and strongly matching candidates."""
    from app.matching import service as matching
    from app.matching.embeddings import refresh
    from app.models.db_models import Application as App, CandidateProfile, Job
    from sqlalchemy import or_

    job = db.get(Job, event.payload.get("job_id"))
    if job is None or job.status != "Active":
        return
    refresh(db, "job", [job])
    pool = db.query(CandidateProfile).filter(or_(
        CandidateProfile.owner_org_id == job.organization_id,
        CandidateProfile.owner_org_id.is_(None) & CandidateProfile.is_searchable.is_(True),
    )).all()
    rows = list(matching.ensure_matches(db, job, pool).values())
    summary = matching.summarize(rows)

    for member in _hiring_team(db, job.organization_id, None):
        notify(db, member, kind="job", event_id=event.id, link=f"/app/talent-match?job={job.id}",
               title=f"{summary['potential']} potentially relevant candidates for {job.title}",
               message=f"{summary['strong']} strong matches (80%+) out of {summary['considered']} profiles reviewed.")

    applied = {cid for (cid,) in db.query(App.candidate_id).filter(App.job_id == job.id)}
    company = job.organization.name if job.organization else "A company"
    for row in rows:
        cand = row.candidate
        if (row.score >= STRONG_MATCH and cand.owner_org_id is None and cand.availability != "not_looking"
                and cand.id not in applied and cand.user and cand.user.is_active):
            notify(db, cand.user, kind="job", event_id=event.id, link="/app/jobs-for-you",
                   title=f"New job match: {job.title} at {company}",
                   message=f"{row.score}% match to the role's listed requirements.")
