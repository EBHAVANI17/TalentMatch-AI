from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.tenancy import (
    TenantContext, get_tenant, get_visible_candidate, get_managed_job, scope_candidates
)
from app.models.db_models import CandidateProfile
from app.models.schemas import JobMatchResult, CandidateMatchResult
from app.services.recommender_service import (
    recommend_jobs_for_candidate_db, recommend_candidates_for_job_db
)

router = APIRouter(prefix="/recommendations", tags=["AI Autonomous Recommendations"])


def jobs_for_candidate(db: Session, ctx: TenantContext, candidate_id: str) -> List[JobMatchResult]:
    """Active jobs ranked for a candidate. Organization members only see their own jobs."""
    get_visible_candidate(db, ctx, candidate_id)
    matches = recommend_jobs_for_candidate_db(db, candidate_id)
    if ctx.is_org_member:
        matches = [m for m in matches if m.job.organization_id == ctx.org_id]
    return matches


@router.get("/jobs-for-candidate/{candidate_id}", response_model=List[JobMatchResult])
def get_jobs_for_candidate(candidate_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    return jobs_for_candidate(db, ctx, candidate_id)


@router.get("/candidates-for-job/{job_id}", response_model=List[CandidateMatchResult])
def get_candidates_for_job(job_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    get_managed_job(db, ctx, job_id)
    return recommend_candidates_for_job_db(db, job_id, scope_candidates(db.query(CandidateProfile), ctx))
