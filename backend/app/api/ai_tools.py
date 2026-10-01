from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
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
    generate_interview_prep_db, generate_job_spec_db,
    auto_screen_application_db, autonomous_sourcing_db,
    grade_mock_interview_db, optimize_job_spec_db,
    generate_learning_roadmap_db
)

router = APIRouter(prefix="/ai", tags=["AI Copilot & Automation"])

@router.post("/generate-outreach", response_model=OutreachPitchResponse)
def generate_outreach(payload: OutreachPitchRequest, db: Session = Depends(get_db)):
    return generate_outreach_pitch_db(
        db=db,
        candidate_id=payload.candidate_id,
        job_id=payload.job_id,
        tone=payload.tone
    )

@router.post("/tailor-resume", response_model=ResumeTailorResponse)
def tailor_resume(payload: ResumeTailorRequest, db: Session = Depends(get_db)):
    return tailor_resume_db(
        db=db,
        candidate_id=payload.candidate_id or "",
        resume_text=payload.resume_text or "",
        target_job_id=payload.target_job_id
    )

@router.post("/interview-prep", response_model=InterviewPrepResponse)
def get_interview_prep(payload: InterviewPrepRequest, db: Session = Depends(get_db)):
    return generate_interview_prep_db(
        db=db,
        candidate_id=payload.candidate_id,
        job_id=payload.job_id
    )

@router.post("/generate-job-spec", response_model=JobSpecGenerateResponse)
def generate_job_spec(payload: JobSpecGenerateRequest):
    query_prompt = payload.prompt or payload.title or "Staff Software Engineer"
    return generate_job_spec_db(
        prompt=query_prompt,
        department=payload.department or "Engineering",
        workplace_type=payload.workplace_type or "Remote"
    )


@router.post("/auto-screen-application/{application_id}", response_model=AutoScreenApplicationResponse)
def auto_screen_application(application_id: str, db: Session = Depends(get_db)):
    return auto_screen_application_db(db=db, application_id=application_id)

@router.post("/autonomous-sourcing", response_model=AutonomousSourcingResponse)
def autonomous_sourcing(payload: AutonomousSourcingRequest, db: Session = Depends(get_db)):
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
        job_title=payload.job_title,
        target_company=payload.target_company or "Top-tier Tech"
    )

@router.post("/optimize-job-spec", response_model=JobSpecOptimizeResponse)
def optimize_job_spec(payload: JobSpecOptimizeRequest):
    return optimize_job_spec_db(
        raw_job_description=payload.raw_job_description,
        job_title=payload.job_title,
        industry=payload.industry or "Software & AI"
    )

@router.post("/learning-roadmap", response_model=LearningRoadmapResponse)
def generate_learning_roadmap(payload: LearningRoadmapRequest, db: Session = Depends(get_db)):
    return generate_learning_roadmap_db(
        db=db,
        candidate_id=payload.candidate_id,
        target_job_id=payload.target_job_id
    )
