import json
import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, Index, Enum
)
from sqlalchemy.orm import relationship
from app.core.database import Base

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

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    raw_resume_text = Column(Text, default="")
    ats_score = Column(Integer, default=90)
    profile_strength = Column(Integer, default=95)
    is_searchable = Column(Boolean, default=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="candidate_profile")
    applications = relationship("Application", back_populates="candidate")
    resumes = relationship("Resume", back_populates="candidate", cascade="all, delete-orphan")
    work_experiences = relationship("WorkExperience", back_populates="candidate", cascade="all, delete-orphan")
    education_records = relationship("EducationRecord", back_populates="candidate", cascade="all, delete-orphan")
    projects = relationship("CandidateProject", back_populates="candidate", cascade="all, delete-orphan")

    @property
    def skills(self):
        try:
            return json.loads(self.skills_json) if self.skills_json else []
        except Exception:
            return []

    @skills.setter
    def skills(self, value):
        self.skills_json = json.dumps(value)

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
    created_at = Column(DateTime, default=datetime.utcnow)

    candidate = relationship("CandidateProfile", back_populates="work_experiences")

    @property
    def achievements(self):
        try:
            return json.loads(self.achievements_json) if self.achievements_json else []
        except Exception:
            return []

class EducationRecord(Base):
    __tablename__ = "education_records"

    id = Column(String(64), primary_key=True, index=True)
    candidate_id = Column(String(64), ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    institution = Column(String(128), nullable=False)
    degree = Column(String(128), nullable=False)
    field_of_study = Column(String(128), default="Computer Science")
    graduation_year = Column(Integer, default=2022)
    gpa = Column(String(32), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow)

    candidate = relationship("CandidateProfile", back_populates="projects")

    @property
    def tech_stack(self):
        try:
            return json.loads(self.tech_stack_json) if self.tech_stack_json else []
        except Exception:
            return []

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
    current_version = Column(Integer, default=1)
    is_primary = Column(Boolean, default=True)
    processing_status = Column(String(32), default="Parsed", index=True) # Uploaded, Processing, Parsed, Failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    candidate = relationship("CandidateProfile", back_populates="resumes")
    versions = relationship("ResumeVersion", back_populates="resume", cascade="all, delete-orphan")
    analyses = relationship("ResumeAnalysis", back_populates="resume", cascade="all, delete-orphan")

class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id = Column(String(64), primary_key=True, index=True)
    resume_id = Column(String(64), ForeignKey("resumes.id"), nullable=False, index=True)
    version_number = Column(Integer, default=1)
    storage_path = Column(String(512), default="")
    extracted_text = Column(Text, default="")
    parsed_payload_json = Column(Text, default="{}") # Structured extracted JSON
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow)

    resume = relationship("Resume", back_populates="analyses")
    target_job = relationship("Job")

    @property
    def findings(self):
        try:
            return json.loads(self.findings_json) if self.findings_json else []
        except Exception:
            return []

    @property
    def missing_items(self):
        try:
            return json.loads(self.missing_items_json) if self.missing_items_json else []
        except Exception:
            return []

    @property
    def suggestions(self):
        try:
            return json.loads(self.suggestions_json) if self.suggestions_json else []
        except Exception:
            return []

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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="jobs")
    applications = relationship("Application", back_populates="job", cascade="all, delete-orphan")

    @property
    def required_skills(self):
        try:
            return json.loads(self.required_skills_json) if self.required_skills_json else []
        except Exception:
            return []

    @property
    def preferred_skills(self):
        try:
            return json.loads(self.preferred_skills_json) if self.preferred_skills_json else []
        except Exception:
            return []

    @property
    def responsibilities(self):
        try:
            return json.loads(self.responsibilities_json) if self.responsibilities_json else []
        except Exception:
            return []

    @property
    def benefits(self):
        try:
            return json.loads(self.benefits_json) if self.benefits_json else []
        except Exception:
            return []

# =========================================================================
# 6. APPLICATIONS & STAGE AUDIT HISTORY
# =========================================================================
class Application(Base):
    __tablename__ = "applications"

    id = Column(String(64), primary_key=True, index=True)
    job_id = Column(String(64), ForeignKey("jobs.id"), nullable=False, index=True)
    candidate_id = Column(String(64), ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    match_score = Column(Integer, default=85)
    
    # Stages: Applied, AI Screened, Shortlisted, Interview, Assessment, Offered, Hired, Rejected
    stage = Column(String(32), default="Applied", index=True)
    cover_note = Column(Text, default="")
    score_breakdown_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    job = relationship("Job", back_populates="applications")
    candidate = relationship("CandidateProfile", back_populates="applications")
    stage_history = relationship("ApplicationStageHistory", back_populates="application", cascade="all, delete-orphan")
    interviews = relationship("Interview", back_populates="application", cascade="all, delete-orphan")

    @property
    def score_breakdown(self):
        try:
            return json.loads(self.score_breakdown_json) if self.score_breakdown_json else {}
        except Exception:
            return {}

class ApplicationStageHistory(Base):
    __tablename__ = "application_stage_history"

    id = Column(String(64), primary_key=True, index=True)
    application_id = Column(String(64), ForeignKey("applications.id"), nullable=False, index=True)
    from_stage = Column(String(32), nullable=False)
    to_stage = Column(String(32), nullable=False)
    changed_by_user_id = Column(String(64), ForeignKey("users.id"), nullable=True)
    reason = Column(String(256), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

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
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    organization = relationship("Organization", back_populates="audit_logs")
    user = relationship("User", back_populates="audit_logs")

    @property
    def details(self):
        try:
            return json.loads(self.details_json) if self.details_json else {}
        except Exception:
            return {}

class SkillTaxonomy(Base):
    __tablename__ = "skill_taxonomies"

    id = Column(String(64), primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    category = Column(String(64), default="Languages")
    demand_level = Column(String(32), default="High")
    avg_salary_boost = Column(String(32), default="+15%")
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization")
