from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.schemas import JobMatchResult, CandidateMatchResult
from app.services.recommender_service import (
    recommend_jobs_for_candidate_db, recommend_candidates_for_job_db
)

router = APIRouter(prefix="/recommendations", tags=["AI Autonomous Recommendations"])

@router.get("/jobs-for-candidate/{candidate_id}", response_model=List[JobMatchResult])
def get_jobs_for_candidate(candidate_id: str, db: Session = Depends(get_db)):
    return recommend_jobs_for_candidate_db(db, candidate_id)

@router.get("/candidates-for-job/{job_id}", response_model=List[CandidateMatchResult])
def get_candidates_for_job(job_id: str, db: Session = Depends(get_db)):
    return recommend_candidates_for_job_db(db, job_id)
