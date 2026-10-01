"""AI drafting endpoints. Every response is a draft with `method` ("ai" or "rules") and a `notice`
the UI must show; nothing is saved until the user reviews and submits it through the normal APIs."""
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.adapters.storage import get_storage
from app.ai import features
from app.ai.schemas import BriefIn, ContactInfo, JobAnalysis, JobDraft, JobTextIn, ResumeDraft
from app.core.database import get_db
from app.core.tenancy import TenantContext, get_tenant, get_visible_candidate, is_own_candidate_profile, require_permission
from app.events import emit
from app.models.db_models import AIRequest, Organization
from app.services import document_service
from app.services.audit_service import log_audit_event
from app.services.text_extraction import UnreadableDocument, extract_text

router = APIRouter(prefix="/ai", tags=["AI Drafting"])


class AIMeta(BaseModel):
    method: str  # ai | rules
    provider: str
    model: str
    notice: str
    request_id: str


class ResumeParseResult(AIMeta):
    document_id: str
    resume_id: Optional[str] = None
    candidate_id: Optional[str] = None
    contact: ContactInfo
    draft: ResumeDraft


class JobDraftResult(AIMeta):
    draft: JobDraft


class JobAnalysisResult(AIMeta):
    analysis: JobAnalysis


@router.post("/resume/parse", response_model=ResumeParseResult)
async def parse_resume(
    file: UploadFile = File(...),
    candidate_id: Optional[str] = Form(None, description="A candidate your organization added; omit to parse your own resume, or to prepare a new candidate"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant),
):
    """Store a resume file and return a draft profile extracted from it, for review.

    - Candidates: the file is attached to their own profile; the draft is NOT applied until they save it.
    - Recruiters: with candidate_id (a candidate they added) it is attached to that profile; without it,
      the file is kept for the organization and can be linked when creating the candidate
      (POST /candidates with resume_document_id).
    """
    from app.api.resumes import safe_filename

    candidate = None
    if ctx.is_candidate:
        candidate = ctx.user.candidate_profile
        if candidate is None or (candidate_id and candidate_id != candidate.id):
            raise HTTPException(status_code=403, detail="You can only parse resumes for your own profile")
    elif ctx.is_org_member and ctx.has("candidates:search_pool"):
        if candidate_id:
            candidate = get_visible_candidate(db, ctx, candidate_id)
            if candidate.owner_org_id != ctx.org_id:
                raise HTTPException(status_code=403, detail="You can only attach resumes to candidates your organization added")
    elif not ctx.is_super_admin:
        raise HTTPException(status_code=403, detail="Not allowed")

    data = await file.read()
    filename = safe_filename(file.filename or "resume.pdf")
    org_id = candidate.owner_org_id if candidate else (ctx.org_id if ctx.is_org_member else None)
    document = document_service.store_file(db, data=data, filename=filename, kind="resume", uploaded_by=ctx.user,
                                           candidate=candidate, organization_id=org_id)
    try:
        text = extract_text(filename, data)
    except UnreadableDocument as exc:
        db.rollback()
        get_storage().delete(document.storage_key)
        raise HTTPException(status_code=422, detail=str(exc))
    db.flush()

    known = [candidate.user.full_name] if candidate and candidate.user else []
    contact, outcome = features.parse_resume_text(db, text, user=ctx.user, organization_id=ctx.org_id,
                                                  input_ref=f"document:{document.id}", known_names=known)
    resume = None
    if candidate is not None:
        resume = features.save_resume(db, candidate=candidate, document=document, text=text, draft=outcome.data)
        emit(db, "candidate.updated", organization_id=candidate.owner_org_id, actor=ctx.user,
             payload={"candidate_id": candidate.id, "fields": ["resume"]})
    db.commit()
    log_audit_event(db=db, action="RESUME_PARSED", module="AI", entity="Document", entity_id=document.id,
                    user_id=ctx.user.id, user_email=ctx.user.email, organization_id=ctx.org_id,
                    details={"method": outcome.method, "provider": outcome.provider, "candidate_id": candidate.id if candidate else None})
    return ResumeParseResult(
        **features.outcome_meta(outcome), document_id=document.id, resume_id=resume.id if resume else None,
        candidate_id=candidate.id if candidate else None, contact=contact, draft=outcome.data,
    )


@router.post("/jobs/generate", response_model=JobDraftResult)
def generate_job(payload: BriefIn, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_permission("jobs:create_edit"))):
    """Draft a full job description from a short brief, e.g. "Senior Backend Developer, 5+ years, Node.js, AWS"."""
    outcome = features.generate_job(db, payload.brief, user=ctx.user, organization_id=ctx.org_id)
    return JobDraftResult(**features.outcome_meta(outcome), draft=outcome.data)


@router.post("/jobs/analyze", response_model=JobAnalysisResult)
def analyze_job(payload: JobTextIn, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_permission("jobs:create_edit"))):
    """Turn a pasted job description into structured requirements."""
    outcome = features.analyze_job(db, payload.text, user=ctx.user, organization_id=ctx.org_id)
    return JobAnalysisResult(**features.outcome_meta(outcome), analysis=outcome.data)


# ---------------------------------------------------------------------------
# Usage (organization view)
# ---------------------------------------------------------------------------
class UsageRow(BaseModel):
    feature: str
    status: str
    requests: int
    credits: int
    tokens: int


class UsageSummary(BaseModel):
    credits_used: int
    credits_limit: int
    period_start: datetime
    rows: List[UsageRow]
    providers_configured: bool


@router.get("/usage", response_model=UsageSummary)
def usage(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    """AI usage for your organization this month."""
    if not ctx.is_org_member:
        raise HTTPException(status_code=403, detail="Usage is reported per organization")
    from app.adapters.llm import get_llm_router

    start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = (
        db.query(AIRequest.feature, AIRequest.status, func.count(AIRequest.id), func.coalesce(func.sum(AIRequest.credits), 0),
                 func.coalesce(func.sum(AIRequest.input_tokens + AIRequest.output_tokens), 0))
        .filter(AIRequest.organization_id == ctx.org_id, AIRequest.created_at >= start)
        .group_by(AIRequest.feature, AIRequest.status).all()
    )
    org = db.get(Organization, ctx.org_id)
    return UsageSummary(
        credits_used=org.monthly_ai_credits_used or 0, credits_limit=org.monthly_ai_credits or 0, period_start=start,
        rows=[UsageRow(feature=f, status=s, requests=n, credits=int(c), tokens=int(t)) for f, s, n, c, t in rows],
        providers_configured=get_llm_router().available,
    )
