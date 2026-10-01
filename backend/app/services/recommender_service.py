import math
from collections import Counter
from typing import List, Tuple
from sqlalchemy.orm import Session
from app.models.db_models import CandidateProfile, Job
from app.models.schemas import (
    JobOut, CandidateProfileOut, MatchExplanation, ScoreBreakdown,
    SkillRecommendation, JobMatchResult, CandidateMatchResult
)

def _calc_tfidf_cosine(cand_skills: List[str], job_skills: List[str]) -> float:
    cand_tokens = [s.lower().strip() for s in cand_skills if s.strip()]
    job_tokens = [s.lower().strip() for s in job_skills if s.strip()]
    if not cand_tokens or not job_tokens:
        return 0.0
    
    vocab = list(set(cand_tokens + job_tokens))
    c_count = Counter(cand_tokens)
    j_count = Counter(job_tokens)

    c_vec = []
    j_vec = []
    for term in vocab:
        df = (1 if term in c_count else 0) + (1 if term in j_count else 0)
        idf = math.log(3.0 / (df + 1.0)) + 1.0
        c_vec.append((c_count.get(term, 0) / max(len(cand_tokens), 1)) * idf)
        j_vec.append((j_count.get(term, 0) / max(len(job_tokens), 1)) * idf)

    dot_product = sum(a * b for a, b in zip(c_vec, j_vec))
    c_norm = math.sqrt(sum(a * a for a in c_vec))
    j_norm = math.sqrt(sum(b * b for b in j_vec))

    if c_norm == 0 or j_norm == 0:
        return 0.0
    return dot_product / (c_norm * j_norm)

def compute_skill_similarity(cand_skills: List[str], job_skills: List[str]) -> float:
    if not job_skills:
        return 1.0
    if not cand_skills:
        return 0.0

    sim = _calc_tfidf_cosine(cand_skills, job_skills)
    cand_lower = {s.lower() for s in cand_skills}
    overlap = sum(1 for s in job_skills if s.lower() in cand_lower)
    overlap_ratio = overlap / len(job_skills)

    combined = (0.6 * overlap_ratio) + (0.4 * float(sim))
    return min(1.0, max(0.0, combined))

def evaluate_experience(cand_exp: float, min_exp: float) -> float:
    if cand_exp >= min_exp:
        ratio = cand_exp / max(min_exp, 1.0)
        return 1.0 if ratio <= 2.0 else 0.95
    return max(0.2, cand_exp / max(min_exp, 1.0))

def evaluate_location(cand_loc: str, cand_remote: str, job_loc: str, workplace_type: str) -> float:
    if workplace_type.lower() == "remote" or cand_remote.lower() == "remote":
        return 1.0
    if cand_loc.lower() == job_loc.lower():
        return 1.0
    if cand_remote.lower() == "hybrid" and workplace_type.lower() == "hybrid":
        return 0.6
    return 0.35

def evaluate_salary(expected_salary: int, salary_min: int, salary_max: int) -> float:
    if salary_min <= expected_salary <= salary_max:
        return 1.0
    elif expected_salary < salary_min:
        return 0.95
    else:
        excess = (expected_salary - salary_max) / max(salary_max, 1)
        return max(0.25, 1.0 - excess)

def evaluate_education(cand_edu: str, req_edu: str) -> float:
    ranks = {"self-taught": 1, "bachelor's": 2, "master's": 3, "phd": 4}
    cand_rank = ranks.get(cand_edu.lower(), 2)
    req_rank = ranks.get(req_edu.lower(), 2)
    return 1.0 if cand_rank >= req_rank else 0.75

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
    cand_skills = candidate.skills
    job_req = job.required_skills
    job_pref = job.preferred_skills
    all_job_skills = list(set(job_req + job_pref))

    cand_skills_lower = {s.lower(): s for s in cand_skills}
    matched_skills = [s for s in all_job_skills if s.lower() in cand_skills_lower]
    missing_critical = [s for s in job_req if s.lower() not in cand_skills_lower]
    missing_preferred = [s for s in job_pref if s.lower() not in cand_skills_lower]

    s_req = compute_skill_similarity(cand_skills, job_req)
    s_pref = compute_skill_similarity(cand_skills, job_pref) if job_pref else 1.0
    skills_score = (0.75 * s_req) + (0.25 * s_pref)

    exp_score = evaluate_experience(candidate.experience_years, job.min_experience_years)
    loc_score = evaluate_location(candidate.location, candidate.remote_preference, job.location, job.workplace_type)
    sal_score = evaluate_salary(candidate.expected_salary, job.salary_min, job.salary_max)
    edu_score = evaluate_education(candidate.education, job.required_education)

    total_score = (
        (skills_score * 0.45) +
        (exp_score * 0.25) +
        (loc_score * 0.15) +
        (sal_score * 0.10) +
        (edu_score * 0.05)
    )

    match_percentage = int(round(total_score * 100))
    match_percentage = max(10, min(99, match_percentage))

    if match_percentage >= 85:
        fit_level = "Exceptional Match"
    elif match_percentage >= 70:
        fit_level = "Strong Match"
    elif match_percentage >= 55:
        fit_level = "Moderate Match"
    else:
        fit_level = "Potential Match"

    strengths = []
    gaps = []

    if s_req >= 0.8:
        strengths.append(f"Strong overlap in core competencies ({len(matched_skills)} skills verified)")
    if candidate.experience_years >= job.min_experience_years:
        strengths.append(f"Exceeds minimum experience requirement ({candidate.experience_years} yrs vs {job.min_experience_years} yrs)")
    if loc_score >= 0.9:
        strengths.append(f"Ideal workplace alignment ({job.workplace_type} / {job.location})")
    if sal_score >= 0.9:
        strengths.append(f"Target compensation (${candidate.expected_salary:,}) is within budgeted range")

    if missing_critical:
        gaps.append(f"Missing {len(missing_critical)} required skills: {', '.join(missing_critical)}")
    if candidate.experience_years < job.min_experience_years:
        gaps.append(f"Experience is {round(job.min_experience_years - candidate.experience_years, 1)} years below minimum requirement")
    if loc_score < 0.6:
        gaps.append(f"Location difference: {candidate.location} ({candidate.remote_preference}) vs {job.location} ({job.workplace_type})")

    breakdown = ScoreBreakdown(
        skills_score=round(skills_score * 100, 1),
        experience_score=round(exp_score * 100, 1),
        location_score=round(loc_score * 100, 1),
        salary_score=round(sal_score * 100, 1),
        education_score=round(edu_score * 100, 1)
    )

    skill_recs = build_skill_recommendations(missing_critical + missing_preferred)

    explanation = MatchExplanation(
        overall_match_percentage=match_percentage,
        fit_level=fit_level,
        strengths=strengths if strengths else ["Basic profile alignment"],
        gaps=gaps if gaps else ["No significant technical gaps identified"],
        breakdown=breakdown,
        missing_critical_skills=missing_critical,
        missing_preferred_skills=missing_preferred,
        matched_skills=matched_skills,
        recommendations_for_candidate=skill_recs
    )

    return match_percentage, explanation

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
        posted_date=job.created_at.strftime("%Y-%m-%d"),
        created_at=job.created_at
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
        candidate = db.query(CandidateProfile).first()
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

def recommend_candidates_for_job_db(db: Session, job_id: str) -> List[CandidateMatchResult]:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        job = db.query(Job).first()
    if not job:
        return []

    candidates = db.query(CandidateProfile).all()
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
