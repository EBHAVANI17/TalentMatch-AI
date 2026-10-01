from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.applications import get_app_out
from app.core.database import get_db
from app.core.tenancy import TenantContext, get_tenant
from app.models.db_models import Application, Job
from app.models.schemas import ApplicationOut
from app.services.dashboard_service import recruiter_dashboard

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class JobCounts(BaseModel):
    total: int
    active: int
    draft: int
    paused: int
    closed: int


class CandidateCounts(BaseModel):
    in_pipeline: int
    new_in_period: int


class FunnelStage(BaseModel):
    stage: str
    kind: str
    count: int


class DayCount(BaseModel):
    date: str
    count: int


class RecruiterDashboard(BaseModel):
    period_days: int
    jobs: JobCounts
    candidates: CandidateCounts
    applications_total: int
    shortlisted: int
    interviewing: int
    upcoming_interviews: int
    hires: int
    average_match_score: Optional[float] = None
    funnel: List[FunnelStage]
    applications_by_day: List[DayCount]
    recent_applications: List[ApplicationOut]
    top_matches: List[ApplicationOut]


@router.get("/recruiter", response_model=RecruiterDashboard)
def get_recruiter_dashboard(
    days: int = Query(30, ge=7, le=365),
    job_id: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None, description="Super admins only; omit for the whole platform"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant),
):
    if ctx.is_super_admin:
        org_id = organization_id
    elif ctx.is_org_member:
        org_id = ctx.org_id
    else:
        raise HTTPException(status_code=403, detail="The hiring dashboard is for organization members")
    if job_id and not ctx.is_super_admin:
        job = db.get(Job, job_id)
        if job is None or job.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Job requisition not found")

    data = recruiter_dashboard(db, org_id, days=days, job_id=job_id)
    recent_ids = data.pop("recent_application_ids")
    top_ids = data.pop("top_match_ids")
    apps = {a.id: a for a in db.query(Application).filter(Application.id.in_(recent_ids + top_ids)).all()}
    return RecruiterDashboard(
        **data,
        recent_applications=[get_app_out(apps[i]) for i in recent_ids if i in apps],
        top_matches=[get_app_out(apps[i]) for i in top_ids if i in apps],
    )
