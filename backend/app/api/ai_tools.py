from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.tenancy import (
    TenantContext, get_tenant, require_permission,
    get_visible_candidate, get_visible_job, get_managed_job, get_org_application
)
from app.models.schemas import (
    OutreachPitchRequest, OutreachPitchResponse,
    ResumeTailorRequest, ResumeTailorResponse,
    InterviewPrepRequest, InterviewPrepResponse,
    JobSpecGenerateRequest, JobSpecGenerateResponse,
    AutoScreenApplicationResponse,
    AutonomousSourcingRequest, AutonomousSourcingResponse,
    MockInterviewGradeRequest, MockInterviewGradeResponse,
    JobSpecOptimizeRequest, JobSpecOptimizeResponse,
    LearningRoadmapRequest, LearningRoadmapResponse
)
from app.services.ai_copilot_service import (
    generate_outreach_pitch_db, tailor_resume_db,
    generate_interview_prep_db,
    auto_screen_application_db, autonomous_sourcing_db,
    grade_mock_interview_db, optimize_job_spec_db,
    generate_learning_roadmap_db
)

# Every AI tool requires a signed-in user, and checks access to the records it reads.
router = APIRouter(prefix="/ai", tags=["AI Copilot & Automation"], dependencies=[Depends(get_tenant)])

@router.post("/generate-outreach", response_model=OutreachPitchResponse)
def generate_outreach(
    payload: OutreachPitchRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("candidates:search_pool"))
):
    get_visible_candidate(db, ctx, payload.candidate_id)
    get_managed_job(db, ctx, payload.job_id)
    return generate_outreach_pitch_db(
        db=db,
        candidate_id=payload.candidate_id,
        job_id=payload.job_id,
        tone=payload.tone
    )

@router.post("/tailor-resume", response_model=ResumeTailorResponse)
def tailor_resume(payload: ResumeTailorRequest, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    candidate_id = payload.candidate_id or ctx.candidate_id or ""
    if candidate_id:
        get_visible_candidate(db, ctx, candidate_id)
    if payload.target_job_id:
        get_visible_job(db, ctx, payload.target_job_id)
    return tailor_resume_db(
        db=db,
        candidate_id=candidate_id,
        resume_text=payload.resume_text or "",
        target_job_id=payload.target_job_id
    )

@router.post("/interview-prep", response_model=InterviewPrepResponse)
def get_interview_prep(payload: InterviewPrepRequest, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    get_visible_candidate(db, ctx, payload.candidate_id)
    get_visible_job(db, ctx, payload.job_id)
    return generate_interview_prep_db(
        db=db,
        candidate_id=payload.candidate_id,
        job_id=payload.job_id
    )

@router.post(
    "/generate-job-spec",
    response_model=JobSpecGenerateResponse,
    dependencies=[Depends(require_permission("jobs:create_edit"))],
)
def generate_job_spec(payload: JobSpecGenerateRequest, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    """Legacy shape over the real generator (/ai/jobs/generate)."""
    from app.ai.features import generate_job

    brief = payload.prompt or payload.title or "Software Engineer"
    draft = generate_job(db, brief, user=ctx.user, organization_id=ctx.org_id).data
    return JobSpecGenerateResponse(
        title=draft.title, department=draft.department or payload.department or "Engineering",
        description=draft.description, key_responsibilities=draft.responsibilities, responsibilities=draft.responsibilities,
        required_skills=draft.required_skills, preferred_skills=draft.preferred_skills,
        min_experience_years=draft.min_experience_years, salary_min=draft.salary_min or 0, salary_max=draft.salary_max or 0,
        equity="", benefits=[],
    )


@router.post("/auto-screen-application/{application_id}", response_model=AutoScreenApplicationResponse)
def auto_screen_application(
    application_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("applications:view_tenant"))
):
    get_org_application(db, ctx, application_id)
    return auto_screen_application_db(db=db, application_id=application_id)

@router.post("/autonomous-sourcing", response_model=AutonomousSourcingResponse)
def autonomous_sourcing(
    payload: AutonomousSourcingRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("candidates:search_pool"))
):
    get_managed_job(db, ctx, payload.job_id)
    return autonomous_sourcing_db(
        db=db,
        job_id=payload.job_id,
        target_count=payload.target_count,
        tone=payload.tone
    )

@router.post("/mock-interview/grade-answer", response_model=MockInterviewGradeResponse)
def grade_mock_interview_answer(payload: MockInterviewGradeRequest):
    return grade_mock_interview_db(
        question=payload.question,
        category=payload.category,
        candidate_answer=payload.candidate_answer,
        job_title=payload.job_title or "",
        target_company=payload.target_company or "Top-tier Tech"
    )

@router.post(
    "/optimize-job-spec",
    response_model=JobSpecOptimizeResponse,
    dependencies=[Depends(require_permission("jobs:create_edit"))],
)
def optimize_job_spec(payload: JobSpecOptimizeRequest):
    return optimize_job_spec_db(
        raw_job_description=payload.raw_job_description or payload.draft_spec or "",
        job_title=payload.job_title,
        industry=payload.industry or "Software & AI"
    )

@router.post("/learning-roadmap", response_model=LearningRoadmapResponse)
def generate_learning_roadmap(payload: LearningRoadmapRequest, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    get_visible_candidate(db, ctx, payload.candidate_id)
    get_visible_job(db, ctx, payload.target_job_id)
    return generate_learning_roadmap_db(
        db=db,
        candidate_id=payload.candidate_id,
        target_job_id=payload.target_job_id
    )
