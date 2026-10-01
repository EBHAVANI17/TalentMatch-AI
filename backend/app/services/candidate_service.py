"""Candidate profiles: serialization with contact privacy, profile edits, sourcing, search."""
import json
import secrets
import uuid
from datetime import datetime
from typing import Iterable, List, Optional, Set

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.core.security import hash_password
from app.core.tenancy import TenantContext
from app.events import emit
from app.models.db_models import (
    Application, CandidateLanguage, CandidateProfile, CandidateProject, CandidateSkill, Certification,
    EducationRecord, SkillTaxonomy, User, WorkExperience,
)
from app.models.schemas import (
    CandidateDetailOut, CandidateProfileOut, CandidateProfileUpdate, CertificationItem, EducationItem,
    LanguageItem, ProjectItem, SourcedCandidateCreate, WorkExperienceItem,
)
from app.services.skills_service import set_candidate_skills

REMOTE_PREFERENCES = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "Onsite", "on-site": "Onsite", "flexible": "Flexible"}


# ---------------------------------------------------------------------------
# Contact privacy
# ---------------------------------------------------------------------------
def contact_visible_ids(db: Session, ctx: TenantContext, candidate_ids: Iterable[str]) -> Set[str]:
    """Candidates whose email/phone the caller may see.

    Organizations see contact details only for people who applied to them or that
    they sourced themselves; browsing the talent pool shows profiles without contacts.
    """
    ids = set(candidate_ids)
    if not ids:
        return set()
    if ctx.is_super_admin:
        return ids
    if ctx.is_candidate:
        return {ctx.candidate_id} & ids if ctx.candidate_id else set()
    if not ctx.is_org_member:
        return set()
    applied = {
        cid for (cid,) in db.query(Application.candidate_id)
        .filter(Application.organization_id == ctx.org_id, Application.candidate_id.in_(ids)).distinct()
    }
    owned = {
        cid for (cid,) in db.query(CandidateProfile.id)
        .filter(CandidateProfile.owner_org_id == ctx.org_id, CandidateProfile.id.in_(ids))
    }
    return applied | owned


def _base_fields(cand: CandidateProfile, contact_visible: bool) -> dict:
    user = cand.user
    return dict(
        id=cand.id,
        user_id=cand.user_id,
        name=user.full_name if user else "Candidate",
        email=(user.email if user else "") if contact_visible else "",
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
        avatar_url=user.avatar_url if user else "",
        availability=cand.availability or "open",
        notice_period_days=cand.notice_period_days,
        preferred_locations=cand.preferred_locations,
        source=cand.source or "self_registered",
        owner_org_id=cand.owner_org_id,
        last_active_at=cand.last_active_at,
        created_at=cand.created_at,
        contact_visible=contact_visible,
    )


def to_summary(cand: CandidateProfile, contact_visible: bool) -> CandidateProfileOut:
    return CandidateProfileOut(**_base_fields(cand, contact_visible))


def to_detail(cand: CandidateProfile, contact_visible: bool) -> CandidateDetailOut:
    def loads(raw, default):
        try:
            return json.loads(raw) if raw else default
        except ValueError:
            return default

    return CandidateDetailOut(
        **_base_fields(cand, contact_visible),
        phone=(cand.phone or "") if contact_visible else "",
        industry=cand.industry or "",
        available_from=cand.available_from,
        employment_types=cand.employment_types,
        is_searchable=bool(cand.is_searchable),
        work_experience=[
            WorkExperienceItem(
                company_name=w.company_name, job_title=w.job_title, location=w.location or "",
                start_date=w.start_date or "", end_date="" if w.is_current else (w.end_date or ""),
                is_current=bool(w.is_current), description=w.description or "", achievements=w.achievements,
            )
            for w in sorted(cand.work_experiences, key=lambda w: (not w.is_current, w.start_date or ""), reverse=False)
        ],
        education_records=[
            EducationItem(institution=e.institution, degree=e.degree, field_of_study=e.field_of_study or "",
                          graduation_year=e.graduation_year, gpa=e.gpa or "")
            for e in cand.education_records
        ],
        certifications=[
            CertificationItem(name=c.name, issuer=c.issuer or "", issued_on=c.issued_on or "",
                              expires_on=c.expires_on or "", credential_url=c.credential_url or "")
            for c in cand.certifications
        ],
        languages=[LanguageItem(language=l.language, proficiency=l.proficiency or "professional") for l in cand.languages],
        projects=[
            ProjectItem(title=p.title, description=p.description or "", tech_stack=p.tech_stack,
                        live_url=p.live_url or "", repo_url=p.repo_url or "")
            for p in cand.projects
        ],
    )


# ---------------------------------------------------------------------------
# Profile completeness (shown to candidates as "profile strength")
# ---------------------------------------------------------------------------
def compute_profile_strength(cand: CandidateProfile) -> int:
    checks = [
        bool(cand.title),
        len(cand.bio or "") >= 40,
        len(cand.skills) >= 3,
        bool(cand.work_experiences),
        bool(cand.education_records),
        bool(cand.location),
        bool(cand.expected_salary),
        bool(cand.linkedin_url or cand.github_url or cand.portfolio_url),
        bool(cand.raw_resume_text),
        bool(cand.preferred_locations) or cand.remote_preference == "Remote",
    ]
    return round(100 * sum(checks) / len(checks))


# ---------------------------------------------------------------------------
# Edits
# ---------------------------------------------------------------------------
def _replace(db: Session, model, candidate_id: str, rows: List) -> None:
    db.query(model).filter(model.candidate_id == candidate_id).delete(synchronize_session=False)
    for row in rows:
        db.add(row)


def apply_profile_update(db: Session, cand: CandidateProfile, payload: CandidateProfileUpdate, actor: User) -> CandidateProfile:
    changes = payload.model_dump(exclude_unset=True)

    if "full_name" in changes and cand.user:
        cand.user.full_name = changes["full_name"].strip()
    simple = {
        "title", "bio", "phone", "experience_years", "location", "expected_salary", "education", "industry",
        "notice_period_days", "availability", "available_from", "is_searchable",
        "github_url", "linkedin_url", "portfolio_url",
    }
    for field in simple & changes.keys():
        setattr(cand, field, changes[field])
    if "remote_preference" in changes:
        pref = REMOTE_PREFERENCES.get((changes["remote_preference"] or "").lower())
        if not pref:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "remote_preference must be Remote, Hybrid, Onsite or Flexible")
        cand.remote_preference = pref
    if "preferred_locations" in changes:
        cand.preferred_locations_json = json.dumps([l.strip() for l in changes["preferred_locations"] or [] if l.strip()])
    if "employment_types" in changes:
        cand.employment_types_json = json.dumps(changes["employment_types"] or [])
    if "skills" in changes:
        set_candidate_skills(db, cand, changes["skills"] or [])

    cid = cand.id
    if payload.work_experience is not None:
        _replace(db, WorkExperience, cid, [
            WorkExperience(
                id=f"exp_{uuid.uuid4().hex[:10]}", candidate_id=cid, company_name=w.company_name, job_title=w.job_title,
                location=w.location, start_date=w.start_date, end_date="Present" if w.is_current else w.end_date,
                is_current=w.is_current, description=w.description, achievements_json=json.dumps(w.achievements),
            ) for w in payload.work_experience
        ])
    if payload.education_records is not None:
        _replace(db, EducationRecord, cid, [
            EducationRecord(id=f"edu_{uuid.uuid4().hex[:10]}", candidate_id=cid, institution=e.institution, degree=e.degree,
                            field_of_study=e.field_of_study, graduation_year=e.graduation_year, gpa=e.gpa)
            for e in payload.education_records
        ])
    if payload.certifications is not None:
        _replace(db, Certification, cid, [
            Certification(id=f"cert_{uuid.uuid4().hex[:10]}", candidate_id=cid, **c.model_dump())
            for c in payload.certifications
        ])
    if payload.languages is not None:
        _replace(db, CandidateLanguage, cid, [
            CandidateLanguage(id=f"lang_{uuid.uuid4().hex[:10]}", candidate_id=cid, **l.model_dump())
            for l in payload.languages
        ])
    if payload.projects is not None:
        _replace(db, CandidateProject, cid, [
            CandidateProject(id=f"proj_{uuid.uuid4().hex[:10]}", candidate_id=cid, title=p.title, description=p.description,
                             tech_stack_json=json.dumps(p.tech_stack), live_url=p.live_url, repo_url=p.repo_url)
            for p in payload.projects
        ])

    db.flush()
    db.refresh(cand)
    cand.profile_strength = compute_profile_strength(cand)
    if actor.id == cand.user_id:
        cand.last_active_at = datetime.utcnow()
    emit(db, "candidate.updated", organization_id=cand.owner_org_id, actor=actor,
         payload={"candidate_id": cand.id, "fields": sorted(changes.keys())})
    return cand


def create_sourced_candidate(db: Session, ctx: TenantContext, payload: SourcedCandidateCreate) -> CandidateProfile:
    email = payload.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This person already has a Talent Match account. Search the talent pool or ask them to apply.",
        )
    # A placeholder account that cannot sign in; it holds the person's name and email.
    user = User(
        id=f"usr_src_{uuid.uuid4().hex[:8]}",
        email=email,
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        full_name=payload.full_name.strip(),
        role="CANDIDATE",
        status="Sourced",
        is_active=False,
        email_verified=False,
    )
    db.add(user)
    cand = CandidateProfile(
        id=f"cand_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        title=payload.title or "",
        bio="",
        skills_json="[]",
        owner_org_id=ctx.org_id,
        source="recruiter",
        is_searchable=False,
        ats_score=0,
        profile_strength=0,
    )
    db.add(cand)
    db.flush()
    apply_profile_update(db, cand, CandidateProfileUpdate(**payload.model_dump(exclude={"email", "full_name", "resume_document_id"}, exclude_unset=True)), ctx.user)
    if payload.resume_document_id:
        _attach_parsed_resume(db, ctx, cand, payload.resume_document_id)
    emit(db, "candidate.created", organization_id=ctx.org_id, actor=ctx.user,
         payload={"candidate_id": cand.id, "source": "recruiter"})
    return cand


def _attach_parsed_resume(db: Session, ctx: TenantContext, cand: CandidateProfile, document_id: str) -> None:
    from app.adapters.storage import get_storage
    from app.ai.features import save_resume
    from app.models.db_models import Document
    from app.services.text_extraction import extract_text

    document = db.get(Document, document_id)
    if document is None or document.organization_id != ctx.org_id or document.candidate_id is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume file not found")
    text = extract_text(document.filename, get_storage().get(document.storage_key))
    save_resume(db, candidate=cand, document=document, text=text, draft=None)
    cand.profile_strength = compute_profile_strength(cand)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def filter_candidates(
    query: Query,
    *,
    q: Optional[str] = None,
    skills: Optional[List[str]] = None,
    location: Optional[str] = None,
    min_experience: Optional[float] = None,
    max_experience: Optional[float] = None,
    availability: Optional[str] = None,
    remote_preference: Optional[str] = None,
    max_salary: Optional[int] = None,
    education: Optional[str] = None,
    source: Optional[str] = None,
) -> Query:
    query = query.outerjoin(User, User.id == CandidateProfile.user_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(User.full_name.ilike(like), CandidateProfile.title.ilike(like), CandidateProfile.bio.ilike(like)))
    for skill in [s.strip() for s in skills or [] if s.strip()]:
        # every requested skill must be present (AND)
        query = query.filter(CandidateProfile.id.in_(
            Query([CandidateSkill.candidate_id]).join(SkillTaxonomy, SkillTaxonomy.id == CandidateSkill.skill_id)
            .filter(SkillTaxonomy.name.ilike(skill))
        ))
    if location:
        like = f"%{location.strip()}%"
        query = query.filter(or_(CandidateProfile.location.ilike(like), CandidateProfile.preferred_locations_json.ilike(like)))
    if min_experience is not None:
        query = query.filter(CandidateProfile.experience_years >= min_experience)
    if max_experience is not None:
        query = query.filter(CandidateProfile.experience_years <= max_experience)
    if availability:
        query = query.filter(CandidateProfile.availability == availability)
    if remote_preference:
        query = query.filter(CandidateProfile.remote_preference == remote_preference)
    if max_salary is not None:
        query = query.filter(CandidateProfile.expected_salary <= max_salary)
    if education:
        query = query.filter(CandidateProfile.education.ilike(f"%{education.strip()}%"))
    if source:
        query = query.filter(CandidateProfile.source == source)
    return query
