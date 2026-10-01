"""AI features: resume parsing, job description generation and analysis.

Each returns a draft for a person to review; nothing is saved to a profile or job
until the user confirms it.
"""
import json
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.ai import rules
from app.ai.orchestrator import AIOutcome, run_structured
from app.ai.schemas import ContactInfo, JobAnalysis, JobDraft, ResumeDraft
from app.matching.ontology import SkillGraph, get_skill_graph
from app.matching.redaction import redact
from app.models.db_models import CandidateProfile, Document, Organization, Resume, ResumeVersion, User

MAX_RESUME_CHARS = 12000


def _canonical_skills(graph: SkillGraph, skills) -> list:
    out = []
    for s in skills:
        for name in graph.canonical(s):
            if name not in out:
                out.append(name)
    return out


# ---------------------------------------------------------------------------
# Resumes
# ---------------------------------------------------------------------------
def parse_resume_text(db: Session, text: str, *, user: User, organization_id: Optional[str], input_ref: str,
                      known_names=()) -> "tuple[ContactInfo, AIOutcome[ResumeDraft]]":
    graph = get_skill_graph(db)
    contact = rules.extract_contact(text)  # local only
    redacted = redact(text, names=[n for n in (contact.name, *known_names) if n])
    outcome = run_structured(
        db, feature="resume_parse", prompt_key="resume_parse",
        variables={"resume_text": redacted[:MAX_RESUME_CHARS]}, schema=ResumeDraft,
        fallback=lambda: rules.parse_resume(text, graph, redacted_text=redacted),
        user=user, organization_id=organization_id, input_ref=input_ref,
        store_output=False,  # career history is personal data; keep only the reference
    )
    draft = outcome.data
    draft.skills = _canonical_skills(graph, draft.skills)
    if draft.total_experience_years is None and draft.work_experience:
        draft.total_experience_years = rules._total_years(draft.work_experience, text)  # noqa: SLF001
    return contact, outcome


def save_resume(db: Session, *, candidate: CandidateProfile, document: Document, text: str, draft: Optional[ResumeDraft]) -> Resume:
    """Attach a stored file to a candidate as their primary resume (the caller commits)."""
    db.query(Resume).filter(Resume.candidate_id == candidate.id).update({Resume.is_primary: False}, synchronize_session=False)
    resume = Resume(
        id=f"res_{uuid.uuid4().hex[:8]}", candidate_id=candidate.id,
        title=document.filename.rsplit(".", 1)[0].replace("_", " "), original_filename=document.filename,
        file_format=document.filename.rsplit(".", 1)[-1].lower(), file_size_bytes=document.size_bytes,
        file_storage_path=document.storage_key, document_id=document.id, current_version=1, is_primary=True,
        processing_status="Parsed",
    )
    db.add(resume)
    db.flush()
    db.add(ResumeVersion(
        id=f"rver_{uuid.uuid4().hex[:8]}", resume_id=resume.id, version_number=1, storage_path=document.storage_key,
        extracted_text=text, parsed_payload_json=draft.model_dump_json() if draft else "{}",
    ))
    document.candidate_id = candidate.id
    candidate.raw_resume_text = text
    return resume


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
def generate_job(db: Session, brief: str, *, user: User, organization_id: Optional[str]) -> AIOutcome[JobDraft]:
    graph = get_skill_graph(db)
    org = db.get(Organization, organization_id) if organization_id else None
    outcome = run_structured(
        db, feature="job_generate", prompt_key="job_generate",
        variables={"brief": redact(brief), "industry": (org.industry if org else "") or "not specified"},
        schema=JobDraft, fallback=lambda: rules.generate_job(brief, graph),
        user=user, organization_id=organization_id, input_ref=f"brief:{len(brief)} chars",
    )
    d = outcome.data
    d.required_skills = _canonical_skills(graph, d.required_skills)
    d.preferred_skills = [s for s in _canonical_skills(graph, d.preferred_skills) if s not in d.required_skills]
    if d.workplace_type not in {"Remote", "Hybrid", "Onsite"}:
        d.workplace_type = "Remote"
    if d.employment_type not in {"Full-time", "Part-time", "Contract", "Internship", "Temporary"}:
        d.employment_type = "Full-time"
    return outcome


def analyze_job(db: Session, text: str, *, user: User, organization_id: Optional[str]) -> AIOutcome[JobAnalysis]:
    graph = get_skill_graph(db)
    outcome = run_structured(
        db, feature="job_analyze", prompt_key="job_analyze", variables={"job_text": redact(text)[:15000]},
        schema=JobAnalysis, fallback=lambda: rules.analyze_job(text, graph),
        user=user, organization_id=organization_id, input_ref=f"job_text:{len(text)} chars",
    )
    a = outcome.data
    a.required_skills = _canonical_skills(graph, a.required_skills)
    a.preferred_skills = [s for s in _canonical_skills(graph, a.preferred_skills) if s not in a.required_skills]
    return outcome


def outcome_meta(outcome: AIOutcome) -> dict:
    return {"method": outcome.method, "provider": outcome.provider, "model": outcome.model,
            "notice": outcome.notice, "request_id": outcome.request_id}


def draft_json(draft) -> str:
    return json.dumps(draft.model_dump())
