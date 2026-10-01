import json
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user, get_current_user_optional, require_roles
from app.models.db_models import Job, Organization, User
from app.models.schemas import JobOut, JobCreate
from app.services.recommender_service import get_job_out
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/jobs", tags=["Job Requisitions"])

@router.get("", response_model=List[JobOut])
def get_all_jobs(
    db: Session = Depends(get_db),
    organization_id: Optional[str] = Query(None),
    status: Optional[str] = Query("Active")
):
    query = db.query(Job)
    if status and status != "all":
        query = query.filter(Job.status == status)
    if organization_id:
        query = query.filter(Job.organization_id == organization_id)
    jobs = query.order_by(Job.created_at.desc()).all()
    return [get_job_out(j) for j in jobs]

@router.get("/{job_id}", response_model=JobOut)
def get_job_by_id(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job requisition not found")
    return get_job_out(job)

@router.post("", response_model=JobOut)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    org_id = current_user.organization_id if current_user and current_user.organization_id else "org_anthropic"
    job_id = f"job_{uuid.uuid4().hex[:8]}"

    job = Job(
        id=job_id,
        organization_id=org_id,
        created_by_user_id=current_user.id if current_user else None,
        title=payload.title,
        department=payload.department,
        description=payload.description,
        responsibilities_json=json.dumps(payload.key_responsibilities),
        required_skills_json=json.dumps(payload.required_skills),
        preferred_skills_json=json.dumps(payload.preferred_skills),
        min_experience_years=payload.min_experience_years,
        location=payload.location,
        workplace_type=payload.workplace_type,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        equity=payload.equity,
        required_education=payload.required_education,
        urgency=payload.urgency,
        status="Active",
        benefits_json=json.dumps(payload.benefits),
        applicants_count=0
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    log_audit_event(
        db=db,
        action="JOB_CREATED",
        module="Jobs",
        entity="Job",
        entity_id=job.id,
        user_id=current_user.id if current_user else None,
        user_email=current_user.email if current_user else "anonymous",
        details={"title": payload.title, "organization_id": org_id}
    )

    return get_job_out(job)
