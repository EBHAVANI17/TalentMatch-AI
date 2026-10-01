from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenancy import TenantContext, get_tenant
from app.matching.ontology import get_skill_graph
from app.models.schemas import CandidateProfileOut, JobOut, OrganizationOut
from app.search import service
from app.services.recommender_service import get_job_out

router = APIRouter(prefix="/search", tags=["Search"])

ALL_TYPES = ("candidates", "jobs", "skills", "organizations")


class CandidateHit(BaseModel):
    candidate: CandidateProfileOut
    relevance: float
    reasons: List[str]


class SkillHit(BaseModel):
    id: str
    name: str
    category: str


class SearchResults(BaseModel):
    query: str
    interpreted: dict  # what the query was understood as (skills, experience, location, work mode, keywords)
    candidates: List[CandidateHit] = []
    jobs: List[JobOut] = []
    skills: List[SkillHit] = []
    organizations: List[OrganizationOut] = []


@router.get("", response_model=SearchResults)
def search(
    q: str = Query(..., min_length=1, max_length=200),
    types: Optional[List[str]] = Query(None, description="candidates, jobs, skills, organizations (default: all you can see)"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant),
):
    """Search across candidates, jobs, skills and organizations in plain language,
    e.g. "senior engineers with strong cloud experience in Bangalore"."""
    wanted = set(types or ALL_TYPES) & set(ALL_TYPES)
    parsed = service.parse_query(q, get_skill_graph(db))
    results = SearchResults(query=q, interpreted=service.interpreted(parsed))
    if "candidates" in wanted and (ctx.is_org_member or ctx.is_super_admin):
        results.candidates = [CandidateHit(**hit) for hit in service.search_candidates(db, ctx, parsed, limit)]
    if "jobs" in wanted:
        results.jobs = [get_job_out(j) for j in service.search_jobs(db, ctx, parsed, limit)]
    if "skills" in wanted:
        results.skills = [SkillHit(**s) for s in service.search_skills(db, q, limit)]
    if "organizations" in wanted:
        results.organizations = service.search_organizations(db, ctx, q, limit)
    return results
