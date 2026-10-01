import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.tenancy import require_super_admin
from app.models.db_models import AuditLog, SkillTaxonomy, Plan, AIUsageRecord
from app.models.schemas import (
    AdminSystemStats, AuditLogOut, SkillTaxonomyOut, PlanOut, AIUsageRecordOut
)
from app.services.analytics_service import get_admin_system_stats_db

router = APIRouter(
    prefix="/admin",
    tags=["Super Admin & System Observability"],
    dependencies=[Depends(require_super_admin)],
)

@router.get("/stats", response_model=AdminSystemStats)
def get_system_stats(db: Session = Depends(get_db)):
    return get_admin_system_stats_db(db)

@router.get("/audit-logs", response_model=List[AuditLogOut])
def get_audit_logs(
    db: Session = Depends(get_db),
    module: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500)
):
    query = db.query(AuditLog)
    if module and module != "all":
        query = query.filter(AuditLog.module == module)
    if action and action != "all":
        query = query.filter(AuditLog.action == action)
    
    logs = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [
        AuditLogOut(
            id=l.id,
            organization_id=l.organization_id,
            user_email=l.user_email,
            action=l.action,
            module=l.module,
            entity=l.entity,
            entity_id=l.entity_id or "",
            details=l.details,
            ip_address=l.ip_address,
            status=l.status or "SUCCESS",
            created_at=l.created_at
        )
        for l in logs
    ]

@router.get("/ai-usage", response_model=List[AIUsageRecordOut])
def get_ai_usage_telemetry(db: Session = Depends(get_db)):
    records = db.query(AIUsageRecord).order_by(AIUsageRecord.created_at.desc()).limit(50).all()
    return records

@router.get("/plans", response_model=List[PlanOut])
def get_plans(db: Session = Depends(get_db)):
    return db.query(Plan).all()

@router.get("/users", response_model=List[dict])
def get_all_users_admin(db: Session = Depends(get_db)):
    from app.models.db_models import User
    users = db.query(User).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "organization_id": u.organization_id,
            "organization_name": u.organization.name if u.organization else "None (Candidate / Admin)",
            "status": u.status or "Active",
            "is_active": u.is_active,
            "created_at": u.created_at.strftime("%Y-%m-%d") if u.created_at else "2025-01-01"
        }
        for u in users
    ]

@router.post("/taxonomies", response_model=SkillTaxonomyOut)
def add_taxonomy_skill(
    name: str,
    category: str,
    demand_level: str = "High",
    avg_salary_boost: str = "+15%",
    db: Session = Depends(get_db)
):
    existing = db.query(SkillTaxonomy).filter(SkillTaxonomy.name == name).first()
    if existing:
        existing.category = category
        existing.demand_level = demand_level
        existing.avg_salary_boost = avg_salary_boost
        db.commit()
        db.refresh(existing)
        item = existing
    else:
        item = SkillTaxonomy(
            id=f"tax_{uuid.uuid4().hex[:8]}",
            name=name,
            category=category,
            demand_level=demand_level,
            avg_salary_boost=avg_salary_boost
        )
        db.add(item)
        db.commit()
        db.refresh(item)
    return SkillTaxonomyOut(
        id=item.id,
        name=item.name,
        category=item.category,
        demand_level=item.demand_level,
        avg_salary_boost=item.avg_salary_boost
    )


