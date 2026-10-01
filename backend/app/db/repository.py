from typing import List, Optional, Dict
import copy
from app.db.seed_data import SEED_CANDIDATES, SEED_JOBS, SKILL_TAXONOMY, INITIAL_APPLICATIONS
from app.models.schemas import Candidate, CandidateCreate, Job, JobCreate, SkillTaxonomyItem, ApplicationRecord, ApplicationSubmission

class InMemoryRepository:
    def __init__(self):
        self.candidates: Dict[str, dict] = {c["id"]: copy.deepcopy(c) for c in SEED_CANDIDATES}
        self.jobs: Dict[str, dict] = {j["id"]: copy.deepcopy(j) for j in SEED_JOBS}
        self.skills: List[dict] = copy.deepcopy(SKILL_TAXONOMY)
        self.applications: Dict[str, dict] = {a["id"]: copy.deepcopy(a) for a in INITIAL_APPLICATIONS}
        self._cand_counter = len(SEED_CANDIDATES) + 1
        self._job_counter = len(SEED_JOBS) + 1
        self._app_counter = len(INITIAL_APPLICATIONS) + 1

    # Candidate operations
    def get_all_candidates(self) -> List[Candidate]:
        return [Candidate(**c) for c in self.candidates.values()]

    def get_candidate(self, candidate_id: str) -> Optional[Candidate]:
        data = self.candidates.get(candidate_id)
        if data:
            return Candidate(**data)
        return None

    def create_candidate(self, candidate: CandidateCreate) -> Candidate:
        cand_id = f"cand_{self._cand_counter:03d}"
        self._cand_counter += 1
        data = candidate.model_dump()
        data["id"] = cand_id
        data["ats_score"] = 92
        data["profile_strength"] = 95
        if not data.get("avatar_url"):
            data["avatar_url"] = "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=200"
        self.candidates[cand_id] = data
        return Candidate(**data)

    # Job operations
    def get_all_jobs(self) -> List[Job]:
        return [Job(**j) for j in self.jobs.values()]

    def get_job(self, job_id: str) -> Optional[Job]:
        data = self.jobs.get(job_id)
        if data:
            return Job(**data)
        return None

    def create_job(self, job: JobCreate) -> Job:
        job_id = f"job_{self._job_counter:03d}"
        self._job_counter += 1
        data = job.model_dump()
        data["id"] = job_id
        data["posted_date"] = "2026-09-25"
        data["applicants_count"] = 0
        data["status"] = "Active"
        if not data.get("company_logo"):
            data["company_logo"] = "🚀"
        self.jobs[job_id] = data
        return Job(**data)

    def get_skills_taxonomy(self) -> List[SkillTaxonomyItem]:
        return [SkillTaxonomyItem(**s) for s in self.skills]

    # Application operations
    def get_candidate_applications(self, candidate_id: str) -> List[ApplicationRecord]:
        return [ApplicationRecord(**a) for a in self.applications.values() if a["candidate_id"] == candidate_id]

    def create_application(self, submission: ApplicationSubmission, match_score: int) -> ApplicationRecord:
        app_id = f"app_{self._app_counter:03d}"
        self._app_counter += 1
        
        job = self.get_job(submission.job_id)
        job_title = job.title if job else "Engineering Role"
        company = job.company if job else "Enterprise Tech"

        data = {
            "id": app_id,
            "candidate_id": submission.candidate_id,
            "job_id": submission.job_id,
            "job_title": job_title,
            "company": company,
            "applied_date": "2026-09-25",
            "match_score": match_score,
            "status": "AI Screened",
            "cover_note": submission.cover_note
        }
        self.applications[app_id] = data
        
        # Increment applicant count on job
        if submission.job_id in self.jobs:
            self.jobs[submission.job_id]["applicants_count"] = self.jobs[submission.job_id].get("applicants_count", 0) + 1
            
        return ApplicationRecord(**data)

    def update_application_stage(self, app_id: str, new_stage: str) -> Optional[ApplicationRecord]:
        if app_id in self.applications:
            self.applications[app_id]["status"] = new_stage
            return ApplicationRecord(**self.applications[app_id])
        return None

repo = InMemoryRepository()
