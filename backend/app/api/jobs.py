from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.tenancy import (
    TenantContext, get_tenant_optional, require_permission, scope_jobs, get_visible_job, get_managed_job
)
from app.models.db_models import Job, Organization
from app.models.schemas import JobOut, JobCreate, JobUpdate
from app.services import job_service
from app.services.recommender_service import get_job_out
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/jobs", tags=["Job Requisitions"])

LifecycleAction = Literal["publish", "pause", "close", "archive"]


def _audit(db: Session, ctx: TenantContext, action: str, job: Job, details: Optional[dict] = None) -> None:
    log_audit_event(
        db=db, action=action, module="Jobs", entity="Job", entity_id=job.id,
        user_id=ctx.user.id, user_email=ctx.user.email, organization_id=job.organization_id,
        details={"title": job.title, "status": job.status, **(details or {})},
    )


@router.get("", response_model=List[JobOut])
def get_all_jobs(
    db: Session = Depends(get_db),
    ctx: Optional[TenantContext] = Depends(get_tenant_optional),
    organization_id: Optional[str] = Query(None),
    status: Optional[str] = Query("Active", description="Draft, Active, Paused, Closed, Archived, or 'all'"),
    q: Optional[str] = Query(None, max_length=100, description="Search title, department and location"),
    department: Optional[str] = Query(None),
    workplace_type: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
):
    # Anonymous users and candidates see the public (Active) job board;
    # organization members see their own organization's requisitions.
    query = scope_jobs(db.query(Job), ctx)
    if status and status != "all":
        query = query.filter(Job.status == status)
    if organization_id:
        query = query.filter(Job.organization_id == organization_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(Job.title.ilike(like), Job.department.ilike(like), Job.location.ilike(like)))
    if department:
        query = query.filter(Job.department == department)
    if workplace_type:
        query = query.filter(Job.workplace_type == workplace_type)
    jobs = query.order_by(Job.created_at.desc()).limit(limit).all()
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
    if not ctx.org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job requisitions must belong to an organization"
        )
    org = db.get(Organization, ctx.org_id)
    job = job_service.create_job(db, org, ctx.user, payload)
    db.commit()
    db.refresh(job)
    _audit(db, ctx, "JOB_CREATED", job, {"organization_id": org.id})
    return get_job_out(job)

@router.patch("/{job_id}", response_model=JobOut)
def update_job(
    job_id: str,
    payload: JobUpdate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("jobs:create_edit"))
):
    job = get_managed_job(db, ctx, job_id)
    job_service.update_job(db, job, ctx.user, payload)
    db.commit()
    db.refresh(job)
    _audit(db, ctx, "JOB_UPDATED", job, {"fields": sorted(payload.model_dump(exclude_unset=True).keys())})
    return get_job_out(job)

@router.post("/{job_id}/duplicate", response_model=JobOut, status_code=201)
def duplicate_job(
    job_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("jobs:create_edit"))
):
    """Copy a requisition (any status) into a new Draft."""
    source = get_managed_job(db, ctx, job_id)
    copy = job_service.duplicate_job(db, source, ctx.user)
    db.commit()
    db.refresh(copy)
    _audit(db, ctx, "JOB_DUPLICATED", copy, {"duplicated_from": source.id})
    return get_job_out(copy)

@router.post("/{job_id}/{action}", response_model=JobOut)
def change_job_status(
    job_id: str,
    action: LifecycleAction,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("jobs:create_edit"))
):
    """Lifecycle: publish (Draft/Paused/Closed -> Active), pause, close, archive."""
    job = get_managed_job(db, ctx, job_id)
    job_service.transition(db, job, action, ctx.user)
    db.commit()
    db.refresh(job)
    _audit(db, ctx, f"JOB_{action.upper()}", job)
    return get_job_out(job)
