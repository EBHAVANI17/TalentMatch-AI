"""Job requisitions: creation, editing and the publish/pause/close/archive lifecycle.

    Draft --publish--> Active (published, on the job board)
    Active --pause--> Paused --publish--> Active
    Active|Paused --close--> Closed --publish--> Active (reopen)
    Draft|Paused|Closed --archive--> Archived (read-only)
"""
import json
import uuid
from datetime import datetime
from typing import Dict, Set

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.events import emit
from app.models.db_models import Job, Organization, User
from app.models.schemas import JobCreate, JobUpdate
from app.services.skills_service import set_job_skills

DRAFT, ACTIVE, PAUSED, CLOSED, ARCHIVED = "Draft", "Active", "Paused", "Closed", "Archived"
JOB_STATUSES = (DRAFT, ACTIVE, PAUSED, CLOSED, ARCHIVED)
WORKPLACE_TYPES = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "Onsite", "on-site": "Onsite"}

# action -> (statuses it may start from, resulting status)
TRANSITIONS: Dict[str, tuple] = {
    "publish": ({DRAFT, PAUSED, CLOSED}, ACTIVE),
    "pause": ({ACTIVE}, PAUSED),
    "close": ({ACTIVE, PAUSED}, CLOSED),
    "archive": ({DRAFT, PAUSED, CLOSED}, ARCHIVED),
}


def _conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, message)


def _normalize_workplace(value: str) -> str:
    normalized = WORKPLACE_TYPES.get((value or "").strip().lower())
    if not normalized:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "workplace_type must be Remote, Hybrid or Onsite")
    return normalized


def _validate_ranges(job: Job) -> None:
    if job.salary_min and job.salary_max and job.salary_min > job.salary_max:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "salary_min cannot be greater than salary_max")
    if job.max_experience_years is not None and job.min_experience_years > job.max_experience_years:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "min_experience_years cannot be greater than max_experience_years")


def ensure_can_publish(db: Session, org: Organization, exclude_job_id: str = "") -> None:
    """Plan entitlement: number of published jobs."""
    active = db.query(Job).filter(Job.organization_id == org.id, Job.status == ACTIVE, Job.id != exclude_job_id).count()
    if active >= org.max_active_jobs:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Your plan allows {org.max_active_jobs} active jobs. Pause or close one, or upgrade the plan.",
        )


def create_job(db: Session, org: Organization, actor: User, payload: JobCreate) -> Job:
    job = Job(
        id=f"job_{uuid.uuid4().hex[:8]}",
        organization_id=org.id,
        created_by_user_id=actor.id,
        title=payload.title.strip(),
        department=payload.department,
        description=payload.description,
        responsibilities_json=json.dumps(payload.key_responsibilities),
        min_experience_years=payload.min_experience_years,
        max_experience_years=payload.max_experience_years,
        location=payload.location,
        workplace_type=_normalize_workplace(payload.workplace_type),
        employment_type=payload.employment_type,
        openings=payload.openings,
        seniority=payload.seniority,
        industry=payload.industry or org.industry or "",
        application_deadline=payload.application_deadline,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        equity=payload.equity,
        required_education=payload.required_education,
        urgency=payload.urgency,
        status=DRAFT,
        benefits_json=json.dumps(payload.benefits),
        screening_questions_json=json.dumps(payload.screening_questions),
        interview_criteria_json=json.dumps(payload.interview_criteria),
        applicants_count=0,
    )
    _validate_ranges(job)
    db.add(job)
    db.flush()
    set_job_skills(db, job, payload.required_skills, payload.preferred_skills)
    emit(db, "job.created", organization_id=org.id, actor=actor, payload={"job_id": job.id, "title": job.title})
    if payload.status == ACTIVE:
        transition(db, job, "publish", actor)
    return job


def update_job(db: Session, job: Job, actor: User, payload: JobUpdate) -> Job:
    if job.status == ARCHIVED:
        raise _conflict("Archived jobs are read-only. Duplicate it to start a new requisition.")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return job

    simple = {
        "title", "department", "description", "min_experience_years", "max_experience_years", "location",
        "employment_type", "openings", "seniority", "industry", "application_deadline", "salary_min",
        "salary_max", "equity", "required_education", "urgency",
    }
    for field in simple & changes.keys():
        setattr(job, field, changes[field])
    if "workplace_type" in changes:
        job.workplace_type = _normalize_workplace(changes["workplace_type"])
    if "key_responsibilities" in changes:
        job.responsibilities_json = json.dumps(changes["key_responsibilities"] or [])
    if "benefits" in changes:
        job.benefits_json = json.dumps(changes["benefits"] or [])
    if "screening_questions" in changes:
        job.screening_questions_json = json.dumps(changes["screening_questions"] or [])
    if "interview_criteria" in changes:
        job.interview_criteria_json = json.dumps(changes["interview_criteria"] or [])
    if "required_skills" in changes or "preferred_skills" in changes:
        set_job_skills(
            db, job,
            changes.get("required_skills", job.required_skills) or [],
            changes.get("preferred_skills", job.preferred_skills) or [],
        )
    _validate_ranges(job)
    job.updated_at = datetime.utcnow()
    emit(db, "job.updated", organization_id=job.organization_id, actor=actor,
         payload={"job_id": job.id, "fields": sorted(changes.keys())})
    return job


def transition(db: Session, job: Job, action: str, actor: User) -> Job:
    if action not in TRANSITIONS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown action '{action}'")
    allowed_from, target = TRANSITIONS[action]
    if job.status not in allowed_from:
        hint = " Close it first." if action == "archive" and job.status == ACTIVE else ""
        raise _conflict(f"Cannot {action} a job that is {job.status}.{hint}")
    if target == ACTIVE:
        ensure_can_publish(db, job.organization, exclude_job_id=job.id)
        job.published_at = job.published_at or datetime.utcnow()
        job.closed_at = None
    if target == CLOSED:
        job.closed_at = datetime.utcnow()
    previous = job.status
    job.status = target
    job.updated_at = datetime.utcnow()
    event_name = {"publish": "job.published", "pause": "job.paused", "close": "job.closed", "archive": "job.archived"}[action]
    emit(db, event_name, organization_id=job.organization_id, actor=actor,
         payload={"job_id": job.id, "title": job.title, "from_status": previous, "to_status": target})
    return job


def duplicate_job(db: Session, job: Job, actor: User) -> Job:
    copy = Job(
        id=f"job_{uuid.uuid4().hex[:8]}",
        organization_id=job.organization_id,
        created_by_user_id=actor.id,
        title=f"{job.title} (copy)"[:128],
        department=job.department,
        description=job.description,
        responsibilities_json=job.responsibilities_json,
        min_experience_years=job.min_experience_years,
        max_experience_years=job.max_experience_years,
        location=job.location,
        workplace_type=job.workplace_type,
        employment_type=job.employment_type,
        openings=job.openings,
        seniority=job.seniority,
        industry=job.industry,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        equity=job.equity,
        required_education=job.required_education,
        urgency=job.urgency,
        status=DRAFT,
        benefits_json=job.benefits_json,
        screening_questions_json=job.screening_questions_json,
        interview_criteria_json=job.interview_criteria_json,
        applicants_count=0,
    )
    db.add(copy)
    db.flush()
    set_job_skills(db, copy, job.required_skills, job.preferred_skills)
    emit(db, "job.created", organization_id=copy.organization_id, actor=actor,
         payload={"job_id": copy.id, "title": copy.title, "duplicated_from": job.id})
    return copy


def available_actions(job: Job) -> Set[str]:
    return {action for action, (allowed_from, _) in TRANSITIONS.items() if job.status in allowed_from}
