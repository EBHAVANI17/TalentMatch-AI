import json
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user, get_current_user_optional
from app.models.db_models import Application, Job, CandidateProfile, User
from app.models.schemas import (
    ApplicationOut, ApplicationSubmitRequest, ApplicationStageUpdateRequest
)
from app.services.recommender_service import calculate_match
from app.services.notification_service import create_notification
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/applications", tags=["Applications Pipeline"])

def get_app_out(app: Application) -> ApplicationOut:
    job = app.job
    cand = app.candidate
    return ApplicationOut(
        id=app.id,
        job_id=app.job_id,
        job_title=job.title if job else "Engineering Role",
        company_name=job.organization.name if job and job.organization else "Enterprise Tech",
        company_logo=job.organization.logo_icon if job and job.organization else "briefcase",
        candidate_id=app.candidate_id,
        candidate_name=cand.user.full_name if cand and cand.user else "Candidate",
        candidate_email=cand.user.email if cand and cand.user else "",
        candidate_title=cand.title if cand else "Software Engineer",
        candidate_avatar=cand.user.avatar_url if cand and cand.user else "",
        candidate_location=cand.location if cand else "Remote",
        candidate_skills=cand.skills if cand else [],
        candidate_experience_years=cand.experience_years if cand else 3.0,
        match_score=app.match_score,
        stage=app.stage,
        cover_note=app.cover_note,
        score_breakdown=app.score_breakdown,
        applied_date=app.created_at.strftime("%Y-%m-%d"),
        created_at=app.created_at
    )


@router.get("", response_model=List[ApplicationOut])
def get_applications(
    db: Session = Depends(get_db),
    candidate_id: Optional[str] = Query(None),
    job_id: Optional[str] = Query(None),
    stage: Optional[str] = Query(None)
):
    query = db.query(Application)
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
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    job = db.query(Job).filter(Job.id == payload.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job requisition not found")

    candidate = None
    if payload.candidate_id:
        candidate = db.query(CandidateProfile).filter(CandidateProfile.id == payload.candidate_id).first()
    elif current_user and current_user.candidate_profile:
        candidate = current_user.candidate_profile
    
    if not candidate:
        candidate = db.query(CandidateProfile).first()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found")

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
        match_score=score,
        stage="Applied",
        cover_note=payload.cover_note or "Applied via 1-Click Autonomous Match",
        score_breakdown_json=json.dumps(exp.breakdown.dict() if hasattr(exp.breakdown, 'dict') else exp.breakdown)
    )
    db.add(app)
    
    # Increment applicant count on job
    job.applicants_count += 1
    db.commit()
    db.refresh(app)

    # Trigger In-App Notification
    if candidate.user_id:
        create_notification(
            db=db,
            user_id=candidate.user_id,
            title=f"Application Sent: {job.title}",
            message=f"Your profile matched with {score}% fit and has been dispatched to {job.organization.name if job.organization else 'the employer'}.",
            notif_type="application",
            link="/applications"
        )

    log_audit_event(
        db=db,
        action="APPLICATION_SUBMITTED",
        module="Applications",
        entity="Application",
        entity_id=app.id,
        user_id=current_user.id if current_user else None,
        user_email=current_user.email if current_user else "anonymous",
        details={"job_id": job.id, "match_score": score}
    )

    return get_app_out(app)

@router.patch("/{app_id}/stage", response_model=ApplicationOut)
def update_application_stage(
    app_id: str,
    payload: ApplicationStageUpdateRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    from app.models.db_models import ApplicationStageHistory

    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application record not found")

    old_stage = app.stage
    app.stage = payload.stage
    
    # Record stage history
    history_entry = ApplicationStageHistory(
        id=f"hist_{uuid.uuid4().hex[:8]}",
        application_id=app.id,
        from_stage=old_stage,
        to_stage=payload.stage,
        reason=payload.reason or "Stage advanced"
    )
    db.add(history_entry)
    db.commit()
    db.refresh(app)

    # Notify candidate of stage change
    if app.candidate and app.candidate.user_id:
        create_notification(
            db=db,
            user_id=app.candidate.user_id,
            title=f"Pipeline Update: {app.job.title if app.job else 'Requisition'}",
            message=f"Your application status was moved from {old_stage} to {payload.stage}.",
            notif_type="stage_change",
            link="/applications"
        )

    log_audit_event(
        db=db,
        action="STAGE_UPDATED",
        module="Applications",
        entity="Application",
        entity_id=app.id,
        user_id=current_user.id if current_user else None,
        user_email=current_user.email if current_user else "anonymous",
        details={"old_stage": old_stage, "new_stage": payload.stage, "reason": payload.reason}
    )

    return get_app_out(app)

@router.get("/{app_id}/history")
def get_application_stage_history(app_id: str, db: Session = Depends(get_db)):
    from app.models.db_models import ApplicationStageHistory
    history = db.query(ApplicationStageHistory).filter(ApplicationStageHistory.application_id == app_id).order_by(ApplicationStageHistory.created_at.asc()).all()
    return history

