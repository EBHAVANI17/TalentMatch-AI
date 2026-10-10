from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.db_models import CandidateProfile, Job
from app.models.schemas import (
    JobOut, CandidateProfileOut, MatchExplanation, ScoreBreakdown,
    SkillRecommendation, JobMatchResult, CandidateMatchResult
)

def build_skill_recommendations(missing_skills: List[str]) -> List[SkillRecommendation]:
    recs = []
    learning_guide = {
        "Docker": ("Cloud & DevOps", "Master multi-stage production Docker builds & zero-root container security", "2-3 weeks"),
        "Kubernetes": ("Cloud & DevOps", "Complete hands-on Certified Kubernetes Application Developer (CKAD) path", "4-6 weeks"),
        "Vector Databases": ("Data & AI", "Architect scalable HNSW indexing with pgvector, Qdrant & Pinecone", "1-2 weeks"),
        "LLMs & RAG": ("Data & AI", "Build low-latency hybrid search pipelines and fine-tune reasoning models", "3-4 weeks"),
        "CUDA & GPU Optimization": ("Data & AI", "Write custom Triton / CUDA kernels for quantized transformer inference", "4-6 weeks"),
        "AWS": ("Cloud & DevOps", "AWS Certified Solutions Architect Associate & EKS mastery", "4-6 weeks"),
        "TypeScript": ("Languages", "Master advanced type-level programming, generics, and compiler ASTs", "2 weeks"),
        "Next.js": ("Frameworks", "Next.js App Router, SSR caching layers, and Server Actions Masterclass", "2-3 weeks"),
        "FastAPI": ("Frameworks", "High-throughput async Python services with background task workers", "1-2 weeks"),
        "Distributed Systems": ("Architecture", "Implement Raft consensus, distributed locking, and event-driven architectures", "4-6 weeks"),
        "Rust": ("Languages", "Master memory safety, async Tokio, and lock-free concurrency", "4-6 weeks"),
        "Go": ("Languages", "Build low-latency microservices with goroutines and atomic primitives", "2-3 weeks")
    }

    for skill in missing_skills:
        if skill in learning_guide:
            cat, action, est = learning_guide[skill]
        else:
            cat = "Engineering Competency"
            action = f"Complete guided projects and open-source contributions on {skill}"
            est = "2-4 weeks"

        recs.append(SkillRecommendation(
            skill=skill,
            category=cat,
            recommended_action=action,
            estimated_learning_time=est
        ))
    return recs

def calculate_match(candidate: CandidateProfile, job: Job, db: Optional[Session] = None) -> Tuple[int, MatchExplanation]:
    """Score with the v2 engine (app/matching) and return it in the original response shape."""
    from sqlalchemy.orm import object_session

    from app.matching.service import score_one

    sess = db or object_session(candidate) or object_session(job)
    if sess is not None:
        result = score_one(sess, job, candidate)
    else:
        from app.core.database import SessionLocal
        with SessionLocal() as fallback_db:
            result = score_one(fallback_db, job, candidate)

    by_key = {f.key: f for f in result.factors}

    def pct(key: str) -> float:
        f = by_key.get(key)
        return round((f.score or 0) * 100, 1) if f and f.applicable else 0.0

    matched = [e.skill for e in result.skills if e.score > 0]
    missing_required = [e.skill for e in result.skills if e.importance == "required" and e.score == 0]
    missing_preferred = [e.skill for e in result.skills if e.importance == "preferred" and e.score == 0]
    breakdown = ScoreBreakdown(
        skills_score=pct("skills"), experience_score=pct("experience"), location_score=pct("location"),
        salary_score=pct("salary"), education_score=pct("education"),
        skill_match_score=pct("skills"), experience_match_score=pct("experience"),
        location_match_score=pct("location"), salary_match_score=pct("salary"),
    )
    explanation = MatchExplanation(
        overall_match_percentage=result.score,
        fit_level=result.fit_level,
        strengths=result.strengths or ["No standout strengths against this job's criteria"],
        gaps=result.gaps or ["No significant gaps against this job's criteria"],
        breakdown=breakdown,
        score_breakdown=breakdown,
        missing_critical_skills=missing_required,
        missing_preferred_skills=missing_preferred,
        missing_skills=missing_required + missing_preferred,
        matched_skills=matched,
        recommendations_for_candidate=build_skill_recommendations(missing_required + missing_preferred),
        rationale=result.explanation,
    )
    return result.score, explanation

def get_job_out(job: Job) -> JobOut:
    j: Any = job
    # Organization members see their organization; candidates and visitors see the public profile
    org = j.organization or j.public_org
    posted = j.published_at or j.created_at
    posted_date = posted.strftime("%Y-%m-%d") if posted is not None else ""
    data: Dict[str, Any] = {
        "id": j.id,
        "organization_id": j.organization_id,
        "company_name": org.name if org else "Enterprise Tech",
        "company_domain": org.domain if org else "tech.io",
        "company_logo": org.logo_icon if org else "briefcase",
        "title": j.title,
        "department": j.department,
        "description": j.description,
        "key_responsibilities": j.responsibilities,
        "responsibilities": j.responsibilities,
        "required_skills": j.required_skills,
        "preferred_skills": j.preferred_skills,
        "min_experience_years": j.min_experience_years,
        "location": j.location,
        "workplace_type": j.workplace_type,
        "salary_min": j.salary_min,
        "salary_max": j.salary_max,
        "equity": j.equity,
        "required_education": j.required_education,
        "urgency": j.urgency or "",  # internal (job_private): empty for candidates and visitors
        "status": j.status,
        "benefits": j.benefits,
        "applicants_count": j.applicants_count,
        "employment_type": j.employment_type or "Full-time",
        "openings": j.openings or 1,
        "max_experience_years": j.max_experience_years,
        "seniority": j.seniority or "",
        "industry": j.industry or "",
        "application_deadline": j.application_deadline,
        "published_at": j.published_at,
        "closed_at": j.closed_at,
        "screening_questions": j.screening_questions,
        "interview_criteria": j.interview_criteria,
        "posted_date": posted_date,
        "created_at": j.created_at,
        "updated_at": j.updated_at,
    }
    return JobOut.model_validate(data)

def get_candidate_out(cand: CandidateProfile) -> CandidateProfileOut:
    c: Any = cand
    user = c.user
    data: Dict[str, Any] = {
        "id": c.id,
        "user_id": c.user_id,
        "name": user.full_name if user else "Candidate",
        "email": user.email if user else "",
        "title": c.title,
        "bio": c.bio,
        "skills": c.skills,
        "experience_years": c.experience_years,
        "location": c.location,
        "remote_preference": c.remote_preference,
        "expected_salary": c.expected_salary,
        "education": c.education,
        "github_url": c.github_url,
        "linkedin_url": c.linkedin_url,
        "portfolio_url": c.portfolio_url,
        "ats_score": c.ats_score,
        "profile_strength": c.profile_strength,
        "avatar_url": user.avatar_url if user else "",
    }
    return CandidateProfileOut.model_validate(data)

def recommend_jobs_for_candidate_db(db: Session, candidate_id: str) -> List[JobMatchResult]:
    candidate = db.query(CandidateProfile).filter(CandidateProfile.id == candidate_id).first()
    if not candidate:
        return []

    jobs = db.query(Job).filter(Job.status == "Active").all()
    results = []

    for j in jobs:
        score, explanation = calculate_match(candidate, j, db=db)
        results.append(JobMatchResult(
            job=get_job_out(j),
            match_score=score,
            fit_level=explanation.fit_level,
            explanation=explanation
        ))

    return sorted(results, key=lambda x: x.match_score, reverse=True)

def recommend_candidates_for_job_db(db: Session, job_id: str, candidate_query=None) -> List[CandidateMatchResult]:
    """Rank candidates for a job. Pass a tenant-scoped candidate_query to limit who is considered."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return []

    candidates = (candidate_query if candidate_query is not None else db.query(CandidateProfile)).all()
    results = []

    # Get existing applications for pipeline stages
    from app.models.db_models import Application
    apps: Dict[str, str] = {str(a.candidate_id): str(a.stage) for a in db.query(Application).filter(Application.job_id == job_id).all()}

    for c in candidates:
        score, explanation = calculate_match(c, job, db=db)
        stage = apps.get(str(c.id), "Sourced")
        results.append(CandidateMatchResult(
            candidate=get_candidate_out(c),
            match_score=score,
            fit_level=explanation.fit_level,
            explanation=explanation,
            pipeline_stage=stage
        ))

    return sorted(results, key=lambda x: x.match_score, reverse=True)
