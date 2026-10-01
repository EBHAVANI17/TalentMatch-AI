"""Structured outputs of AI features. Lenient on input (models vary) but always normalized on output."""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


def _clean_list(values) -> List[str]:
    out: List[str] = []
    for v in values or []:
        if isinstance(v, str) and v.strip() and v.strip() not in out:
            out.append(v.strip())
    return out


class _Lenient(BaseModel):
    model_config = {"extra": "ignore"}


class ExperienceDraft(_Lenient):
    job_title: str = ""
    company_name: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    is_current: bool = False
    description: str = ""
    achievements: List[str] = []

    @field_validator("achievements", mode="before")
    @classmethod
    def clean_lists(cls, v):
        return _clean_list(v)


class EducationDraft(_Lenient):
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    graduation_year: Optional[int] = None

    @field_validator("graduation_year", mode="before")
    @classmethod
    def _year(cls, v):
        try:
            year = int(str(v)[:4]) if v not in (None, "") else None
        except ValueError:
            return None
        return year if year and 1950 <= year <= 2100 else None


class CertificationDraft(_Lenient):
    name: str = ""
    issuer: str = ""
    issued_on: str = ""


class ProjectDraft(_Lenient):
    title: str = ""
    description: str = ""
    tech_stack: List[str] = []

    @field_validator("tech_stack", mode="before")
    @classmethod
    def clean_lists(cls, v):
        return _clean_list(v)


class LanguageDraft(_Lenient):
    language: str = ""
    proficiency: str = "professional"

    @field_validator("proficiency", mode="before")
    @classmethod
    def _level(cls, v):
        v = (v or "").lower()
        return v if v in {"basic", "conversational", "professional", "native"} else "professional"


class ResumeDraft(_Lenient):
    headline: str = ""
    summary: str = ""
    total_experience_years: Optional[float] = None
    skills: List[str] = []
    work_experience: List[ExperienceDraft] = []
    education: List[EducationDraft] = []
    certifications: List[CertificationDraft] = []
    projects: List[ProjectDraft] = []
    languages: List[LanguageDraft] = []
    industries: List[str] = []

    @field_validator("skills", "industries", mode="before")
    @classmethod
    def clean_lists(cls, v):
        return _clean_list(v)

    @field_validator("total_experience_years", mode="before")
    @classmethod
    def _years(cls, v):
        try:
            return round(float(v), 1) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None


class ContactInfo(BaseModel):
    """Extracted locally with patterns; never sent to or produced by an AI model."""
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""


class JobDraft(_Lenient):
    title: str = ""
    department: str = ""
    seniority: str = ""
    employment_type: str = "Full-time"
    workplace_type: str = "Remote"
    location: str = ""
    description: str = ""
    responsibilities: List[str] = []
    required_skills: List[str] = []
    preferred_skills: List[str] = []
    min_experience_years: float = 0
    max_experience_years: Optional[float] = None
    required_education: str = "Bachelor's"
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    interview_criteria: List[str] = []
    screening_questions: List[str] = []

    @field_validator("responsibilities", "required_skills", "preferred_skills", "interview_criteria", "screening_questions", mode="before")
    @classmethod
    def clean_lists(cls, v):
        return _clean_list(v)

    @field_validator("min_experience_years", mode="before")
    @classmethod
    def _min(cls, v):
        try:
            return max(0.0, float(v or 0))
        except (TypeError, ValueError):
            return 0.0


class JobAnalysis(_Lenient):
    title: str = ""
    seniority: str = ""
    industry: str = ""
    employment_type: str = ""
    workplace_type: str = ""
    location: str = ""
    required_skills: List[str] = []
    preferred_skills: List[str] = []
    min_experience_years: Optional[float] = None
    max_experience_years: Optional[float] = None
    required_education: str = ""
    certifications: List[str] = []
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    responsibilities: List[str] = []

    @field_validator("required_skills", "preferred_skills", "certifications", "responsibilities", mode="before")
    @classmethod
    def clean_lists(cls, v):
        return _clean_list(v)


class BriefIn(BaseModel):
    brief: str = Field(min_length=3, max_length=2000)


class JobTextIn(BaseModel):
    text: str = Field(min_length=20, max_length=20000)
