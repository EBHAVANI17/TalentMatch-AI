"""Dashboard figures for hiring teams, always scoped to one organization (or the whole platform for super admins)."""
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.db_models import Application, Interview, Job
from app.services.pipeline_service import get_stages


def recruiter_dashboard(db: Session, org_id: Optional[str], *, days: int = 30, job_id: Optional[str] = None) -> Dict:
    since = datetime.utcnow() - timedelta(days=days)

    jobs_q = db.query(Job)
    apps_q = db.query(Application)
    if org_id:
        jobs_q = jobs_q.filter(Job.organization_id == org_id)
        apps_q = apps_q.filter(Application.organization_id == org_id)
    if job_id:
        jobs_q = jobs_q.filter(Job.id == job_id)
        apps_q = apps_q.filter(Application.job_id == job_id)

    job_status = dict(jobs_q.with_entities(Job.status, func.count(Job.id)).group_by(Job.status).all())
    stage_counts = dict(apps_q.with_entities(Application.stage, func.count(Application.id)).group_by(Application.stage).all())
    stages = get_stages(db, org_id)
    hired_stage = next((s.name for s in stages if s.kind == "hired"), "Hired")
    rejected_stage = next((s.name for s in stages if s.kind == "rejected"), "Rejected")

    open_apps = apps_q.filter(Application.stage.notin_([hired_stage, rejected_stage]))
    avg_score = apps_q.with_entities(func.avg(Application.match_score)).scalar()

    interviews_q = db.query(Interview).join(Application, Interview.application_id == Application.id)
    if org_id:
        interviews_q = interviews_q.filter(Application.organization_id == org_id)
    if job_id:
        interviews_q = interviews_q.filter(Application.job_id == job_id)
    upcoming_interviews = interviews_q.filter(Interview.status == "Scheduled").count()

    # Applications per day for the period (dates with no applications are filled with 0)
    rows = (
        apps_q.filter(Application.created_at >= since)
        .with_entities(func.date(Application.created_at), func.count(Application.id))
        .group_by(func.date(Application.created_at))
        .all()
    )
    per_day = {str(day): count for day, count in rows}
    timeline: List[Dict] = []
    for offset in range(days, -1, -1):
        day = (datetime.utcnow() - timedelta(days=offset)).date().isoformat()
        timeline.append({"date": day, "count": per_day.get(day, 0)})

    return {
        "period_days": days,
        "jobs": {
            "total": sum(job_status.values()),
            "active": job_status.get("Active", 0),
            "draft": job_status.get("Draft", 0),
            "paused": job_status.get("Paused", 0),
            "closed": job_status.get("Closed", 0),
        },
        "candidates": {
            "in_pipeline": open_apps.with_entities(func.count(func.distinct(Application.candidate_id))).scalar() or 0,
            "new_in_period": apps_q.filter(Application.created_at >= since)
                .with_entities(func.count(func.distinct(Application.candidate_id))).scalar() or 0,
        },
        "applications_total": sum(stage_counts.values()),
        "shortlisted": stage_counts.get("Shortlisted", 0),
        "interviewing": stage_counts.get("Interview", 0),
        "upcoming_interviews": upcoming_interviews,
        "hires": stage_counts.get(hired_stage, 0),
        "average_match_score": round(float(avg_score), 1) if avg_score is not None else None,
        "funnel": [{"stage": s.name, "kind": s.kind, "count": stage_counts.get(s.name, 0)} for s in stages],
        "applications_by_day": timeline,
        "recent_application_ids": [a.id for a in apps_q.order_by(Application.created_at.desc()).limit(8)],
        "top_match_ids": [a.id for a in open_apps.order_by(Application.match_score.desc(), Application.created_at.desc()).limit(5)],
    }
