from typing import List, Optional, Dict, Any, Union
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
    industry: Optional[str] = None
    plan_tier: Optional[str] = None
    status: Optional[str] = None
    max_recruiter_seats: Optional[int] = None
    max_active_jobs: Optional[int] = None
    monthly_ai_credits: Optional[int] = None

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

    model_config = ConfigDict(from_attributes=True)

class CandidateProfileUpdate(BaseModel):
    title: Optional[str] = None
    bio: Optional[str] = None
    skills: Optional[List[str]] = None
    experience_years: Optional[float] = None
    location: Optional[str] = None
    remote_preference: Optional[str] = None
    expected_salary: Optional[int] = None
    education: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None

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
    status: str = "Active"
    benefits: List[str] = []
    applicants_count: int = 0
    posted_date: str = ""
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class JobCreate(BaseModel):
    organization_id: Optional[str] = None
    title: str
    department: str = "Engineering"
    description: str
    key_responsibilities: List[str] = []
    required_skills: List[str] = []
    preferred_skills: List[str] = []
    min_experience_years: float = 3.0
    location: str = "San Francisco, CA"
    workplace_type: str = "Remote"
    salary_min: int = 140000
    salary_max: int = 190000
    equity: str = "0.1% - 0.25%"
    required_education: str = "Bachelor's"
    urgency: str = "High"
    benefits: List[str] = ["Health & Dental", "Unlimited PTO", "401(k)"]

class JobUpdate(BaseModel):
    title: Optional[str] = None
    department: Optional[str] = None
    description: Optional[str] = None
    required_skills: Optional[List[str]] = None
    preferred_skills: Optional[List[str]] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    status: Optional[str] = None

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
    candidate_id: str
    candidate_name: str
    candidate_email: str
    candidate_avatar: str
    candidate_skills: List[str] = []
    match_score: int
    stage: str
    cover_note: str = ""
    score_breakdown: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None

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
