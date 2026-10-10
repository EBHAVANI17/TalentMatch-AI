import json
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.tenancy import (
    TenantContext, get_tenant, scope_applications, get_visible_job,
    get_visible_candidate, get_visible_application, get_org_application
)
from app.models.db_models import Application, ApplicationStageHistory
from app.models.schemas import (
    ApplicationOut, ApplicationSubmitRequest, ApplicationStageUpdateRequest
)
from app.services.recommender_service import calculate_match
from app.events import emit
from app.services.pipeline_service import move_application
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/applications", tags=["Applications Pipeline"])

def get_app_out(application: Application) -> ApplicationOut:
    app: Any = application
    job = app.job
    cand = app.candidate
    data: Dict[str, Any] = {
        "id": app.id,
        "job_id": app.job_id,
        "job_title": job.title if job else "Engineering Role",
        "company_name": job.organization.name if job and job.organization else "Enterprise Tech",
        "company_logo": job.organization.logo_icon if job and job.organization else "briefcase",
        "candidate_id": app.candidate_id,
        "candidate_name": cand.user.full_name if cand and cand.user else "Candidate",
        "candidate_email": cand.user.email if cand and cand.user else "",
        "candidate_title": cand.title if cand else "Software Engineer",
        "candidate_avatar": cand.user.avatar_url if cand and cand.user else "",
        "candidate_location": cand.location if cand else "Remote",
        "candidate_skills": cand.skills if cand else [],
        "candidate_experience_years": cand.experience_years if cand else 3.0,
        "match_score": app.match_score,
        "stage": app.stage,
        "cover_note": app.cover_note,
        "score_breakdown": app.score_breakdown,
        "applied_date": app.created_at.strftime("%Y-%m-%d") if app.created_at else "",
        "organization_id": app.organization_id,
        "source": app.source or "applied",
        "created_at": app.created_at,
        "updated_at": app.updated_at,
    }
    return ApplicationOut.model_validate(data)


@router.get("", response_model=List[ApplicationOut])
def get_applications(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant),
    candidate_id: Optional[str] = Query(None),
    job_id: Optional[str] = Query(None),
    stage: Optional[str] = Query(None)
):
    query = scope_applications(db.query(Application), ctx)
    if candidate_id:
        query = query.filter(Application.candidate_id == candidate_id)
    if job_id:
        query = query.filter(Application.job_id == job_id)
    if stage and stage != "all":
        query = query.filter(Application.stage == stage)
    apps = query.order_by(Application.created_at.desc()).all()
    return [get_app_out(a) for a in apps]

@router.post("", response_model=ApplicationOut)
@router.post("/apply", response_model=ApplicationOut)
def apply_to_job(
    payload: ApplicationSubmitRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant)
):
    current_user = ctx.user
    job = get_visible_job(db, ctx, payload.job_id)

    if ctx.is_candidate:
        # Candidates can only apply as themselves.
        candidate = current_user.candidate_profile
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate profile not found")
        if payload.candidate_id and payload.candidate_id != candidate.id:
            raise HTTPException(status_code=403, detail="Candidates can only apply with their own profile")
    else:
        # Hiring side adds a candidate to one of its own organization's jobs.
        ctx.require("applications:advance_stage")
        if not ctx.is_super_admin and job.organization_id != ctx.org_id:
            raise HTTPException(status_code=404, detail="Job requisition not found")
        if not payload.candidate_id:
            raise HTTPException(status_code=400, detail="candidate_id is required")
        candidate = get_visible_candidate(db, ctx, payload.candidate_id)

    # Check existing application
    existing = db.query(Application).filter(
        Application.job_id == job.id,
        Application.candidate_id == candidate.id
    ).first()
    if existing:
        return get_app_out(existing)

    score, exp = calculate_match(candidate, job)
    app_id = f"app_{uuid.uuid4().hex[:8]}"

    app = Application(
        id=app_id,
        job_id=job.id,
        candidate_id=candidate.id,
        organization_id=job.organization_id,
        source="applied" if ctx.is_candidate else "sourced",
        match_score=score,
        stage="Applied",
        cover_note=payload.cover_note or "Applied via 1-Click Autonomous Match",
        score_breakdown_json=json.dumps(exp.breakdown.dict() if hasattr(exp.breakdown, 'dict') else exp.breakdown)
    )
    db.add(app)

    # Applicant count is recomputed by the database (candidates can't update jobs under RLS)
    from app.db.functions import refresh_applicants_count
    refresh_applicants_count(db, job.id)
    emit(db, "application.created", organization_id=str(job.organization_id) if job.organization_id else None, actor=current_user, payload={
        "application_id": app_id, "job_id": job.id, "candidate_id": candidate.id,
        "match_score": score, "source": app.source,
    })
    db.commit()  # notifications are sent by app/events/handlers.py once this commits
    db.refresh(app)

    log_audit_event(
        db=db,
        action="APPLICATION_SUBMITTED",
        module="Applications",
        entity="Application",
        entity_id=str(app.id),
        user_id=str(current_user.id) if current_user.id else None,
        user_email=str(current_user.email),
        organization_id=str(job.organization_id) if job.organization_id else None,
        details={"job_id": str(job.id), "match_score": score}
    )

    return get_app_out(app)

@router.patch("/{app_id}/stage", response_model=ApplicationOut)
def update_application_stage(
    app_id: str,
    payload: ApplicationStageUpdateRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant)
):
    ctx.require("applications:advance_stage")
    current_user = ctx.user
    app = get_org_application(db, ctx, app_id)

    old_stage = app.stage
    if not move_application(db, app, payload.stage, current_user, payload.reason or ""):
        return get_app_out(app)  # already in that stage
    db.commit()  # history + application.stage_changed event are saved together
    db.refresh(app)

    log_audit_event(
        db=db,
        action="STAGE_UPDATED",
        module="Applications",
        entity="Application",
        entity_id=str(app.id),
        user_id=str(current_user.id) if current_user.id else None,
        user_email=str(current_user.email),
        organization_id=str(app.job.organization_id) if app.job and app.job.organization_id else None,
        details={"old_stage": old_stage, "new_stage": app.stage, "reason": payload.reason}
    )

    return get_app_out(app)

@router.get("/{app_id}/history")
def get_application_stage_history(
    app_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant)
):
    get_visible_application(db, ctx, app_id)
    history = db.query(ApplicationStageHistory).filter(ApplicationStageHistory.application_id == app_id).order_by(ApplicationStageHistory.created_at.asc()).all()
    return history

