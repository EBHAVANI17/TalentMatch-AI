"""Prompt registry: versioned prompts stored in the database, seeded from these defaults.

Edit a prompt by creating a new version (POST /api/v1/admin/prompts/{key}/versions) and
activating it; older versions stay available for rollback and for auditing past results.
"""
import uuid
from dataclasses import dataclass
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models.db_models import PromptTemplate

_PRIVACY = (
    "Personal identifiers in the input have been replaced with placeholders such as [name], [email], "
    "[phone] and [link]; never try to recover them. Never infer or mention age, gender, ethnicity, "
    "nationality, religion, marital status, health, or any other personal characteristic."
)


@dataclass(frozen=True)
class PromptDefault:
    system: str
    user_template: str
    notes: str = ""


DEFAULT_PROMPTS: Dict[str, PromptDefault] = {
    "resume_parse": PromptDefault(
        system=(
            "You extract structured career information from resumes for a recruiting platform. "
            + _PRIVACY + " Only include facts that appear in the resume; use empty strings, empty lists "
            "or null when something is not stated. Dates use YYYY-MM. Respond with one JSON object only, "
            "with exactly these keys:\n"
            '{"headline": str, "summary": str, "total_experience_years": number|null, "skills": [str], '
            '"work_experience": [{"job_title": str, "company_name": str, "location": str, "start_date": str, '
            '"end_date": str, "is_current": bool, "description": str, "achievements": [str]}], '
            '"education": [{"institution": str, "degree": str, "field_of_study": str, "graduation_year": int|null}], '
            '"certifications": [{"name": str, "issuer": str, "issued_on": str}], '
            '"projects": [{"title": str, "description": str, "tech_stack": [str]}], '
            '"languages": [{"language": str, "proficiency": "basic"|"conversational"|"professional"|"native"}], '
            '"industries": [str]}'
        ),
        user_template="Resume text:\n\"\"\"\n{resume_text}\n\"\"\"",
        notes="v1: structured extraction; contact details are extracted locally, never by the model.",
    ),
    "job_generate": PromptDefault(
        system=(
            "You write clear, inclusive job descriptions for a recruiting platform from a short brief. "
            + _PRIVACY + " Do not add requirements about age, gender, nationality, physical ability or "
            "anything unrelated to doing the job. Avoid jargon like 'rockstar' or 'ninja'. Keep skills "
            "specific (technologies, methods). Only set salary if the brief gives one. Respond with one JSON "
            "object only, with exactly these keys:\n"
            '{"title": str, "department": str, "seniority": str, "employment_type": "Full-time"|"Part-time"|'
            '"Contract"|"Internship"|"Temporary", "workplace_type": "Remote"|"Hybrid"|"Onsite", "location": str, '
            '"description": str, "responsibilities": [str], "required_skills": [str], "preferred_skills": [str], '
            '"min_experience_years": number, "max_experience_years": number|null, "required_education": str, '
            '"salary_min": int|null, "salary_max": int|null, "interview_criteria": [str], "screening_questions": [str]}'
        ),
        user_template="Brief from the recruiter:\n\"\"\"\n{brief}\n\"\"\"\nOrganization industry: {industry}",
        notes="v1: draft generation; the recruiter reviews everything before publishing.",
    ),
    "job_analyze": PromptDefault(
        system=(
            "You turn an existing job description into structured requirements for a recruiting platform. "
            + _PRIVACY + " Extract only what the text states; do not invent requirements. Respond with one JSON "
            "object only, with exactly these keys:\n"
            '{"title": str, "seniority": str, "industry": str, "employment_type": str, "workplace_type": '
            '"Remote"|"Hybrid"|"Onsite"|"", "location": str, "required_skills": [str], "preferred_skills": [str], '
            '"min_experience_years": number|null, "max_experience_years": number|null, "required_education": str, '
            '"certifications": [str], "salary_min": int|null, "salary_max": int|null, "responsibilities": [str]}'
        ),
        user_template="Job description:\n\"\"\"\n{job_text}\n\"\"\"",
        notes="v1: structured extraction from pasted descriptions.",
    ),
}


def ensure_default_prompts(db: Session) -> None:
    """Insert version 1 of any prompt key that has no versions yet (never overwrites edits)."""
    existing = {k for (k,) in db.query(PromptTemplate.key).distinct()}
    for key, default in DEFAULT_PROMPTS.items():
        if key not in existing:
            db.add(PromptTemplate(
                id=f"prompt_{uuid.uuid4().hex[:12]}", key=key, version=1, status="active",
                system=default.system, user_template=default.user_template, notes=default.notes,
            ))
    db.commit()


def get_active_prompt(db: Session, key: str) -> PromptTemplate:
    prompt = db.query(PromptTemplate).filter(PromptTemplate.key == key, PromptTemplate.status == "active").first()
    if prompt is None:
        default = DEFAULT_PROMPTS[key]
        return PromptTemplate(key=key, version=0, status="active", system=default.system, user_template=default.user_template)
    return prompt


def create_version(db: Session, key: str, system: str, user_template: str, notes: str, author_id: Optional[str]) -> PromptTemplate:
    latest = db.query(PromptTemplate).filter(PromptTemplate.key == key).order_by(PromptTemplate.version.desc()).first()
    prompt = PromptTemplate(
        id=f"prompt_{uuid.uuid4().hex[:12]}", key=key, version=(latest.version + 1) if latest else 1, status="draft",
        system=system, user_template=user_template, notes=notes, created_by_user_id=author_id,
    )
    db.add(prompt)
    db.commit()
    return prompt


def activate_version(db: Session, key: str, version: int) -> PromptTemplate:
    target = db.query(PromptTemplate).filter(PromptTemplate.key == key, PromptTemplate.version == version).first()
    if target is None:
        raise KeyError(f"{key} v{version}")
    for p in db.query(PromptTemplate).filter(PromptTemplate.key == key, PromptTemplate.status == "active"):
        p.status = "retired"
    target.status = "active"
    db.commit()
    return target
