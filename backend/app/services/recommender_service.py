from typing import List, Tuple
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

def calculate_match(candidate: CandidateProfile, job: Job) -> Tuple[int, MatchExplanation]:
    """Score with the v2 engine (app/matching) and return it in the original response shape."""
    from sqlalchemy.orm import object_session

    from app.matching.service import score_one

    result = score_one(object_session(candidate) or object_session(job), job, candidate)
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
    return JobOut(
        id=job.id,
        organization_id=job.organization_id,
        company_name=job.organization.name if job.organization else "Enterprise Tech",
        company_domain=job.organization.domain if job.organization else "tech.io",
        company_logo=job.organization.logo_icon if job.organization else "briefcase",
        title=job.title,
        department=job.department,
        description=job.description,
        key_responsibilities=job.responsibilities,
        required_skills=job.required_skills,
        preferred_skills=job.preferred_skills,
        min_experience_years=job.min_experience_years,
        location=job.location,
        workplace_type=job.workplace_type,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        equity=job.equity,
        required_education=job.required_education,
        urgency=job.urgency,
        status=job.status,
        benefits=job.benefits,
        applicants_count=job.applicants_count,
        employment_type=job.employment_type or "Full-time",
        openings=job.openings or 1,
        max_experience_years=job.max_experience_years,
        seniority=job.seniority or "",
        industry=job.industry or "",
        application_deadline=job.application_deadline,
        published_at=job.published_at,
        closed_at=job.closed_at,
        screening_questions=job.screening_questions,
        interview_criteria=job.interview_criteria,
        posted_date=(job.published_at or job.created_at).strftime("%Y-%m-%d"),
        created_at=job.created_at,
        updated_at=job.updated_at
    )

def get_candidate_out(cand: CandidateProfile) -> CandidateProfileOut:
    return CandidateProfileOut(
        id=cand.id,
        user_id=cand.user_id,
        name=cand.user.full_name if cand.user else "Candidate",
        email=cand.user.email if cand.user else "",
        title=cand.title,
        bio=cand.bio,
        skills=cand.skills,
        experience_years=cand.experience_years,
        location=cand.location,
        remote_preference=cand.remote_preference,
        expected_salary=cand.expected_salary,
        education=cand.education,
        github_url=cand.github_url,
        linkedin_url=cand.linkedin_url,
        portfolio_url=cand.portfolio_url,
        ats_score=cand.ats_score,
        profile_strength=cand.profile_strength,
        avatar_url=cand.user.avatar_url if cand.user else ""
    )

def recommend_jobs_for_candidate_db(db: Session, candidate_id: str) -> List[JobMatchResult]:
    candidate = db.query(CandidateProfile).filter(CandidateProfile.id == candidate_id).first()
    if not candidate:
        return []

    jobs = db.query(Job).filter(Job.status == "Active").all()
    results = []

    for j in jobs:
        score, explanation = calculate_match(candidate, j)
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
    apps = {a.candidate_id: a.stage for a in db.query(Application).filter(Application.job_id == job_id).all()}

    for c in candidates:
        score, explanation = calculate_match(c, job)
        stage = apps.get(c.id, "Sourced")
        results.append(CandidateMatchResult(
            candidate=get_candidate_out(c),
            match_score=score,
            fit_level=explanation.fit_level,
            explanation=explanation,
            pipeline_stage=stage
        ))

    return sorted(results, key=lambda x: x.match_score, reverse=True)
