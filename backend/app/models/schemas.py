from typing import List, Literal, Optional, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict

# =========================================================================
# 1. AUTHENTICATION & USERS
# =========================================================================
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None  # access token lifetime in seconds
    refresh_token: Optional[str] = None
    user: "UserOut"

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class TokenRequest(BaseModel):
    token: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class AcceptInvitationRequest(BaseModel):
    token: str
    full_name: str = Field(min_length=1, max_length=128)
    password: str

class InvitationCreate(BaseModel):
    email: EmailStr
    role: str = "RECRUITER"

class InvitationOut(BaseModel):
    id: str
    organization_id: str
    email: str
    role: str
    status: str
    expires_at: datetime
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class MessageResponse(BaseModel):
    message: str

class RegisterCandidateRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    title: str = "Software Engineer"
    skills: List[str] = []
    experience_years: float = 2.0
    location: str = "San Francisco, CA"
    remote_preference: str = "Remote"
    expected_salary: int = 140000

class RegisterEmployerRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company_name: str
    company_domain: str
    industry: str = "Software & AI"

class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    organization_id: Optional[str] = None
    avatar_url: Optional[str] = None
    status: str = "Active"
    is_active: bool = True
    email_verified: bool = True
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class UserStatusUpdate(BaseModel):
    status: str # Active, Suspended, Inactive
    role: Optional[str] = None

# =========================================================================
# 2. ORGANIZATIONS
# =========================================================================
class OrganizationOut(BaseModel):
    id: str
    name: str
    domain: str
    industry: str = "Software & AI"
    plan_tier: str = "Enterprise"
    logo_icon: str = "briefcase"
    website: str = ""
    status: str = "Active"
    is_active: bool = True
    max_recruiter_seats: int = 10
    max_active_jobs: int = 50
    monthly_ai_credits: int = 5000
    monthly_ai_credits_used: int = 0
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class OrganizationCreate(BaseModel):
    name: str
    domain: str
    industry: str = "Software & AI"
    plan_tier: str = "Enterprise"
    logo_icon: str = "briefcase"
    website: str = ""

class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    industry: Optional[str] = None
    plan_tier: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None
    max_recruiter_seats: Optional[int] = None
    max_active_jobs: Optional[int] = None
    monthly_ai_credits: Optional[int] = None

class AdminUserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    organization_id: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None

class EncryptionStatusOut(BaseModel):
    status: str
    algorithm: str
    key_derived: bool
    key_source: str
    keys_configured: int
    token_prefix: str
    protected_fields: List[str]
    self_test_passed: bool

class EncryptionTestRequest(BaseModel):
    text: str = Field(..., max_length=500)

class EncryptionTestResponse(BaseModel):
    original: str
    encrypted: str
    decrypted: str
    is_valid: bool

# =========================================================================
# 3. CANDIDATE PROFILES & SUB-ENTITIES
# =========================================================================
class WorkExperienceOut(BaseModel):
    id: str
    company_name: str
    job_title: str
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    is_current: bool = False
    description: str = ""
    achievements: List[str] = []

    model_config = ConfigDict(from_attributes=True)

class WorkExperienceCreate(BaseModel):
    company_name: str
    job_title: str
    location: str = ""
    start_date: str = ""
    end_date: str = "Present"
    is_current: bool = False
    description: str = ""
    achievements: List[str] = []

class EducationRecordOut(BaseModel):
    id: str
    institution: str
    degree: str
    field_of_study: str = ""
    graduation_year: int = 2022
    gpa: Optional[str] = ""

    model_config = ConfigDict(from_attributes=True)

class EducationRecordCreate(BaseModel):
    institution: str
    degree: str
    field_of_study: str = "Computer Science"
    graduation_year: int = 2022
    gpa: str = ""

class CandidateProjectOut(BaseModel):
    id: str
    title: str
    description: str
    tech_stack: List[str] = []
    live_url: str = ""
    repo_url: str = ""

    model_config = ConfigDict(from_attributes=True)

class CandidateProfileOut(BaseModel):
    id: str
    user_id: Optional[str] = ""
    name: str = ""
    email: str = ""
    title: str = ""
    bio: str = ""
    skills: List[str] = []
    experience_years: float = 0.0
    location: str = ""
    remote_preference: str = "Remote"
    expected_salary: int = 120000
    education: str = "Bachelor's"
    github_url: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""
    ats_score: int = 85
    profile_strength: int = 90
    avatar_url: Optional[str] = ""
    # Phase 2 summary fields
    availability: str = "open"
    notice_period_days: Optional[int] = None
    preferred_locations: List[str] = []
    source: str = "self_registered"
    owner_org_id: Optional[str] = None
    last_active_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    # False when the caller may see the profile but not the person's email/phone
    contact_visible: bool = True

    model_config = ConfigDict(from_attributes=True)

Availability = Literal["open", "passive", "not_looking"]
RemotePreference = Literal["Remote", "Hybrid", "Onsite", "Flexible"]

class WorkExperienceItem(BaseModel):
    company_name: str = Field(min_length=1, max_length=128)
    job_title: str = Field(min_length=1, max_length=128)
    location: str = Field("", max_length=128)
    start_date: str = Field("", max_length=32, description="YYYY-MM")
    end_date: str = Field("", max_length=32, description="YYYY-MM, empty when current")
    is_current: bool = False
    description: str = Field("", max_length=5000)
    achievements: List[str] = Field(default_factory=list, max_length=30)

class EducationItem(BaseModel):
    institution: str = Field(min_length=1, max_length=128)
    degree: str = Field(min_length=1, max_length=128)
    field_of_study: str = Field("", max_length=128)
    graduation_year: Optional[int] = Field(None, ge=1950, le=2100)
    gpa: str = Field("", max_length=32)

class CertificationItem(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    issuer: str = Field("", max_length=128)
    issued_on: str = Field("", max_length=16)
    expires_on: str = Field("", max_length=16)
    credential_url: str = Field("", max_length=512)

class LanguageItem(BaseModel):
    language: str = Field(min_length=1, max_length=64)
    proficiency: Literal["basic", "conversational", "professional", "native"] = "professional"

class ProjectItem(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    description: str = Field("", max_length=5000)
    tech_stack: List[str] = Field(default_factory=list, max_length=30)
    live_url: str = Field("", max_length=256)
    repo_url: str = Field("", max_length=256)

class CandidateDetailOut(CandidateProfileOut):
    phone: str = ""
    industry: str = ""
    available_from: Optional[datetime] = None
    employment_types: List[str] = []
    is_searchable: bool = True
    work_experience: List[WorkExperienceItem] = []
    education_records: List[EducationItem] = []
    certifications: List[CertificationItem] = []
    languages: List[LanguageItem] = []
    projects: List[ProjectItem] = []

class CandidateProfileBaseFields(BaseModel):
    title: Optional[str] = Field(None, max_length=128)
    bio: Optional[str] = Field(None, max_length=5000)
    phone: Optional[str] = Field(None, max_length=32)
    skills: Optional[List[str]] = Field(None, max_length=100)
    experience_years: Optional[float] = Field(None, ge=0, le=60)
    location: Optional[str] = Field(None, max_length=128)
    remote_preference: Optional[str] = None
    expected_salary: Optional[int] = Field(None, ge=0)
    education: Optional[str] = Field(None, max_length=128)
    industry: Optional[str] = Field(None, max_length=64)
    notice_period_days: Optional[int] = Field(None, ge=0, le=365)
    availability: Optional[Availability] = None
    available_from: Optional[datetime] = None
    preferred_locations: Optional[List[str]] = Field(None, max_length=20)
    employment_types: Optional[List[str]] = Field(None, max_length=5)
    is_searchable: Optional[bool] = None
    github_url: Optional[str] = Field(None, max_length=256)
    linkedin_url: Optional[str] = Field(None, max_length=256)
    portfolio_url: Optional[str] = Field(None, max_length=256)
    work_experience: Optional[List[WorkExperienceItem]] = Field(None, max_length=30)
    education_records: Optional[List[EducationItem]] = Field(None, max_length=15)
    certifications: Optional[List[CertificationItem]] = Field(None, max_length=30)
    languages: Optional[List[LanguageItem]] = Field(None, max_length=15)
    projects: Optional[List[ProjectItem]] = Field(None, max_length=30)

class CandidateProfileUpdate(CandidateProfileBaseFields):
    """Partial update. List fields (experience, education, ...) replace the whole list when sent."""
    full_name: Optional[str] = Field(None, min_length=1, max_length=128)

class SourcedCandidateCreate(CandidateProfileBaseFields):
    """A recruiter adds someone who isn't on the platform yet. Private to the recruiter's organization."""
    full_name: str = Field(..., min_length=1, max_length=128)
    email: EmailStr
    title: Optional[str] = Field("", max_length=128)
    # From POST /ai/resume/parse (recruiter, no candidate yet): attach that file as their resume
    resume_document_id: Optional[str] = None

class CandidateNoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    application_id: Optional[str] = None

class CandidateNoteOut(BaseModel):
    id: str
    candidate_id: str
    application_id: Optional[str] = None
    author_user_id: Optional[str] = None
    author_name: str = ""
    body: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# =========================================================================
# 4. RESUMES & MULTI-DIMENSION QUALITY ANALYSIS
# =========================================================================
class ResumeAnalysisOut(BaseModel):
    id: str
    resume_id: str
    target_job_id: Optional[str] = None
    ats_compatibility_score: int = 85
    skills_coverage_score: int = 85
    experience_presentation_score: int = 85
    achievement_strength_score: int = 85
    keyword_alignment_score: int = 85
    formatting_completeness_score: int = 85
    overall_quality_score: int = 85
    findings: List[str] = []
    missing_items: List[str] = []
    suggestions: List[str] = []
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ResumeOut(BaseModel):
    id: str
    candidate_id: str
    title: str = "Resume"
    original_filename: str = "resume.pdf"
    file_format: str = "pdf"
    file_size_bytes: int = 0
    current_version: int = 1
    is_primary: bool = True
    processing_status: str = "Completed"
    created_at: Optional[datetime] = None
    document_id: Optional[str] = None  # use POST /documents/{id}/download-url to download the file
    latest_analysis: Optional[ResumeAnalysisOut] = None

    model_config = ConfigDict(from_attributes=True)

# =========================================================================
# 5. JOBS & REQUISITIONS
# =========================================================================
class JobOut(BaseModel):
    id: str
    organization_id: str = ""
    company_name: str = ""
    company_domain: str = ""
    company_logo: str = "briefcase"
    title: str = ""
    department: str = "Engineering"
    description: str = ""
    key_responsibilities: List[str] = []
    responsibilities: List[str] = []
    required_skills: List[str] = []
    preferred_skills: List[str] = []
    min_experience_years: float = 3.0
    location: str = "San Francisco, CA"
    workplace_type: str = "Remote"
    salary_min: int = 120000
    salary_max: int = 180000
    equity: str = "0.1% - 0.25%"
    required_education: str = "Bachelor's"
    urgency: str = "High"
    status: str = "Active"  # Draft | Active (published) | Paused | Closed | Archived
    benefits: List[str] = []
    applicants_count: int = 0
    employment_type: str = "Full-time"
    openings: int = 1
    max_experience_years: Optional[float] = None
    seniority: str = ""
    industry: str = ""
    application_deadline: Optional[datetime] = None
    published_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    screening_questions: List[str] = []
    interview_criteria: List[str] = []
    posted_date: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

WorkplaceType = Literal["Remote", "Hybrid", "Onsite"]
EmploymentType = Literal["Full-time", "Part-time", "Contract", "Internship", "Temporary"]

class JobCreate(BaseModel):
    organization_id: Optional[str] = None  # ignored: jobs are always created in the caller's organization
    title: str = Field(min_length=2, max_length=128)
    department: str = Field("Engineering", max_length=64)
    description: str = Field(min_length=1, max_length=20000)
    key_responsibilities: List[str] = []
    required_skills: List[str] = Field(default_factory=list, max_length=50)
    preferred_skills: List[str] = Field(default_factory=list, max_length=50)
    min_experience_years: float = Field(3.0, ge=0, le=50)
    max_experience_years: Optional[float] = Field(None, ge=0, le=60)
    location: str = Field("San Francisco, CA", max_length=128)
    workplace_type: str = "Remote"
    employment_type: EmploymentType = "Full-time"
    openings: int = Field(1, ge=1, le=1000)
    seniority: str = Field("", max_length=32)
    industry: str = Field("", max_length=64)
    application_deadline: Optional[datetime] = None
    salary_min: int = Field(140000, ge=0)
    salary_max: int = Field(190000, ge=0)
    equity: str = "0.1% - 0.25%"
    required_education: str = "Bachelor's"
    urgency: str = "High"
    benefits: List[str] = ["Health & Dental", "Unlimited PTO", "401(k)"]
    screening_questions: List[str] = Field(default_factory=list, max_length=20)
    interview_criteria: List[str] = Field(default_factory=list, max_length=20)
    # Published immediately by default (classic UI behaviour); send "Draft" to save without publishing.
    status: Literal["Draft", "Active"] = "Active"

class JobUpdate(BaseModel):
    """Partial update: only fields that are sent are changed. Status changes use the lifecycle actions."""
    title: Optional[str] = Field(None, min_length=2, max_length=128)
    department: Optional[str] = Field(None, max_length=64)
    description: Optional[str] = Field(None, min_length=1, max_length=20000)
    key_responsibilities: Optional[List[str]] = None
    required_skills: Optional[List[str]] = Field(None, max_length=50)
    preferred_skills: Optional[List[str]] = Field(None, max_length=50)
    min_experience_years: Optional[float] = Field(None, ge=0, le=50)
    max_experience_years: Optional[float] = Field(None, ge=0, le=60)
    location: Optional[str] = Field(None, max_length=128)
    workplace_type: Optional[str] = None
    employment_type: Optional[EmploymentType] = None
    openings: Optional[int] = Field(None, ge=1, le=1000)
    seniority: Optional[str] = Field(None, max_length=32)
    industry: Optional[str] = Field(None, max_length=64)
    application_deadline: Optional[datetime] = None
    salary_min: Optional[int] = Field(None, ge=0)
    salary_max: Optional[int] = Field(None, ge=0)
    equity: Optional[str] = None
    required_education: Optional[str] = None
    urgency: Optional[str] = None
    benefits: Optional[List[str]] = None
    screening_questions: Optional[List[str]] = Field(None, max_length=20)
    interview_criteria: Optional[List[str]] = Field(None, max_length=20)

# =========================================================================
# 6. VECTOR RECOMMENDER & EXPLAINABILITY SCHEMAS
# =========================================================================
class ScoreBreakdown(BaseModel):
    skills_score: float = 90.0
    experience_score: float = 95.0
    location_score: float = 100.0
    salary_score: float = 90.0
    education_score: float = 90.0
    skill_match_score: float = 90.0
    experience_match_score: float = 95.0
    location_match_score: float = 100.0
    salary_match_score: float = 90.0

class SkillRecommendation(BaseModel):
    skill: str = ""
    skill_name: Optional[str] = ""
    category: str = "Engineering Competency"
    recommended_action: str = ""
    estimated_learning_time: str = "2-4 weeks"
    market_demand: str = "High"
    priority: str = "Recommended"

class MatchExplanation(BaseModel):
    overall_match_percentage: int = 90
    fit_level: str = "Strong Match"
    strengths: List[str] = []
    gaps: List[str] = []
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    missing_critical_skills: List[str] = []
    missing_preferred_skills: List[str] = []
    recommendations_for_candidate: List[SkillRecommendation] = []
    recommended_skills: List[SkillRecommendation] = []
    score_breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    breakdown: Any = Field(default_factory=ScoreBreakdown)
    rationale: str = ""

class JobMatchResult(BaseModel):
    job: JobOut
    match_score: int
    fit_level: str = "Strong Match"
    explanation: MatchExplanation

class CandidateMatchResult(BaseModel):
    candidate: CandidateProfileOut
    match_score: int
    fit_level: str = "Strong Match"
    pipeline_stage: str = "Sourced"
    explanation: MatchExplanation

# =========================================================================
# 7. AI COPILOT & AUTOMATION SCHEMAS
# =========================================================================
class OutreachPitchRequest(BaseModel):
    candidate_id: str
    job_id: str
    tone: str = "Compelling & Visionary"

class OutreachPitchResponse(BaseModel):
    subject_line: str
    email_body: str
    pitch_content: str = ""
    personalized_hook: str = ""
    key_selling_points: List[str] = []
    candidate_id: Optional[str] = None
    job_id: Optional[str] = None

class ResumeTailorRequest(BaseModel):
    candidate_id: Optional[str] = ""
    resume_text: Optional[str] = ""
    target_job_id: str

class ResumeTailorResponse(BaseModel):
    ats_compatibility_score: int
    matched_keywords: List[str] = []
    missing_keywords: List[str] = []
    optimized_summary: str = ""
    tailored_summary: str = ""
    bullet_point_enhancements: List[Any] = []
    suggested_bullet_points: List[str] = []
    missing_skills: List[str] = []

class InterviewQuestion(BaseModel):
    category: str
    question: str
    why_asked: str = ""
    expected_answer_points: List[str] = []
    sample_answer: str = ""
    probing_focus: str = ""

class InterviewPrepRequest(BaseModel):
    candidate_id: str
    job_id: str

class InterviewPrepResponse(BaseModel):
    role_title: str = ""
    job_title: str = ""
    candidate_name: str
    overall_readiness_score: int = 90
    technical_focus_areas: List[str] = []
    questions: List[InterviewQuestion] = []

class JobSpecGenerateRequest(BaseModel):
    prompt: Optional[str] = None
    title: Optional[str] = None
    department: Optional[str] = "Engineering"
    workplace_type: Optional[str] = "Remote"

class JobSpecGenerateResponse(BaseModel):
    title: str
    department: str
    description: str
    salary_min: int = 140000
    salary_max: int = 200000
    required_skills: List[str] = []
    preferred_skills: List[str] = []
    key_responsibilities: List[str] = []
    responsibilities: List[str] = []
    min_experience_years: float = 3.0
    equity: str = "0.1% - 0.25%"
    benefits: List[str] = []

class AutoScreenApplicationResponse(BaseModel):
    application_id: str
    candidate_name: str = ""
    job_title: str = ""
    company_name: str = ""
    match_score: int = 85
    overall_screening_score: int = 85
    recommendation: str = "Advance to Interview"
    advanced_stage: str = "AI Screened"
    technical_fit_score: int = 90
    experience_fit_score: int = 88
    architecture_fit_score: int = 92
    compensation_alignment: str = "Optimal"
    key_strengths: List[str] = []
    identified_gaps: List[str] = []
    hiring_manager_probing_questions: List[str] = []
    executive_summary: str = ""
    automated_stage_updated: str = "AI Screened"
    rubric_breakdown: Dict[str, Any] = Field(default_factory=dict)
    screening_notes: str = ""

class OutreachStep(BaseModel):
    step_number: int
    channel: str
    delay_days: int
    subject: str
    message: str
    call_to_action: str

class SourcedCandidate(BaseModel):
    candidate: CandidateProfileOut
    match_score: int
    fit_level: str
    match_reasons: List[str]
    outreach_sequence: List[OutreachStep]

class AutonomousSourcingRequest(BaseModel):
    job_id: str
    candidate_limit: int = 5
    target_count: int = 5
    campaign_tone: str = "Compelling & Visionary"
    tone: str = "Compelling & Visionary"

class AutonomousSourcingResponse(BaseModel):
    job_id: str
    job_title: str
    total_candidates_analyzed: int = 0
    total_candidates_scanned: int = 0
    top_matches_found: int = 0
    sourced_candidates: List[Any] = []
    sourcing_summary: str = ""

class MockInterviewGradeRequest(BaseModel):
    question: str
    category: str
    candidate_answer: str
    target_job: Optional[str] = None
    job_title: Optional[str] = "Staff Backend Engineer"
    target_company: Optional[str] = "Top-tier Tech"

class MockInterviewGradeResponse(BaseModel):
    composite_score: int = 85
    overall_score: int = 85
    technical_depth_score: int = 85
    system_scalability_score: int = 85
    communication_clarity_score: int = 85
    hiring_signal: str = "Strong Hire"
    strengths: List[str] = []
    weaknesses: List[str] = []
    areas_for_improvement: List[str] = []
    improvement_tips: List[str] = []
    exemplary_model_answer: str = ""
    exemplary_answer: str = ""
    rubric: Dict[str, Any] = Field(default_factory=dict)

class JobSpecOptimizeRequest(BaseModel):
    raw_job_description: Optional[str] = None
    draft_spec: Optional[str] = None
    job_title: str = "Senior Engineer"
    industry: Optional[str] = "Software & AI"

class JobSpecOptimizeResponse(BaseModel):
    original_inclusivity_score: int = 65
    optimized_inclusivity_score: int = 95
    inclusivity_score: int = 95
    detected_biases_and_fixes: List[Dict[str, Any]] = []
    identified_bias_flags: List[str] = []
    unrealistic_requirements_flagged: List[str] = []
    optimized_job_description: str = ""
    optimized_spec: str = ""
    estimated_talent_pool_expansion_pct: int = 35
    estimated_candidate_pool_expansion_pct: int = 35

class LearningRoadmapWeek(BaseModel):
    week_number: int
    theme: str
    core_objectives: List[str]
    recommended_reading_and_papers: List[str]
    hands_on_lab_or_repo: str
    target_interview_problems: List[str]

class LearningRoadmapRequest(BaseModel):
    candidate_id: str
    target_job_id: str

class LearningRoadmapResponse(BaseModel):
    candidate_name: str
    target_role: str = ""
    target_job_title: str = ""
    target_company: str = ""
    current_match_score: int
    projected_match_score: int = 95
    projected_post_roadmap_score: int = 95
    critical_skills_to_acquire: List[str] = []
    weeks: List[LearningRoadmapWeek] = []
    four_week_plan: List[Dict[str, Any]] = []
    executive_advice: str = ""

class CandidateDossierResponse(BaseModel):
    candidate: CandidateProfileOut
    verified_certifications: List[str] = []
    top_technical_superpowers: List[Dict[str, Any]] = []
    market_compensation_benchmark: Dict[str, Any] = Field(default_factory=dict)
    interview_risk_matrix: Dict[str, Any] = Field(default_factory=dict)
    overall_readiness_grade: str = "A+ (Ready for Immediate Offer)"
    suggested_leveling: str = "Staff Engineer / L6"

class AnalyticsOverview(BaseModel):
    total_candidates: int
    active_jobs: int
    total_applications: int
    average_match_score: float = 92.4
    top_demanded_skills: List[Dict[str, Any]] = []
    department_distribution: List[Dict[str, Any]] = []
    salary_trends: List[Dict[str, Any]] = []
    recent_placements_count: int = 28

# =========================================================================
# 8. APPLICATIONS & STAGE AUDIT
# =========================================================================
class StageHistoryOut(BaseModel):
    id: str
    application_id: str
    from_stage: str
    to_stage: str
    reason: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ApplicationOut(BaseModel):
    id: str
    job_id: str
    job_title: str
    company_name: str
    company_logo: str = "briefcase"
    organization_id: Optional[str] = None
    candidate_id: str
    candidate_name: str
    candidate_email: str
    candidate_avatar: str
    candidate_title: str = ""
    candidate_location: str = ""
    candidate_experience_years: float = 0.0
    candidate_skills: List[str] = []
    match_score: int
    stage: str
    source: str = "applied"
    cover_note: str = ""
    score_breakdown: Dict[str, Any] = Field(default_factory=dict)
    applied_date: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ApplicationCreate(BaseModel):
    job_id: str
    # Candidates apply as themselves (leave empty); recruiters adding someone must set it.
    candidate_id: Optional[str] = None
    cover_note: str = ""

ApplicationSubmitRequest = ApplicationCreate

class ApplicationStageUpdate(BaseModel):
    stage: str
    reason: Optional[str] = "Pipeline stage advanced"

ApplicationStageUpdateRequest = ApplicationStageUpdate

# =========================================================================
# 9. INTERVIEWS & FEEDBACK
# =========================================================================
class InterviewFeedbackOut(BaseModel):
    id: str
    rating: int
    technical_score: int
    communication_score: int
    strengths: str
    growth_areas: str
    decision: str
    notes: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class InterviewFeedbackCreate(BaseModel):
    rating: int = 4
    technical_score: int = 85
    communication_score: int = 85
    strengths: str = ""
    growth_areas: str = ""
    decision: str = "Hire"
    notes: str = ""

class InterviewOut(BaseModel):
    id: str
    application_id: str
    round_name: str
    scheduled_at: Optional[datetime] = None
    status: str
    meeting_link: str
    feedback: Optional[InterviewFeedbackOut] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class InterviewCreate(BaseModel):
    application_id: str
    interviewer_user_id: Optional[str] = None
    round_name: str = "Technical System Design"
    scheduled_at: Optional[datetime] = None
    meeting_link: str = "https://meet.google.com/xyz-abcd-efg"

# =========================================================================
# 10. AI TELEMETRY & PLANS
# =========================================================================
class AIUsageRecordOut(BaseModel):
    id: str
    organization_id: Optional[str] = None
    operation_type: str
    provider: str
    status: str
    latency_ms: int
    tokens_consumed: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class PlanOut(BaseModel):
    id: str
    name: str
    monthly_price: int
    max_recruiter_seats: int
    max_active_jobs: int
    monthly_ai_credits: int
    allow_autonomous_sourcing: bool
    allow_custom_roadmaps: bool

    model_config = ConfigDict(from_attributes=True)

# =========================================================================
# 11. NOTIFICATIONS & AUDIT LOGS
# =========================================================================
class NotificationOut(BaseModel):
    id: str
    title: str
    message: str
    type: str
    link: str
    is_read: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class AuditLogOut(BaseModel):
    id: str
    organization_id: Optional[str] = None
    user_email: str
    action: str
    module: str
    entity: str
    entity_id: str
    details: Dict[str, Any] = Field(default_factory=dict)
    ip_address: str
    status: str = "SUCCESS"
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class SkillTaxonomyOut(BaseModel):
    id: str
    name: str
    category: str
    demand_level: str
    avg_salary_boost: str

    model_config = ConfigDict(from_attributes=True)

class AdminSystemStats(BaseModel):
    total_organizations: int
    total_users: int
    total_candidates: int
    total_recruiters: int
    total_jobs: int
    total_applications: int
    total_resumes_processed: int
    total_ai_requests_today: int
    system_health_pct: float
    engine_uptime: str
    database_status: str
