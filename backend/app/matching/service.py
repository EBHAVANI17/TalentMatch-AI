"""Glue between the database and the scoring engine: facts, weights, persisted matches."""
import hashlib
import json
import uuid
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.adapters.embeddings import get_embedder
from app.matching import embeddings
from app.matching.engine import DEFAULT_WEIGHTS, ENGINE_VERSION, CandidateFacts, JobFacts, MatchResult, score_match
from app.matching.ontology import get_skill_graph
from app.models.db_models import CandidateProfile, Embedding, Job, Match, Organization


# ---------------------------------------------------------------------------
# Facts (the only data the engine sees)
# ---------------------------------------------------------------------------
def candidate_facts(c: CandidateProfile) -> CandidateFacts:
    return CandidateFacts(
        skills=tuple(c.skills),
        certifications=tuple(cert.name for cert in c.certifications),
        experience_years=float(c.experience_years or 0),
        titles=tuple(t for t in [c.title, *(w.job_title for w in c.work_experiences)] if t),
        location=c.location or "",
        preferred_locations=tuple(c.preferred_locations),
        remote_preference=c.remote_preference or "",
        expected_salary=c.expected_salary or None,
        education_levels=tuple(e for e in [c.education, *(r.degree for r in c.education_records)] if e),
        industry=c.industry or "",
        notice_period_days=c.notice_period_days,
    )


def job_facts(j: Job) -> JobFacts:
    return JobFacts(
        required_skills=tuple(j.required_skills),
        preferred_skills=tuple(j.preferred_skills),
        min_experience_years=float(j.min_experience_years or 0),
        max_experience_years=j.max_experience_years,
        title=j.title or "",
        location=j.location or "",
        workplace_type=j.workplace_type or "",
        salary_min=j.salary_min or None,
        salary_max=j.salary_max or None,
        required_education=j.required_education or "",
        industry=j.industry or "",
    )


# ---------------------------------------------------------------------------
# Organization weights
# ---------------------------------------------------------------------------
def get_weights(org: Optional[Organization]) -> Dict[str, float]:
    weights = dict(DEFAULT_WEIGHTS)
    if org and org.matching_weights_json:
        try:
            weights.update({k: float(v) for k, v in json.loads(org.matching_weights_json).items() if k in DEFAULT_WEIGHTS})
        except (ValueError, TypeError):
            pass
    return weights


def set_weights(db: Session, org: Organization, weights: Dict[str, float]) -> Dict[str, float]:
    unknown = set(weights) - set(DEFAULT_WEIGHTS)
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown factors: {', '.join(sorted(unknown))}")
    if any(not 0 <= v <= 1 for v in weights.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Each weight must be between 0 and 1")
    merged = {**DEFAULT_WEIGHTS, **weights}
    if merged.get("skills", 0) <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Skills must keep a weight above 0")
    org.matching_weights_json = json.dumps({k: round(v, 4) for k, v in weights.items()})
    db.commit()
    return get_weights(org)


def _hash(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Persisted matches
# ---------------------------------------------------------------------------
def _store(row: Match, result: MatchResult, inputs: str, weights_hash: str) -> None:
    row.score = result.score
    row.fit_level = result.fit_level
    row.factors_json = json.dumps([f.__dict__ for f in result.factors])
    row.strengths_json = json.dumps(result.strengths)
    row.gaps_json = json.dumps(result.gaps)
    row.matching_skills_json = json.dumps(result.matching_skills)
    row.missing_skills_json = json.dumps(result.missing_skills)
    row.explanation = result.explanation
    row.engine_version = ENGINE_VERSION
    row.weights_hash = weights_hash
    row.inputs_hash = inputs
    row.computed_at = datetime.utcnow()


def ensure_matches(db: Session, job: Job, candidates: Iterable[CandidateProfile], *, force: bool = False) -> Dict[str, Match]:
    """Matches for one job and these candidates, (re)computing only those whose inputs changed. Caller commits."""
    candidates = list(candidates)
    if not candidates:
        return {}
    graph = get_skill_graph(db)
    weights = get_weights(job.organization)
    weights_hash = _hash(json.dumps(weights, sort_keys=True))[:16]
    model = get_embedder().name

    emb_hashes = {
        (e.entity_type, e.entity_id): e.content_hash
        for e in db.query(Embedding.entity_type, Embedding.entity_id, Embedding.content_hash).filter(
            Embedding.model == model,
            Embedding.entity_id.in_([job.id, *(c.id for c in candidates)]),
        )
    }
    existing = {m.candidate_id: m for m in db.query(Match).filter(
        Match.job_id == job.id, Match.candidate_id.in_([c.id for c in candidates]))}

    # Embedding text is part of the inputs, so only vectors that are needed get loaded.
    job_key = (job.updated_at, emb_hashes.get(("job", job.id)), job.required_skills_json, job.preferred_skills_json)
    stale = []
    for c in candidates:
        inputs = _hash(ENGINE_VERSION, weights_hash, job_key, c.updated_at, c.skills_json,
                       emb_hashes.get(("candidate", c.id)), len(c.certifications), len(c.work_experiences))
        row = existing.get(c.id)
        if force or row is None or row.inputs_hash != inputs:
            stale.append((c, inputs))

    if stale:
        vectors = embeddings.vectors_for(db, "candidate", [c.id for c, _ in stale])
        job_vec = embeddings.vectors_for(db, "job", [job.id]).get(job.id)
        jf = job_facts(job)
        for c, inputs in stale:
            result = score_match(candidate_facts(c), jf, graph, weights,
                                 embeddings.cosine(job_vec, vectors.get(c.id)))
            row = existing.get(c.id)
            if row is None:
                row = Match(id=f"match_{uuid.uuid4().hex[:16]}", organization_id=job.organization_id,
                            job_id=job.id, candidate_id=c.id, status="new")
                db.add(row)
                existing[c.id] = row
            _store(row, result, inputs, weights_hash)
        db.flush()
    return existing


def score_one(db: Session, job: Job, candidate: CandidateProfile) -> MatchResult:
    """Score without persisting (used when a candidate applies or views a job)."""
    vectors = embeddings.vectors_for(db, "candidate", [candidate.id])
    job_vec = embeddings.vectors_for(db, "job", [job.id]).get(job.id)
    return score_match(candidate_facts(candidate), job_facts(job), get_skill_graph(db),
                       get_weights(job.organization), embeddings.cosine(job_vec, vectors.get(candidate.id)))


def result_from_row(row: Match) -> dict:
    return {
        "score": row.score,
        "fit_level": row.fit_level,
        "factors": row.factors,
        "strengths": row.strengths,
        "gaps": row.gaps,
        "matching_skills": row.matching_skills,
        "missing_skills": row.missing_skills,
        "explanation": row.explanation,
        "engine_version": row.engine_version,
        "computed_at": row.computed_at,
    }


def summarize(rows: List[Match]) -> dict:
    scores = [r.score for r in rows]
    return {
        "considered": len(scores),
        "strong": sum(s >= 80 for s in scores),
        "potential": sum(s >= 60 for s in scores),
    }
