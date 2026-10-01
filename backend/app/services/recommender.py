import math
from collections import Counter
from typing import List, Dict, Tuple
from app.db.repository import repo
from app.core.config import settings
from app.models.schemas import (
    Candidate, Job, MatchExplanation, ScoreBreakdown,
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
        # Full score + small boost for optimal seniority
        ratio = cand_exp / max(min_exp, 1.0)
        if ratio <= 2.0:
            return 1.0
        return 0.95  # Slight overqualification penalty limit
    else:
        # Pro-rated score
        return max(0.2, cand_exp / max(min_exp, 1.0))

def evaluate_location(cand_loc: str, cand_remote: str, job_loc: str, workplace_type: str) -> float:
    if workplace_type.lower() == "remote" or cand_remote.lower() == "remote":
        return 1.0
    if cand_loc.lower() == job_loc.lower():
        return 1.0
    if cand_remote.lower() == "hybrid" and workplace_type.lower() == "hybrid":
        return 0.5  # Different city but hybrid may require relocation
    return 0.3

def evaluate_salary(expected_salary: int, salary_min: int, salary_max: int) -> float:
    if salary_min <= expected_salary <= salary_max:
        return 1.0
    elif expected_salary < salary_min:
        return 0.95  # Candidate is cheaper than budget
    else:
        # Above budget
        excess_ratio = (expected_salary - salary_max) / max(salary_max, 1)
        return max(0.2, 1.0 - excess_ratio)

def evaluate_education(cand_edu: str, req_edu: str) -> float:
    ranks = {"self-taught": 1, "bachelor's": 2, "master's": 3, "phd": 4}
    cand_rank = ranks.get(cand_edu.lower(), 2)
    req_rank = ranks.get(req_edu.lower(), 2)
    if cand_rank >= req_rank:
        return 1.0
    return 0.7

def build_skill_recommendations(missing_skills: List[str]) -> List[SkillRecommendation]:
    recs = []
    learning_guide = {
        "Docker": ("Cloud & DevOps", "Complete Docker & Containerization Fundamentals with hands-on multi-stage builds", "2-3 weeks"),
        "Kubernetes": ("Cloud & DevOps", "CKAD/CKA Certified Kubernetes Application Developer bootcamp", "4-6 weeks"),
        "Vector Databases": ("Data & AI", "Build RAG applications with Pinecone, Qdrant & LangChain", "1-2 weeks"),
        "LLMs & RAG": ("Data & AI", "Deep dive into fine-tuning, embeddings, and LangChain/LlamaIndex architectures", "3-4 weeks"),
        "AWS": ("Cloud & DevOps", "AWS Certified Solutions Architect Associate Pathway", "4-6 weeks"),
        "TypeScript": ("Languages", "Master TypeScript generics, strict typing, and AST tools", "2 weeks"),
        "Next.js": ("Frameworks", "Next.js App Router, SSR, and Server Actions Masterclass", "2-3 weeks"),
        "Pandas": ("Data & AI", "Data Analysis & Feature Engineering with Pandas & Polars", "1-2 weeks"),
        "FastAPI": ("Frameworks", "High-performance Async Python API development", "1-2 weeks"),
        "Microservices": ("API & Architecture", "Domain Driven Design & Event-Driven Microservices Architecture", "3-4 weeks")
    }

    for skill in missing_skills:
        if skill in learning_guide:
            cat, action, est = learning_guide[skill]
        else:
            cat = "General Engineering"
            action = f"Complete guided projects and certification on {skill}"
            est = "2-4 weeks"

        recs.append(SkillRecommendation(
            skill=skill,
            category=cat,
            recommended_action=action,
            estimated_learning_time=est
        ))
    return recs

def calculate_match(candidate: Candidate, job: Job) -> Tuple[int, MatchExplanation]:
    w = settings.weights
    
    # Skill overlap
    all_job_skills = list(set(job.required_skills + job.preferred_skills))
    cand_skills_lower = {s.lower(): s for s in candidate.skills}
    
    matched_skills = [s for s in all_job_skills if s.lower() in cand_skills_lower]
    missing_critical = [s for s in job.required_skills if s.lower() not in cand_skills_lower]
    missing_preferred = [s for s in job.preferred_skills if s.lower() not in cand_skills_lower]

    # Scores (0.0 to 1.0)
    s_req = compute_skill_similarity(candidate.skills, job.required_skills)
    s_pref = compute_skill_similarity(candidate.skills, job.preferred_skills) if job.preferred_skills else 1.0
    skills_score = (0.75 * s_req) + (0.25 * s_pref)
    
    exp_score = evaluate_experience(candidate.experience_years, job.min_experience_years)
    loc_score = evaluate_location(candidate.location, candidate.remote_preference, job.location, job.workplace_type)
    sal_score = evaluate_salary(candidate.expected_salary, job.salary_min, job.salary_max)
    edu_score = evaluate_education(candidate.education, job.required_education)

    # Weighted Overall Score
    total_score = (
        (skills_score * w.skills_weight) +
        (exp_score * w.experience_weight) +
        (loc_score * w.location_weight) +
        (sal_score * w.salary_weight) +
        (edu_score * w.education_weight)
    )

    match_percentage = int(round(total_score * 100))
    match_percentage = max(10, min(99, match_percentage))

    # Fit level
    if match_percentage >= 85:
        fit_level = "Exceptional Match"
    elif match_percentage >= 70:
        fit_level = "Strong Match"
    elif match_percentage >= 55:
        fit_level = "Moderate Match"
    else:
        fit_level = "Potential Match"

    # Strengths & Gaps
    strengths = []
    gaps = []

    if s_req >= 0.8:
        strengths.append(f"Strong overlap in core required skills ({len(matched_skills)} skills matched)")
    if candidate.experience_years >= job.min_experience_years:
        strengths.append(f"Exceeds minimum experience requirement ({candidate.experience_years} yrs vs {job.min_experience_years} yrs required)")
    if loc_score >= 0.9:
        strengths.append(f"Ideal workplace alignment ({job.workplace_type} / {job.location})")
    if sal_score >= 0.9:
        strengths.append("Expected compensation is within the budgeted salary range")

    if missing_critical:
        gaps.append(f"Missing {len(missing_critical)} required skills: {', '.join(missing_critical)}")
    if candidate.experience_years < job.min_experience_years:
        gaps.append(f"Experience is {round(job.min_experience_years - candidate.experience_years, 1)} years below minimum requirement")
    if loc_score < 0.6:
        gaps.append(f"Location mismatch: Candidate is in {candidate.location} ({candidate.remote_preference}) vs {job.location} ({job.workplace_type})")

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
        strengths=strengths if strengths else ["Basic profile compatibility"],
        gaps=gaps if gaps else ["No significant technical gaps detected"],
        breakdown=breakdown,
        missing_critical_skills=missing_critical,
        missing_preferred_skills=missing_preferred,
        matched_skills=matched_skills,
        recommendations_for_candidate=skill_recs
    )

    return match_percentage, explanation

def recommend_jobs_for_candidate(candidate_id: str) -> List[JobMatchResult]:
    candidate = repo.get_candidate(candidate_id)
    if not candidate:
        # Fallback to first candidate if not found
        candidates = repo.get_all_candidates()
        if not candidates:
            return []
        candidate = candidates[0]

    jobs = repo.get_all_jobs()
    results = []

    for job in jobs:
        score, explanation = calculate_match(candidate, job)
        results.append(JobMatchResult(
            job=job,
            match_score=score,
            fit_level=explanation.fit_level,
            explanation=explanation
        ))

    return sorted(results, key=lambda x: x.match_score, reverse=True)

def recommend_candidates_for_job(job_id: str) -> List[CandidateMatchResult]:
    job = repo.get_job(job_id)
    if not job:
        jobs = repo.get_all_jobs()
        if not jobs:
            return []
        job = jobs[0]

    candidates = repo.get_all_candidates()
    results = []

    stages = ["Sourced", "Screening", "Interview", "Offered", "Hired"]
    stage_idx = 0

    for cand in candidates:
        score, explanation = calculate_match(cand, job)
        assigned_stage = stages[stage_idx % len(stages)]
        stage_idx += 1
        
        results.append(CandidateMatchResult(
            candidate=cand,
            match_score=score,
            fit_level=explanation.fit_level,
            explanation=explanation,
            pipeline_stage=assigned_stage
        ))

    return sorted(results, key=lambda x: x.match_score, reverse=True)

# Legacy support
def recommend_jobs(userId: str):
    matches = recommend_jobs_for_candidate(userId)
    return [
        {
            "jobId": m.job.id,
            "title": m.job.title,
            "score": round(m.match_score / 100.0, 3),
            "missing_skills": m.explanation.missing_critical_skills
        }
        for m in matches
    ]