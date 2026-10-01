from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.tenancy import get_tenant
from app.models.db_models import SkillTaxonomy
from app.models.schemas import AnalyticsOverview, SkillTaxonomyOut
from app.services.analytics_service import get_analytics_overview_db

# Market-level aggregates (counts, skill demand); no per-tenant records are returned.
router = APIRouter(prefix="/analytics", tags=["Talent Market Radar"], dependencies=[Depends(get_tenant)])

@router.get("/overview", response_model=AnalyticsOverview)
def get_overview(db: Session = Depends(get_db)):
    return get_analytics_overview_db(db)

@router.get("/skills-taxonomy", response_model=List[SkillTaxonomyOut])
def get_taxonomy(db: Session = Depends(get_db)):
    skills = db.query(SkillTaxonomy).all()
    return [
        SkillTaxonomyOut(
            id=s.id,
            name=s.name,
            category=s.category,
            demand_level=s.demand_level,
            avg_salary_boost=s.avg_salary_boost
        )
        for s in skills
    ]
