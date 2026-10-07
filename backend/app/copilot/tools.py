"""Read-only tools the copilot uses to look things up.

Every tool works inside the caller's organization through the tenancy helpers, so
neither a model nor a crafted question can reach another tenant's records. Tools
return facts without names or contact details; free text is redacted.
"""
import re
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.copilot.records import RefBook, Record
from app.core.tenancy import TenantContext, can_view_candidate, scope_applications, scope_candidates
from app.matching import service as matching
from app.matching.redaction import redact
from app.models.db_models import Application, CandidateProfile, Interview, Job
from app.search import service as search
from app.matching.ontology import get_skill_graph
from app.services.dashboard_service import recruiter_dashboard

MAX_RESULTS = 8


# ---------------------------------------------------------------------------
# Facts (never names, emails, phones or links)
# ---------------------------------------------------------------------------
def candidate_facts(c: CandidateProfile) -> dict:
    name = c.user.full_name if c.user else ""
    facts = {
        "headline": redact(c.title or "", names=[name]),
        "experience_years": c.experience_years,
        "location": c.location or "",
        "work_mode": c.remote_preference or "",
        "skills": (c.skills or [])[:12],
        "availability": c.availability or "",
    }
    if c.notice_period_days is not None:
        facts["notice_period_days"] = c.notice_period_days
    if c.bio:
        facts["summary"] = redact(c.bio, names=[name])[:400]
    return facts


def job_facts(j: Job) -> dict:
    return {
        "title": j.title,
        "status": j.status,
        "location": j.location or "",
        "workplace_type": j.workplace_type or "",
        "min_experience_years": j.min_experience_years,
        "required_skills": (j.required_skills or [])[:12],
        "applicants": j.applicants_count or 0,
    }


def _date(value: Optional[datetime]) -> str:
    return value.strftime("%Y-%m-%d") if value else ""


# ---------------------------------------------------------------------------
# Lookup helpers (scoped)
# ---------------------------------------------------------------------------
def org_jobs(db: Session, ctx: TenantContext):
    return db.query(Job).filter(Job.organization_id == ctx.org_id)


def find_job(db: Session, ctx: TenantContext, book: RefBook, job: Optional[str]) -> Optional[Job]:
    """A job reference ("J1"), id, or title words, within the caller's organization."""
    if not job:
        return None
    job_id = book.resolve(job, "job") or str(job)
    found = org_jobs(db, ctx).filter(Job.id == job_id).first()
    if found:
        return found
    words = [w for w in re.findall(r"[a-z0-9+#]+", str(job).lower()) if len(w) > 1]
    if not words:
        return None
    best, best_hits = None, 0
    for candidate_job in org_jobs(db, ctx).filter(Job.status != "Archived").all():
        title = candidate_job.title.lower()
        hits = sum(1 for w in words if w in title)
        if hits > best_hits:
            best, best_hits = candidate_job, hits
    return best


def find_candidate(db: Session, ctx: TenantContext, book: RefBook, candidate: Optional[str]) -> Optional[CandidateProfile]:
    if not candidate:
        return None
    candidate_id = book.resolve(candidate, "candidate") or str(candidate)
    profile = db.get(CandidateProfile, candidate_id)
    return profile if profile and can_view_candidate(db, ctx, profile) else None


def add_candidate(book: RefBook, c: CandidateProfile, **extra) -> str:
    return book.add(Record("candidate", c.id, {**candidate_facts(c), **extra}))


def add_job(book: RefBook, j: Job, **extra) -> str:
    return book.add(Record("job", j.id, {**job_facts(j), **extra}))


# ---------------------------------------------------------------------------
# Tools: (db, ctx, book, **args) -> short note on what was found
# ---------------------------------------------------------------------------
def search_candidates(db: Session, ctx: TenantContext, book: RefBook, query: str = "", **_) -> str:
    query = re.sub(r"\[[CJS]\d+\]", " ", query or "").strip()
    if not query:
        return "search_candidates: no search terms"
    parsed = search.parse_query(query, get_skill_graph(db))
    results = search.search_candidates(db, ctx, parsed, MAX_RESULTS)
    for rank, hit in enumerate(results, start=1):
        profile = db.get(CandidateProfile, hit["candidate"].id)
        if profile:
            add_candidate(book, profile, search_rank=rank, search_reasons=hit["reasons"])
    return f"search_candidates({query!r}): {len(results)} found"


def top_matches(db: Session, ctx: TenantContext, book: RefBook, job: Optional[str] = None,
                status: str = "active", **_) -> str:
    target = find_job(db, ctx, book, job)
    if target is None:
        return "top_matches: job not found"
    job_ref = add_job(book, target)
    pool = scope_candidates(db.query(CandidateProfile), ctx).all()
    rows = list(matching.ensure_matches(db, target, pool).values())
    db.commit()
    if status == "shortlisted":
        rows = [r for r in rows if r.status == "shortlisted"]
    else:
        rows = [r for r in rows if r.status != "dismissed"]
    rows.sort(key=lambda r: r.score, reverse=True)
    for row in rows[:MAX_RESULTS]:
        add_candidate(book, row.candidate, match={
            "job": job_ref, "score": row.score, "fit": row.fit_level, "decision": row.status,
            "strengths": row.strengths[:3], "gaps": row.gaps[:3],
            "missing_skills": [s["skill"] if isinstance(s, dict) else str(s) for s in row.missing_skills[:5]],
        })
    return f"top_matches({job_ref}): {min(len(rows), MAX_RESULTS)} of {len(rows)} shown"


def list_jobs(db: Session, ctx: TenantContext, book: RefBook, status: Optional[str] = None, **_) -> str:
    query = org_jobs(db, ctx).filter(Job.status != "Archived")
    if status:
        query = query.filter(Job.status == str(status).capitalize())
    jobs = query.order_by(Job.created_at.desc()).limit(15).all()
    for j in jobs:
        add_job(book, j)
    return f"list_jobs: {len(jobs)} found"


def pipeline_summary(db: Session, ctx: TenantContext, book: RefBook, job: Optional[str] = None,
                     days: int = 30, **_) -> str:
    target = find_job(db, ctx, book, job) if job else None
    days = max(7, min(int(days or 30), 365))
    data = recruiter_dashboard(db, ctx.org_id, days=days, job_id=target.id if target else None)
    for key in ("recent_application_ids", "top_match_ids", "applications_by_day"):
        data.pop(key, None)
    facts = {"scope": "job" if target else "organization", **data}
    if target:
        facts["job"] = add_job(book, target)
    book.add(Record("summary", f"pipeline:{target.id if target else ctx.org_id}:{days}", facts))
    return f"pipeline_summary: last {days} days"


def candidate_overview(db: Session, ctx: TenantContext, book: RefBook, candidate: Optional[str] = None, **_) -> str:
    profile = find_candidate(db, ctx, book, candidate)
    if profile is None:
        return "candidate_overview: candidate not found"
    apps = scope_applications(db.query(Application), ctx).filter(Application.candidate_id == profile.id).all()
    applications = []
    for app in apps:
        if app.job is None:
            continue
        applications.append({"job": add_job(book, app.job), "stage": app.stage, "match_score": app.match_score,
                             "applied_on": _date(app.created_at)})
    ref = add_candidate(book, profile, applications=applications)
    return f"candidate_overview({ref}): {len(applications)} applications"


def upcoming_interviews(db: Session, ctx: TenantContext, book: RefBook, days: int = 14, **_) -> str:
    days = max(1, min(int(days or 14), 90))
    now = datetime.utcnow()
    rows = (
        scope_applications(db.query(Interview).join(Application, Interview.application_id == Application.id), ctx)
        .filter(Interview.status == "Scheduled")
        .filter((Interview.scheduled_at.is_(None)) | (Interview.scheduled_at <= now + timedelta(days=days)))
        .order_by(Interview.scheduled_at)
        .limit(20)
        .all()
    )
    entries = []
    for interview in rows:
        app = interview.application
        if app is None or app.candidate is None or app.job is None:
            continue
        entries.append({
            "candidate": add_candidate(book, app.candidate), "job": add_job(book, app.job),
            "round": interview.round_name, "scheduled_for": _date(interview.scheduled_at) or "not set",
        })
    book.add(Record("summary", f"interviews:{ctx.org_id}:{days}", {"interviews": entries, "window_days": days}))
    return f"upcoming_interviews: {len(entries)} in the next {days} days"


TOOLS: Dict[str, Callable[..., str]] = {
    "search_candidates": search_candidates,
    "top_matches": top_matches,
    "list_jobs": list_jobs,
    "pipeline_summary": pipeline_summary,
    "candidate_overview": candidate_overview,
    "upcoming_interviews": upcoming_interviews,
}

TOOL_GUIDE = """Tools (choose 1 to 3; arguments are optional unless stated):
- search_candidates {"query": "skills, title, experience, location in plain words"} (required: query)
- top_matches {"job": "job reference like J1, or job title words", "status": "active" | "shortlisted"}: best-matching candidates for a job
- list_jobs {"status": "Active" | "Draft" | "Paused" | "Closed"}
- pipeline_summary {"job": "J1 (omit for the whole organization)", "days": 30}: funnel, counts, hires, average match score
- candidate_overview {"candidate": "candidate reference like C1"}: profile facts and their applications here
- upcoming_interviews {"days": 14}"""
