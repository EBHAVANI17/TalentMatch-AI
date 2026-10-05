import json
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, Index, Enum, LargeBinary
)
from pgvector.sqlalchemy import Vector

from app.core.config import settings
from app.core.crypto import EncryptedString, EncryptedText
from sqlalchemy.orm import relationship
from app.core.database import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _parse_json(val: Any, default: Any = None) -> Any:
    if default is None:
        default = []
    if not val:
        return default
    try:
        return json.loads(str(val))
    except Exception:
        return default

# =========================================================================
# 1. ORGANIZATIONS (MULTI-TENANCY ISOLATION BOUNDARY)
# =========================================================================
class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(64), primary_key=True, index=True)
    name = Column(String(128), nullable=False, index=True)
    domain = Column(String(128), unique=True, index=True)
    industry = Column(String(64), default="Software & AI")
    plan_tier = Column(String(32), default="Enterprise")
    logo_icon = Column(String(64), default="briefcase")
    website = Column(String(256), default="")
    status = Column(String(32), default="Active", index=True) # Active, Suspended, Inactive
    is_active = Column(Boolean, default=True)
    
    # Entitlement Limits
    max_recruiter_seats = Column(Integer, default=10)
    max_active_jobs = Column(Integer, default=50)
    monthly_ai_credits = Column(Integer, default=5000)
    monthly_ai_credits_used = Column(Integer, default=0)
    # Organization-specific weights for the matching engine (JSON object); empty = platform defaults
    matching_weights_json = Column(Text, default="")

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="organization", cascade="all, delete-orphan")
    ai_usage_records = relationship("AIUsageRecord", back_populates="organization")
    audit_logs = relationship("AuditLog", back_populates="organization")

# =========================================================================
# 2. USERS & ROLES (RBAC & IDENTITY)
# =========================================================================
class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, index=True)
    email = Column(String(128), unique=True, nullable=False, index=True)
    hashed_password = Column(String(256), nullable=False)
    full_name = Column(String(128), nullable=False)
    
    # Roles: SUPER_ADMIN, ORG_ADMIN, RECRUITER, HIRING_MANAGER, INTERVIEWER, CANDIDATE, ANALYST
    # Backward compatible with EMPLOYER_ADMIN
    role = Column(String(32), nullable=False, default="CANDIDATE", index=True)
    
    organization_id = Column(String(64), ForeignKey("organizations.id"), nullable=True, index=True)
    avatar_url = Column(String(512), default="")
    status = Column(String(32), default="Active", index=True) # Active, Suspended, Pending_Verification
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=True)
    last_login_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    organization = relationship("Organization", back_populates="users")
    candidate_profile = relationship("CandidateProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")
    interview_feedback = relationship("InterviewFeedback", back_populates="interviewer")

# =========================================================================
# 3. CANDIDATE PROFILES & DETAILED ENTITIES
# =========================================================================
class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id = Column(String(64), primary_key=True, index=True)
    user_id = Column(String(64), ForeignKey("users.id"), unique=True, nullable=False, index=True)
    title = Column(String(128), nullable=False)
    bio = Column(Text, default="")
    skills_json = Column(Text, default="[]")  # JSON List of strings
    experience_years = Column(Float, default=0.0)
    location = Column(String(128), default="San Francisco, CA")
    remote_preference = Column(String(32), default="Remote") # Remote, Hybrid, Onsite
    expected_salary = Column(Integer, default=150000)
    education = Column(String(128), default="Bachelor's")
    github_url = Column(String(256), default="")
    linkedin_url = Column(String(256), default="")
    portfolio_url = Column(String(256), default="")
    raw_resume_text = Column(EncryptedText, default="")
    ats_score = Column(Integer, default=90)
    profile_strength = Column(Integer, default=95)
    is_searchable = Column(Boolean, default=True, index=True)

    # Contact, availability and preferences (encrypted at rest)
    phone = Column(EncryptedString(256), default="")
    industry = Column(String(64), default="")
    notice_period_days = Column(Integer, nullable=True)
    availability = Column(String(32), default="open")  # open | passive | not_looking
    available_from = Column(DateTime, nullable=True)
    preferred_locations_json = Column(Text, default="[]")
    employment_types_json = Column(Text, default="[]")  # Full-time, Contract, ...

    # Tenancy: NULL = self-registered talent; set = sourced by (and private to) that organization
    owner_org_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    source = Column(String(32), default="self_registered")  # self_registered | recruiter | import
    last_active_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    user = relationship("User", back_populates="candidate_profile")
    applications = relationship("Application", back_populates="candidate")
    resumes = relationship("Resume", back_populates="candidate", cascade="all, delete-orphan")
    work_experiences = relationship("WorkExperience", back_populates="candidate", cascade="all, delete-orphan")
    education_records = relationship("EducationRecord", back_populates="candidate", cascade="all, delete-orphan")
    projects = relationship("CandidateProject", back_populates="candidate", cascade="all, delete-orphan")
    certifications = relationship("Certification", back_populates="candidate", cascade="all, delete-orphan")
    languages = relationship("CandidateLanguage", back_populates="candidate", cascade="all, delete-orphan")
    skill_links = relationship("CandidateSkill", back_populates="candidate", cascade="all, delete-orphan")

    @property
    def preferred_locations(self):
        return _parse_json(self.preferred_locations_json, [])

    @property
    def employment_types(self):
        return _parse_json(self.employment_types_json, [])

    @property
    def skills(self):
        return _parse_json(self.skills_json, [])

    @skills.setter
    def skills(self, value):
        setattr(self, "skills_json", json.dumps(value))

class WorkExperience(Base):
    __tablename__ = "work_experiences"

    id = Column(String(64), primary_key=True, index=True)
    candidate_id = Column(String(64), ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    company_name = Column(String(128), nullable=False)
    job_title = Column(String(128), nullable=False)
    location = Column(String(128), default="")
    start_date = Column(String(32), default="") # e.g. "2021-03"
    end_date = Column(String(32), default="Present")
    is_current = Column(Boolean, default=False)
    description = Column(Text, default="")
    achievements_json = Column(Text, default="[]") # List of quantified achievement bullet points
    created_at = Column(DateTime, default=utc_now)

    candidate = relationship("CandidateProfile", back_populates="work_experiences")

    @property
    def achievements(self):
        return _parse_json(self.achievements_json, [])

class EducationRecord(Base):
    __tablename__ = "education_records"

    id = Column(String(64), primary_key=True, index=True)
    candidate_id = Column(String(64), ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    institution = Column(String(128), nullable=False)
    degree = Column(String(128), nullable=False)
    field_of_study = Column(String(128), default="Computer Science")
    graduation_year = Column(Integer, default=2022)
    gpa = Column(String(32), default="")
    created_at = Column(DateTime, default=utc_now)

    candidate = relationship("CandidateProfile", back_populates="education_records")

class CandidateProject(Base):
    __tablename__ = "candidate_projects"

    id = Column(String(64), primary_key=True, index=True)
    candidate_id = Column(String(64), ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    title = Column(String(128), nullable=False)
    description = Column(Text, default="")
    tech_stack_json = Column(Text, default="[]")
    live_url = Column(String(256), default="")
    repo_url = Column(String(256), default="")
    metrics_json = Column(Text, default="{}") # e.g. {"qps": 50000, "latency_reduction": "40%"}
    created_at = Column(DateTime, default=utc_now)

    candidate = relationship("CandidateProfile", back_populates="projects")

    @property
    def tech_stack(self):
        return _parse_json(self.tech_stack_json, [])

# =========================================================================
# 4. RESUMES, VERSIONS & MULTI-DIMENSIONAL ANALYSIS
# =========================================================================
class Resume(Base):
    __tablename__ = "resumes"

    id = Column(String(64), primary_key=True, index=True)
    candidate_id = Column(String(64), ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    title = Column(String(128), default="Primary Technical Resume")
    original_filename = Column(String(256), nullable=False)
    file_format = Column(String(32), default="pdf") # pdf, docx, txt
    file_size_bytes = Column(Integer, default=0)
    file_storage_path = Column(String(512), default="")
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    current_version = Column(Integer, default=1)
    is_primary = Column(Boolean, default=True)
    processing_status = Column(String(32), default="Parsed", index=True) # Uploaded, Processing, Parsed, Failed
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    candidate = relationship("CandidateProfile", back_populates="resumes")
    versions = relationship("ResumeVersion", back_populates="resume", cascade="all, delete-orphan")
    analyses = relationship("ResumeAnalysis", back_populates="resume", cascade="all, delete-orphan")

class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id = Column(String(64), primary_key=True, index=True)
    resume_id = Column(String(64), ForeignKey("resumes.id"), nullable=False, index=True)
    version_number = Column(Integer, default=1)
    storage_path = Column(String(512), default="")
    extracted_text = Column(EncryptedText, default="")
    parsed_payload_json = Column(Text, default="{}") # Structured extracted JSON
    created_at = Column(DateTime, default=utc_now)

    resume = relationship("Resume", back_populates="versions")

class ResumeAnalysis(Base):
    __tablename__ = "resume_analyses"

    id = Column(String(64), primary_key=True, index=True)
    resume_id = Column(String(64), ForeignKey("resumes.id"), nullable=False, index=True)
    target_job_id = Column(String(64), ForeignKey("jobs.id"), nullable=True, index=True)
    
    # 6-Dimension Deterministic Quality Scores (0-100)
    ats_compatibility_score = Column(Integer, default=90)
    skills_coverage_score = Column(Integer, default=85)
    experience_presentation_score = Column(Integer, default=80)
    achievement_strength_score = Column(Integer, default=75)
    keyword_alignment_score = Column(Integer, default=88)
    formatting_completeness_score = Column(Integer, default=92)
    overall_quality_score = Column(Integer, default=85)

    findings_json = Column(Text, default="[]")       # List of identified findings/strengths
    missing_items_json = Column(Text, default="[]")  # List of missing keywords / metrics
    suggestions_json = Column(Text, default="[]")    # Actionable suggestions for improvements
    raw_analysis_notes = Column(Text, default="")
    created_at = Column(DateTime, default=utc_now)

    resume = relationship("Resume", back_populates="analyses")
    target_job = relationship("Job")

    @property
    def findings(self):
        return _parse_json(self.findings_json, [])

    @property
    def missing_items(self):
        return _parse_json(self.missing_items_json, [])

    @property
    def suggestions(self):
        return _parse_json(self.suggestions_json, [])

# =========================================================================
# 5. JOBS & REQUISITIONS (TENANT BOUND)
# =========================================================================
class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(64), primary_key=True, index=True)
    organization_id = Column(String(64), ForeignKey("organizations.id"), nullable=False, index=True)
    created_by_user_id = Column(String(64), ForeignKey("users.id"), nullable=True)
    title = Column(String(128), nullable=False, index=True)
    department = Column(String(64), nullable=False, default="Engineering")
    description = Column(Text, nullable=False)
    responsibilities_json = Column(Text, default="[]")
    required_skills_json = Column(Text, default="[]")
    preferred_skills_json = Column(Text, default="[]")
    min_experience_years = Column(Float, default=3.0)
    location = Column(String(128), default="San Francisco, CA")
    workplace_type = Column(String(32), default="Remote") # Remote, Hybrid, Onsite
    salary_min = Column(Integer, default=140000)
    salary_max = Column(Integer, default=190000)
    equity = Column(String(64), default="0.1% - 0.25%")
    required_education = Column(String(64), default="Bachelor's")
    urgency = Column(String(32), default="High")
    status = Column(String(32), default="Active", index=True) # Active, Closed, Draft, Paused
    benefits_json = Column(Text, default="[]")
    applicants_count = Column(Integer, default=0)
    employment_type = Column(String(32), default="Full-time")  # Full-time | Part-time | Contract | Internship
    openings = Column(Integer, default=1)
    max_experience_years = Column(Float, nullable=True)
    seniority = Column(String(32), default="")
    industry = Column(String(64), default="")
    application_deadline = Column(DateTime, nullable=True)
    screening_questions_json = Column(Text, default="[]")
    interview_criteria_json = Column(Text, default="[]")
    published_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    organization = relationship("Organization", back_populates="jobs")
    skill_links = relationship("JobSkill", back_populates="job", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="job", cascade="all, delete-orphan")

    @property
    def required_skills(self):
        return _parse_json(self.required_skills_json, [])

    @property
    def preferred_skills(self):
        return _parse_json(self.preferred_skills_json, [])

    @property
    def responsibilities(self):
        return _parse_json(self.responsibilities_json, [])

    @property
    def screening_questions(self):
        return _parse_json(self.screening_questions_json, [])

    @property
    def interview_criteria(self):
        return _parse_json(self.interview_criteria_json, [])

    @property
    def benefits(self):
        return _parse_json(self.benefits_json, [])

# =========================================================================
# 6. APPLICATIONS & STAGE AUDIT HISTORY
# =========================================================================
class Application(Base):
    __tablename__ = "applications"

    id = Column(String(64), primary_key=True, index=True)
    job_id = Column(String(64), ForeignKey("jobs.id"), nullable=False, index=True)
    candidate_id = Column(String(64), ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    # Copied from the job so tenant-scoped queries don't need a join
    organization_id = Column(String(64), ForeignKey("organizations.id"), nullable=True, index=True)
    source = Column(String(32), default="applied")  # applied | sourced | referral | import
    match_score = Column(Integer, default=85)
    
    # Stages: Applied, AI Screened, Shortlisted, Interview, Assessment, Offered, Hired, Rejected
    stage = Column(String(32), default="Applied", index=True)
    cover_note = Column(Text, default="")
    score_breakdown_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    job = relationship("Job", back_populates="applications")
    candidate = relationship("CandidateProfile", back_populates="applications")
    stage_history = relationship("ApplicationStageHistory", back_populates="application", cascade="all, delete-orphan")
    interviews = relationship("Interview", back_populates="application", cascade="all, delete-orphan")

    @property
    def score_breakdown(self):
        return _parse_json(self.score_breakdown_json, {})

class ApplicationStageHistory(Base):
    __tablename__ = "application_stage_history"

    id = Column(String(64), primary_key=True, index=True)
    application_id = Column(String(64), ForeignKey("applications.id"), nullable=False, index=True)
    from_stage = Column(String(32), nullable=False)
    to_stage = Column(String(32), nullable=False)
    changed_by_user_id = Column(String(64), ForeignKey("users.id"), nullable=True)
    reason = Column(String(256), default="")
    created_at = Column(DateTime, default=utc_now)

    application = relationship("Application", back_populates="stage_history")

# =========================================================================
# 7. INTERVIEWS & RUBRIC FEEDBACK
# =========================================================================
class Interview(Base):
    __tablename__ = "interviews"

    id = Column(String(64), primary_key=True, index=True)
    application_id = Column(String(64), ForeignKey("applications.id"), nullable=False, index=True)
    interviewer_user_id = Column(String(64), ForeignKey("users.id"), nullable=True)
    round_name = Column(String(128), default="Technical System Design Round")
    scheduled_at = Column(DateTime, nullable=True)
    status = Column(String(32), default="Scheduled") # Scheduled, Completed, Cancelled
    meeting_link = Column(String(256), default="")
    created_at = Column(DateTime, default=utc_now)

    application = relationship("Application", back_populates="interviews")
    feedback = relationship("InterviewFeedback", back_populates="interview", uselist=False, cascade="all, delete-orphan")

class InterviewFeedback(Base):
    __tablename__ = "interview_feedback"

    id = Column(String(64), primary_key=True, index=True)
    interview_id = Column(String(64), ForeignKey("interviews.id"), nullable=False, index=True)
    interviewer_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, default=4) # 1-5
    technical_score = Column(Integer, default=85)
    communication_score = Column(Integer, default=85)
    strengths = Column(Text, default="")
    growth_areas = Column(Text, default="")
    decision = Column(String(32), default="Strong Hire") # Strong Hire, Hire, Leaning Hire, Reject
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=utc_now)

    interview = relationship("Interview", back_populates="feedback")
    interviewer = relationship("User", back_populates="interview_feedback")

# =========================================================================
# 8. PLANS, ENTITLEMENTS & AI USAGE TELEMETRY
# =========================================================================
class Plan(Base):
    __tablename__ = "plans"

    id = Column(String(64), primary_key=True, index=True) # free, pro, business, enterprise
    name = Column(String(128), nullable=False)
    monthly_price = Column(Integer, default=0) # In USD
    max_recruiter_seats = Column(Integer, default=3)
    max_active_jobs = Column(Integer, default=10)
    monthly_ai_credits = Column(Integer, default=1000)
    allow_autonomous_sourcing = Column(Boolean, default=True)
    allow_custom_roadmaps = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)

class AIUsageRecord(Base):
    __tablename__ = "ai_usage_records"

    id = Column(String(64), primary_key=True, index=True)
    organization_id = Column(String(64), ForeignKey("organizations.id"), nullable=True, index=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=True, index=True)
    operation_type = Column(String(64), nullable=False, index=True) # resume_parsing, job_matching, mock_interview, dei_optimization, sourcing_agent
    provider = Column(String(64), default="NexusNLP-v2.5")
    status = Column(String(32), default="SUCCESS", index=True) # SUCCESS, FAILED
    latency_ms = Column(Integer, default=12)
    tokens_consumed = Column(Integer, default=350)
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=utc_now, index=True)

    organization = relationship("Organization", back_populates="ai_usage_records")

# =========================================================================
# 9. NOTIFICATIONS & AUDIT LOGS
# =========================================================================
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(64), primary_key=True, index=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(128), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(32), default="system") # application, stage_change, outreach, system
    link = Column(String(256), default="")
    event_id = Column(String(64), nullable=True, index=True)  # outbox event that caused it (dedupes retries)
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=utc_now)

    # Relationships
    user = relationship("User", back_populates="notifications")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(64), primary_key=True, index=True)
    organization_id = Column(String(64), ForeignKey("organizations.id"), nullable=True, index=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=True, index=True)
    user_email = Column(String(128), default="system")
    action = Column(String(64), nullable=False, index=True)
    module = Column(String(64), nullable=False)
    entity = Column(String(64), nullable=False)
    entity_id = Column(String(64), default="")
    details_json = Column(Text, default="{}")
    ip_address = Column(String(64), default="127.0.0.1")
    status = Column(String(32), default="SUCCESS")
    created_at = Column(DateTime, default=utc_now, index=True)

    # Relationships
    organization = relationship("Organization", back_populates="audit_logs")
    user = relationship("User", back_populates="audit_logs")

    @property
    def details(self):
        return _parse_json(self.details_json, {})

class SkillTaxonomy(Base):
    __tablename__ = "skill_taxonomies"

    id = Column(String(64), primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    category = Column(String(64), default="Languages")
    demand_level = Column(String(32), default="High")
    avg_salary_boost = Column(String(32), default="+15%")
    created_at = Column(DateTime, default=utc_now)

# =========================================================================
# 10. ACCOUNT LIFECYCLE: ONE-TIME TOKENS & TEAM INVITATIONS
# =========================================================================
class UserToken(Base):
    """Opaque single-use tokens (refresh, email verification, password reset).

    Only a SHA-256 hash of the token is stored, so a database leak can't be replayed.
    """
    __tablename__ = "user_tokens"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose = Column(String(32), nullable=False)  # refresh | email_verify | password_reset
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    __table_args__ = (Index("ix_user_tokens_user_purpose", "user_id", "purpose"),)


class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(String(64), primary_key=True)
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(128), nullable=False, index=True)
    role = Column(String(32), nullable=False, default="RECRUITER")
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    invited_by_user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(16), nullable=False, default="pending", index=True)  # pending | accepted | revoked
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    organization = relationship("Organization")


# =========================================================================
# 11. NORMALIZED SKILLS, CERTIFICATIONS, LANGUAGES, NOTES
# =========================================================================
class CandidateSkill(Base):
    __tablename__ = "candidate_skills"

    id = Column(String(64), primary_key=True)
    candidate_id = Column(String(64), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(String(64), ForeignKey("skill_taxonomies.id", ondelete="CASCADE"), nullable=False, index=True)
    years = Column(Float, nullable=True)
    proficiency = Column(String(16), default="")  # beginner | intermediate | advanced | expert
    position = Column(Integer, default=0)  # display order chosen by the candidate

    candidate = relationship("CandidateProfile", back_populates="skill_links")
    skill = relationship("SkillTaxonomy")

    __table_args__ = (Index("uq_candidate_skill", "candidate_id", "skill_id", unique=True),)


class JobSkill(Base):
    __tablename__ = "job_skills"

    id = Column(String(64), primary_key=True)
    job_id = Column(String(64), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(String(64), ForeignKey("skill_taxonomies.id", ondelete="CASCADE"), nullable=False, index=True)
    importance = Column(String(16), nullable=False, default="required")  # required | preferred
    position = Column(Integer, default=0)

    job = relationship("Job", back_populates="skill_links")
    skill = relationship("SkillTaxonomy")

    __table_args__ = (Index("uq_job_skill", "job_id", "skill_id", unique=True),)


class Certification(Base):
    __tablename__ = "certifications"

    id = Column(String(64), primary_key=True)
    candidate_id = Column(String(64), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    issuer = Column(String(128), default="")
    issued_on = Column(String(16), default="")   # "2024-05"
    expires_on = Column(String(16), default="")
    credential_url = Column(String(512), default="")
    created_at = Column(DateTime, default=utc_now)

    candidate = relationship("CandidateProfile", back_populates="certifications")


class CandidateLanguage(Base):
    __tablename__ = "candidate_languages"

    id = Column(String(64), primary_key=True)
    candidate_id = Column(String(64), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    language = Column(String(64), nullable=False)
    proficiency = Column(String(16), default="professional")  # basic | conversational | professional | native

    candidate = relationship("CandidateProfile", back_populates="languages")


class CandidateNote(Base):
    """Private recruiter notes. Always scoped to one organization."""
    __tablename__ = "candidate_notes"

    id = Column(String(64), primary_key=True)
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id = Column(String(64), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    application_id = Column(String(64), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True)
    author_user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now, index=True)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    author = relationship("User")


# =========================================================================
# 12. HIRING PIPELINE CONFIGURATION
# =========================================================================
class PipelineStage(Base):
    """Per-organization pipeline. Organizations without rows use DEFAULT_PIPELINE (services/pipeline_service.py)."""
    __tablename__ = "pipeline_stages"

    id = Column(String(64), primary_key=True)
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(48), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    kind = Column(String(16), nullable=False, default="active")  # active | hired | rejected

    __table_args__ = (Index("uq_pipeline_stage_org_name", "organization_id", "name", unique=True),)


# =========================================================================
# 13. DOCUMENTS (FILE STORAGE METADATA)
# =========================================================================
class Document(Base):
    """A stored file. Bytes live in the storage backend (local disk or S3), never in the database."""
    __tablename__ = "documents"

    id = Column(String(64), primary_key=True)
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    candidate_id = Column(String(64), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=True, index=True)
    uploaded_by_user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    kind = Column(String(32), nullable=False, default="resume")  # resume | attachment | avatar
    filename = Column(String(256), nullable=False)
    content_type = Column(String(128), nullable=False, default="application/octet-stream")
    size_bytes = Column(Integer, nullable=False, default=0)
    sha256 = Column(String(64), nullable=False, index=True)
    storage_backend = Column(String(16), nullable=False, default="local")
    storage_key = Column(String(512), nullable=False)
    created_at = Column(DateTime, default=utc_now)


# =========================================================================
# 14. DOMAIN EVENTS (TRANSACTIONAL OUTBOX)
# =========================================================================
class OutboxEvent(Base):
    """Domain events written in the same transaction as the change that caused them.

    A dispatcher delivers them (notifications today; workflows and webhooks later),
    so a crash between "save" and "notify" can never lose an event.
    """
    __tablename__ = "events_outbox"

    id = Column(String(64), primary_key=True)
    type = Column(String(64), nullable=False, index=True)  # e.g. application.created
    organization_id = Column(String(64), nullable=True, index=True)
    actor_user_id = Column(String(64), nullable=True)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=utc_now, index=True)
    dispatched_at = Column(DateTime, nullable=True, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, default="")

    @property
    def payload(self):
        return _parse_json(self.payload_json, {})


# =========================================================================
# 15. SKILL ONTOLOGY (SYNONYMS AND RELATED SKILLS)
# =========================================================================
class SkillAlias(Base):
    """Another name for a catalog skill, e.g. "k8s" -> Kubernetes, "Postgres" -> PostgreSQL."""
    __tablename__ = "skill_aliases"

    id = Column(String(64), primary_key=True)
    skill_id = Column(String(64), ForeignKey("skill_taxonomies.id", ondelete="CASCADE"), nullable=False, index=True)
    alias = Column(String(128), nullable=False, unique=True, index=True)  # stored lower-case

    skill = relationship("SkillTaxonomy")


class SkillRelation(Base):
    """Two skills that are related, with how much one counts as evidence for the other (0-1).

    kind: "parent" (React -> JavaScript), "related" (Docker <-> Kubernetes), "transferable" (Java <-> C#)
    """
    __tablename__ = "skill_relations"

    id = Column(String(64), primary_key=True)
    skill_id = Column(String(64), ForeignKey("skill_taxonomies.id", ondelete="CASCADE"), nullable=False, index=True)
    related_skill_id = Column(String(64), ForeignKey("skill_taxonomies.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(16), nullable=False, default="related")
    weight = Column(Float, nullable=False, default=0.5)

    __table_args__ = (Index("uq_skill_relation_pair", "skill_id", "related_skill_id", unique=True),)


# =========================================================================
# 16. EMBEDDINGS (SEMANTIC SEARCH AND MATCHING)
# =========================================================================
class Embedding(Base):
    """One vector per (entity, model). pgvector on PostgreSQL; packed float32 bytes elsewhere."""
    __tablename__ = "embeddings"

    id = Column(String(64), primary_key=True)
    entity_type = Column(String(16), nullable=False)  # candidate | job
    entity_id = Column(String(64), nullable=False)
    organization_id = Column(String(64), nullable=True, index=True)  # owner org for private records
    model = Column(String(64), nullable=False)
    content_hash = Column(String(64), nullable=False)  # skip re-embedding unchanged text
    vector = Column(LargeBinary().with_variant(Vector(settings.embedding_dim), "postgresql"), nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (Index("uq_embedding_entity_model", "entity_type", "entity_id", "model", unique=True),)


# =========================================================================
# 17. PERSISTED MATCHES (EXPLAINABLE, VERSIONED)
# =========================================================================
class Match(Base):
    """A computed candidate-to-job match, kept so ranking pages are fast and results are auditable."""
    __tablename__ = "matches"

    id = Column(String(64), primary_key=True)
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(String(64), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id = Column(String(64), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    score = Column(Integer, nullable=False)
    fit_level = Column(String(32), nullable=False)
    factors_json = Column(Text, nullable=False, default="[]")
    strengths_json = Column(Text, nullable=False, default="[]")
    gaps_json = Column(Text, nullable=False, default="[]")
    matching_skills_json = Column(Text, nullable=False, default="[]")
    missing_skills_json = Column(Text, nullable=False, default="[]")
    explanation = Column(Text, nullable=False, default="")
    engine_version = Column(String(16), nullable=False)
    weights_hash = Column(String(16), nullable=False, default="")
    # Hash of everything the score depends on; a different hash means the match is stale
    inputs_hash = Column(String(64), nullable=False, default="")
    # Recruiter decision from the Talent Match screen: new | shortlisted | dismissed
    status = Column(String(16), nullable=False, default="new", index=True)
    computed_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    candidate = relationship("CandidateProfile")
    job = relationship("Job")

    __table_args__ = (
        Index("uq_match_job_candidate", "job_id", "candidate_id", unique=True),
        Index("ix_matches_job_score", "job_id", "score"),
    )

    def _json(self, raw):
        try:
            return json.loads(raw) if raw else []
        except Exception:
            return []

    @property
    def factors(self):
        return self._json(self.factors_json)

    @property
    def strengths(self):
        return self._json(self.strengths_json)

    @property
    def gaps(self):
        return self._json(self.gaps_json)

    @property
    def matching_skills(self):
        return self._json(self.matching_skills_json)

    @property
    def missing_skills(self):
        return self._json(self.missing_skills_json)


# =========================================================================
# 18. AI GOVERNANCE: EVERY MODEL CALL, VERSIONED PROMPTS
# =========================================================================
class AIRequest(Base):
    """One AI feature invocation: who, which feature, which model and prompt version, outcome and cost.

    Outputs are stored only for features whose output contains no personal data
    (see app/ai/orchestrator.py); other features keep a reference instead.
    """
    __tablename__ = "ai_requests"

    id = Column(String(64), primary_key=True)
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    feature = Column(String(48), nullable=False, index=True)        # resume_parse | job_generate | job_analyze | ...
    status = Column(String(16), nullable=False, index=True)         # success | fallback | error | blocked
    provider = Column(String(32), nullable=False, default="")       # groq | gemini | openrouter | rules
    model = Column(String(96), nullable=False, default="")
    prompt_key = Column(String(64), nullable=False, default="")
    prompt_version = Column(Integer, nullable=True)
    input_ref = Column(String(128), nullable=False, default="")     # e.g. "resume:res_123"
    input_chars = Column(Integer, nullable=False, default=0)
    output_json = Column(Text, nullable=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    credits = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Integer, nullable=False, default=0)
    attempts = Column(Text, nullable=False, default="[]")            # providers tried and why they failed
    error = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=utc_now, index=True)


class PromptTemplate(Base):
    """Versioned prompts. Exactly one active version per key; older versions stay for rollback and audit."""
    __tablename__ = "prompt_templates"

    id = Column(String(64), primary_key=True)
    key = Column(String(64), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False, default="draft")  # draft | active | retired
    system = Column(Text, nullable=False)
    user_template = Column(Text, nullable=False)  # str.format placeholders, e.g. {resume_text}
    notes = Column(Text, nullable=False, default="")
    created_by_user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    __table_args__ = (Index("uq_prompt_key_version", "key", "version", unique=True),)
