"""Normalized skills.

Skills live in `skill_taxonomies` (the shared catalog) and are linked to candidates
(`candidate_skills`) and jobs (`job_skills`). The older JSON columns
(`skills_json`, `required_skills_json`, `preferred_skills_json`) are still written
too, so existing code and the classic UI keep working during the migration.
"""
import json
import uuid
from typing import Dict, Iterable, List

from sqlalchemy.orm import Session

from app.models.db_models import CandidateProfile, CandidateSkill, Job, JobSkill, SkillTaxonomy


def clean_skill_names(names: Iterable[str]) -> List[str]:
    """Trim, drop blanks and case-insensitive duplicates, keep the caller's order."""
    seen, result = set(), []
    for name in names or []:
        if not isinstance(name, str):
            continue
        cleaned = " ".join(name.split())[:128]
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            result.append(cleaned)
    return result


def resolve_skills(db: Session, names: Iterable[str]) -> List[SkillTaxonomy]:
    """Catalog entries for these names, creating 'Uncategorized' entries for new skills."""
    names = clean_skill_names(names)
    if not names:
        return []
    existing: Dict[str, SkillTaxonomy] = {s.name.lower(): s for s in db.query(SkillTaxonomy).all()}
    result = []
    for name in names:
        skill = existing.get(name.lower())
        if skill is None:
            skill = SkillTaxonomy(
                id=f"tax_{uuid.uuid4().hex[:8]}", name=name, category="Uncategorized",
                demand_level="Medium", avg_salary_boost="",
            )
            db.add(skill)
            existing[name.lower()] = skill
        result.append(skill)
    db.flush()
    return result


def set_candidate_skills(db: Session, candidate: CandidateProfile, names: Iterable[str]) -> None:
    skills = resolve_skills(db, names)
    candidate.skills_json = json.dumps([s.name for s in skills])
    db.query(CandidateSkill).filter(CandidateSkill.candidate_id == candidate.id).delete(synchronize_session=False)
    for position, skill in enumerate(skills):
        db.add(CandidateSkill(
            id=f"cs_{uuid.uuid4().hex[:12]}", candidate_id=candidate.id, skill_id=skill.id, position=position,
        ))
    db.flush()


def set_job_skills(db: Session, job: Job, required: Iterable[str], preferred: Iterable[str]) -> None:
    required_skills = resolve_skills(db, required)
    required_ids = {s.id for s in required_skills}
    # A skill listed as both required and preferred counts as required.
    preferred_skills = [s for s in resolve_skills(db, preferred) if s.id not in required_ids]

    job.required_skills_json = json.dumps([s.name for s in required_skills])
    job.preferred_skills_json = json.dumps([s.name for s in preferred_skills])
    db.query(JobSkill).filter(JobSkill.job_id == job.id).delete(synchronize_session=False)
    for importance, skills in (("required", required_skills), ("preferred", preferred_skills)):
        for position, skill in enumerate(skills):
            db.add(JobSkill(
                id=f"js_{uuid.uuid4().hex[:12]}", job_id=job.id, skill_id=skill.id,
                importance=importance, position=position,
            ))
    db.flush()


def sync_all_skill_links(db: Session) -> None:
    """Rebuild every link from the JSON columns (used after bulk inserts such as demo seeding)."""
    for candidate in db.query(CandidateProfile).all():
        set_candidate_skills(db, candidate, candidate.skills)
    for job in db.query(Job).all():
        set_job_skills(db, job, job.required_skills, job.preferred_skills)
    db.commit()
