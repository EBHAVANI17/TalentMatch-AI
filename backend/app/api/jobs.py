import json
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.tenancy import (
    TenantContext, get_tenant_optional, require_permission, scope_jobs, get_visible_job
)
from app.models.db_models import Job
from app.models.schemas import JobOut, JobCreate
from app.services.recommender_service import get_job_out
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/jobs", tags=["Job Requisitions"])

@router.get("", response_model=List[JobOut])
def get_all_jobs(
    db: Session = Depends(get_db),
    ctx: Optional[TenantContext] = Depends(get_tenant_optional),
    organization_id: Optional[str] = Query(None),
    status: Optional[str] = Query("Active")
):
    # Anonymous users and candidates see the public (Active) job board;
    # organization members see their own organization's requisitions.
    query = scope_jobs(db.query(Job), ctx)
    if status and status != "all":
        query = query.filter(Job.status == status)
    if organization_id:
        query = query.filter(Job.organization_id == organization_id)
    jobs = query.order_by(Job.created_at.desc()).all()
    return [get_job_out(j) for j in jobs]

@router.get("/{job_id}", response_model=JobOut)
def get_job_by_id(
    job_id: str,
    db: Session = Depends(get_db),
    ctx: Optional[TenantContext] = Depends(get_tenant_optional)
):
    return get_job_out(get_visible_job(db, ctx, job_id))

@router.post("", response_model=JobOut)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("jobs:create_edit"))
):
    current_user = ctx.user
    org_id = ctx.org_id
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job requisitions must belong to an organization"
        )
    job_id = f"job_{uuid.uuid4().hex[:8]}"

    job = Job(
        id=job_id,
        organization_id=org_id,
        created_by_user_id=current_user.id,
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
        user_id=current_user.id,
        user_email=current_user.email,
        organization_id=org_id,
        details={"title": payload.title, "organization_id": org_id}
    )

    return get_job_out(job)
