"""Talent Match: ranked, explainable candidate matches for a job, and job matches for candidates.

Scores rank fit to a job's listed criteria. Shortlisting or rejecting is always a
person's decision; nothing here changes a candidate's status automatically.
"""
import uuid
from datetime import datetime
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenancy import TenantContext, get_tenant, get_visible_candidate, require_permission, scope_candidates
from app.events import emit
from app.matching import service as matching
from app.matching.engine import DEFAULT_WEIGHTS, FACTOR_LABELS
from app.models.db_models import Application, CandidateProfile, Job, Match, Organization, Resume
from app.models.schemas import CandidateProfileOut, JobOut
from app.services import candidate_service
from app.services.audit_service import log_audit_event
from app.services.pipeline_service import get_stages, move_application
from app.services.recommender_service import get_job_out

router = APIRouter(prefix="/matching", tags=["Talent Matching"])

DISCLAIMER = "Match scores measure fit to this job's listed criteria. They are not a measure of a person's quality or potential."


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class FactorOut(BaseModel):
    key: str
    label: str
    score: Optional[float] = None
    weight: float
    detail: str


class SkillMatchOut(BaseModel):
    skill: str
    importance: str
    score: float
    kind: str
    via: Optional[str] = None


class MissingSkillOut(BaseModel):
    skill: str
    importance: str


class MatchDetail(BaseModel):
    score: int
    fit_level: str
    factors: List[FactorOut]
    strengths: List[str]
    gaps: List[str]
    matching_skills: List[SkillMatchOut]
    missing_skills: List[MissingSkillOut]
    explanation: str
    engine_version: str
    computed_at: datetime


class ApplicationRef(BaseModel):
    id: str
    stage: str


class CandidateMatchItem(BaseModel):
    candidate: CandidateProfileOut
    match: MatchDetail
    status: str  # new | shortlisted | dismissed
    application: Optional[ApplicationRef] = None
    resume_document_id: Optional[str] = None


class MatchSummary(BaseModel):
    considered: int
    strong: int     # score >= 80
    potential: int  # score >= 60


class CandidateMatchList(BaseModel):
    job: JobOut
    summary: MatchSummary
    total: int
    items: List[CandidateMatchItem]
    disclaimer: str = DISCLAIMER


class JobMatchItem(BaseModel):
    job: JobOut
    match: MatchDetail
    applied: bool
    application_stage: Optional[str] = None


class WeightsOut(BaseModel):
    weights: Dict[str, float]
    defaults: Dict[str, float]
    labels: Dict[str, str]


class WeightsIn(BaseModel):
    weights: Dict[str, float]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _hiring_job(db: Session, ctx: TenantContext, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None or not (ctx.is_super_admin or (ctx.is_org_member and job.organization_id == ctx.org_id)):
        raise HTTPException(status_code=404, detail="Job requisition not found")
    return job


def _detail(row: Match) -> MatchDetail:
    return MatchDetail(**matching.result_from_row(row))


def _latest_resume_ids(db: Session, candidate_ids: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for r in db.query(Resume).filter(Resume.candidate_id.in_(candidate_ids), Resume.document_id.isnot(None)).order_by(Resume.created_at):
        out[r.candidate_id] = r.document_id  # later rows overwrite earlier ones
    return out


def _items(db: Session, ctx: TenantContext, job: Job, rows: List[Match]) -> List[CandidateMatchItem]:
    ids = [r.candidate_id for r in rows]
    visible = candidate_service.contact_visible_ids(db, ctx, ids)
    apps = {a.candidate_id: a for a in db.query(Application).filter(Application.job_id == job.id, Application.candidate_id.in_(ids))}
    resumes = _latest_resume_ids(db, [i for i in ids if i in visible])
    return [
        CandidateMatchItem(
            candidate=candidate_service.to_summary(r.candidate, r.candidate_id in visible),
            match=_detail(r),
            status=r.status,
            application=ApplicationRef(id=apps[r.candidate_id].id, stage=apps[r.candidate_id].stage) if r.candidate_id in apps else None,
            resume_document_id=resumes.get(r.candidate_id),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Candidates for a job
# ---------------------------------------------------------------------------
@router.get("/jobs/{job_id}/candidates", response_model=CandidateMatchList)
def candidates_for_job(
    job_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("candidates:search_pool")),
    min_score: int = Query(0, ge=0, le=100),
    skills: Optional[List[str]] = Query(None),
    location: Optional[str] = Query(None, max_length=100),
    min_experience: Optional[float] = Query(None, ge=0),
    max_experience: Optional[float] = Query(None, ge=0),
    education: Optional[str] = Query(None, max_length=64),
    availability: Optional[str] = Query(None),
    max_salary: Optional[int] = Query(None, ge=0),
    remote_preference: Optional[str] = Query(None),
    status: Literal["active", "new", "shortlisted", "dismissed", "all"] = Query("active", description="active = not dismissed"),
    sort: Literal["score", "experience", "active", "recent"] = Query("score"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    job = _hiring_job(db, ctx, job_id)
    pool = candidate_service.filter_candidates(
        scope_candidates(db.query(CandidateProfile), ctx),
        skills=skills, location=location, min_experience=min_experience, max_experience=max_experience,
        availability=availability, remote_preference=remote_preference, max_salary=max_salary, education=education,
    ).all()
    rows = list(matching.ensure_matches(db, job, pool).values())
    db.commit()

    summary = matching.summarize([r for r in rows if r.status != "dismissed"])
    if status == "active":
        rows = [r for r in rows if r.status != "dismissed"]
    elif status != "all":
        rows = [r for r in rows if r.status == status]
    rows = [r for r in rows if r.score >= min_score]
    keys = {
        "score": lambda r: (r.score, r.candidate.experience_years or 0),
        "experience": lambda r: (r.candidate.experience_years or 0, r.score),
        "active": lambda r: (r.candidate.last_active_at or datetime.min, r.score),
        "recent": lambda r: (r.candidate.created_at or datetime.min, r.score),
    }
    rows.sort(key=keys[sort], reverse=True)
    page = rows[offset: offset + limit]
    return CandidateMatchList(job=get_job_out(job), summary=MatchSummary(**summary), total=len(rows), items=_items(db, ctx, job, page))


@router.get("/jobs/{job_id}/candidates/{candidate_id}", response_model=CandidateMatchItem)
def explain_match(
    job_id: str, candidate_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("candidates:search_pool")),
):
    job = _hiring_job(db, ctx, job_id)
    cand = get_visible_candidate(db, ctx, candidate_id)
    row = matching.ensure_matches(db, job, [cand])[cand.id]
    db.commit()
    return _items(db, ctx, job, [row])[0]


@router.post("/jobs/{job_id}/refresh", response_model=MatchSummary)
def refresh_matches(job_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_permission("candidates:search_pool"))):
    """Recompute every match for this job (e.g. after changing weights or the skill ontology)."""
    job = _hiring_job(db, ctx, job_id)
    pool = scope_candidates(db.query(CandidateProfile), ctx).all()
    rows = list(matching.ensure_matches(db, job, pool, force=True).values())
    db.commit()
    return MatchSummary(**matching.summarize([r for r in rows if r.status != "dismissed"]))


def _decide(db: Session, ctx: TenantContext, job_id: str, candidate_id: str) -> tuple:
    ctx.require("applications:advance_stage")
    job = _hiring_job(db, ctx, job_id)
    cand = get_visible_candidate(db, ctx, candidate_id)
    row = matching.ensure_matches(db, job, [cand])[cand.id]
    app = db.query(Application).filter(Application.job_id == job.id, Application.candidate_id == cand.id).first()
    return job, cand, row, app


@router.post("/jobs/{job_id}/candidates/{candidate_id}/shortlist", response_model=CandidateMatchItem)
def shortlist(job_id: str, candidate_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    """A recruiter's decision: add the candidate to the pipeline in the Shortlisted stage."""
    job, cand, row, app = _decide(db, ctx, job_id, candidate_id)
    if app is None:
        app = Application(
            id=f"app_{uuid.uuid4().hex[:8]}", job_id=job.id, candidate_id=cand.id,
            organization_id=job.organization_id, source="sourced", match_score=row.score, stage="Applied",
            cover_note="Shortlisted from Talent Match",
        )
        db.add(app)
        job.applicants_count = (job.applicants_count or 0) + 1
        db.flush()
        emit(db, "application.created", organization_id=job.organization_id, actor=ctx.user,
             payload={"application_id": app.id, "job_id": job.id, "candidate_id": cand.id, "match_score": row.score, "source": "sourced"})
    move_application(db, app, "Shortlisted", ctx.user, "Shortlisted from Talent Match")
    row.status = "shortlisted"
    db.commit()
    log_audit_event(db=db, action="MATCH_SHORTLISTED", module="Matching", entity="Application", entity_id=app.id,
                    user_id=ctx.user.id, user_email=ctx.user.email, organization_id=job.organization_id,
                    details={"job_id": job.id, "candidate_id": cand.id, "score": row.score})
    return _items(db, ctx, job, [row])[0]


@router.post("/jobs/{job_id}/candidates/{candidate_id}/reject", response_model=CandidateMatchItem)
def reject(job_id: str, candidate_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    """Applicants move to the rejected stage (and are told); non-applicants are only hidden from this list."""
    job, cand, row, app = _decide(db, ctx, job_id, candidate_id)
    if app is not None:
        rejected = next((s.name for s in get_stages(db, job.organization_id) if s.kind == "rejected"), "Rejected")
        move_application(db, app, rejected, ctx.user, "Rejected from Talent Match")
    row.status = "dismissed"
    db.commit()
    log_audit_event(db=db, action="MATCH_REJECTED", module="Matching", entity="Match", entity_id=row.id,
                    user_id=ctx.user.id, user_email=ctx.user.email, organization_id=job.organization_id,
                    details={"job_id": job.id, "candidate_id": cand.id, "had_application": app is not None})
    return _items(db, ctx, job, [row])[0]


@router.post("/jobs/{job_id}/candidates/{candidate_id}/restore", response_model=CandidateMatchItem)
def restore(job_id: str, candidate_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    """Undo a dismissal (an application that was rejected stays rejected until moved)."""
    job, _, row, _ = _decide(db, ctx, job_id, candidate_id)
    if row.status == "dismissed":
        row.status = "new"
    db.commit()
    return _items(db, ctx, job, [row])[0]


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------
@router.get("/weights", response_model=WeightsOut)
def get_weights(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    if not ctx.is_org_member:
        raise HTTPException(status_code=403, detail="Matching weights belong to organizations")
    return WeightsOut(weights=matching.get_weights(db.get(Organization, ctx.org_id)), defaults=DEFAULT_WEIGHTS, labels=FACTOR_LABELS)


@router.put("/weights", response_model=WeightsOut)
def put_weights(payload: WeightsIn, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    if not ctx.is_org_admin:
        raise HTTPException(status_code=403, detail="Organization admin access required")
    org = db.get(Organization, ctx.org_id)
    weights = matching.set_weights(db, org, payload.weights)
    log_audit_event(db=db, action="MATCH_WEIGHTS_UPDATED", module="Matching", entity="Organization", entity_id=org.id,
                    user_id=ctx.user.id, user_email=ctx.user.email, organization_id=org.id, details={"weights": weights})
    return WeightsOut(weights=weights, defaults=DEFAULT_WEIGHTS, labels=FACTOR_LABELS)


# ---------------------------------------------------------------------------
# Jobs for the signed-in candidate
# ---------------------------------------------------------------------------
@router.get("/me/jobs", response_model=List[JobMatchItem])
def my_job_matches(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant),
    min_score: int = Query(0, ge=0, le=100),
    limit: int = Query(20, ge=1, le=100),
):
    cand = ctx.user.candidate_profile
    if not ctx.is_candidate or cand is None:
        raise HTTPException(status_code=403, detail="Job matches are for candidates")
    jobs = db.query(Job).filter(Job.status == "Active").all()
    apps = {a.job_id: a for a in db.query(Application).filter(Application.candidate_id == cand.id)}
    rows = matching.ensure_matches_for_candidate(db, cand, jobs)
    items = []
    for job in jobs:
        row = rows[job.id]
        if row.score >= min_score:
            app = apps.get(job.id)
            items.append(JobMatchItem(job=get_job_out(job), match=_detail(row), applied=app is not None,
                                      application_stage=app.stage if app else None))
    db.commit()
    items.sort(key=lambda i: i.match.score, reverse=True)
    return items[:limit]
