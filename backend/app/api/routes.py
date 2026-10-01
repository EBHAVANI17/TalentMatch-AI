from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.organizations import router as organizations_router
from app.api.jobs import router as jobs_router
from app.api.candidates import router as candidates_router
from app.api.resumes import router as resumes_router
from app.api.applications import router as applications_router
from app.api.recommendations import router as recommendations_router
from app.api.ai_tools import router as ai_tools_router
from app.api.analytics import router as analytics_router
from app.api.notifications import router as notifications_router
from app.api.admin import router as admin_router
from app.api.system import router as system_router
from app.core.tenancy import TenantContext, get_tenant
from app.api.recommendations import jobs_for_candidate

router = APIRouter()

# Include all modular REST routers
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(organizations_router)
router.include_router(jobs_router)
router.include_router(candidates_router)
router.include_router(resumes_router)
router.include_router(applications_router)
router.include_router(recommendations_router)
router.include_router(ai_tools_router)
router.include_router(analytics_router)
router.include_router(notifications_router)
router.include_router(admin_router)
router.include_router(system_router)

# Legacy Backward-Compatibility Endpoint
@router.get("/ai/recommend-jobs/{userId}", tags=["Legacy"])
def get_recommendations_legacy(userId: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    matches = jobs_for_candidate(db, ctx, userId)
    return [
        {
            "jobId": m.job.id,
            "title": m.job.title,
            "score": round(m.match_score / 100.0, 3),
            "missing_skills": m.explanation.missing_critical_skills
        }
        for m in matches
    ]