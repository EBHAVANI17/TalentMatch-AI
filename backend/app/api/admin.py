import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.tenancy import require_super_admin, TenantContext
from app.models.db_models import AuditLog, SkillTaxonomy, Plan, AIUsageRecord, Organization, User, Job, CandidateProfile
from app.models.schemas import (
    AdminSystemStats, AuditLogOut, SkillTaxonomyOut, PlanOut, AIUsageRecordOut,
    OrganizationUpdate, AdminUserUpdate, EncryptionStatusOut, EncryptionTestRequest, EncryptionTestResponse
)
from app.services.analytics_service import get_admin_system_stats_db
from app.services.audit_service import log_audit_event
from app.core.crypto import get_encryption_status, encrypt_value, decrypt_value
from app.core.security import ROLE_PERMISSIONS
from app.services.account_service import REFRESH, revoke_tokens
from app.services import membership_service
from app.models.db_models import Membership

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

# =========================================================================
# ORGANIZATIONS MANAGEMENT (SUPER ADMIN)
# =========================================================================
@router.get("/organizations", response_model=List[dict])
def get_all_organizations_admin(db: Session = Depends(get_db)):
    orgs = db.query(Organization).order_by(Organization.created_at.desc()).all()
    results = []
    for o in orgs:
        user_count = db.query(Membership).filter(Membership.organization_id == o.id, Membership.status == "active").count()
        job_count = db.query(Job).filter(Job.organization_id == o.id).count()
        results.append({
            "id": o.id,
            "name": o.name,
            "domain": o.domain,
            "industry": o.industry,
            "plan_tier": o.plan_tier,
            "status": o.status or ("Active" if o.is_active else "Suspended"),
            "is_active": o.is_active,
            "max_recruiter_seats": o.max_recruiter_seats,
            "max_active_jobs": o.max_active_jobs,
            "monthly_ai_credits": o.monthly_ai_credits,
            "monthly_ai_credits_used": o.monthly_ai_credits_used,
            "user_count": user_count,
            "job_count": job_count,
            "created_at": o.created_at.strftime("%Y-%m-%d") if o.created_at else "2025-01-01"
        })
    return results

@router.patch("/organizations/{org_id}", response_model=dict)
def update_organization_admin(
    org_id: str,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_super_admin)
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    if payload.domain is not None and payload.domain != org.domain:
        existing = db.query(Organization).filter(Organization.domain == payload.domain, Organization.id != org_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Domain already taken by another organization")
        setattr(org, "domain", payload.domain)

    if payload.name is not None: setattr(org, "name", payload.name)
    if payload.industry is not None: setattr(org, "industry", payload.industry)
    if payload.plan_tier is not None: setattr(org, "plan_tier", payload.plan_tier)
    if payload.max_recruiter_seats is not None: setattr(org, "max_recruiter_seats", payload.max_recruiter_seats)
    if payload.max_active_jobs is not None: setattr(org, "max_active_jobs", payload.max_active_jobs)
    if payload.monthly_ai_credits is not None: setattr(org, "monthly_ai_credits", payload.monthly_ai_credits)
    
    if payload.is_active is not None:
        setattr(org, "is_active", payload.is_active)
        setattr(org, "status", "Active" if payload.is_active else "Suspended")
    elif payload.status is not None:
        setattr(org, "status", payload.status)
        setattr(org, "is_active", payload.status == "Active")

    db.commit()
    db.refresh(org)

    log_audit_event(
        db=db,
        action="SUPERADMIN_ORGANIZATION_UPDATED",
        module="SuperAdmin",
        entity="Organization",
        entity_id=org.id,
        user_id=ctx.user.id,
        user_email=ctx.user.email,
        organization_id=org.id,
        details={"name": org.name, "status": org.status, "plan": org.plan_tier}
    )

    return {
        "id": org.id,
        "name": org.name,
        "domain": org.domain,
        "industry": org.industry,
        "plan_tier": org.plan_tier,
        "status": org.status,
        "is_active": org.is_active,
        "max_recruiter_seats": org.max_recruiter_seats,
        "max_active_jobs": org.max_active_jobs,
        "monthly_ai_credits": org.monthly_ai_credits,
        "message": f"Organization '{org.name}' updated successfully"
    }

@router.post("/organizations/{org_id}/toggle-status", response_model=dict)
def toggle_organization_status_admin(
    org_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_super_admin)
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    new_active = not org.is_active
    setattr(org, "is_active", new_active)
    setattr(org, "status", "Active" if new_active else "Suspended")

    db.commit()
    db.refresh(org)

    log_audit_event(
        db=db,
        action="SUPERADMIN_ORGANIZATION_ACTIVATED" if new_active else "SUPERADMIN_ORGANIZATION_DEACTIVATED",
        module="SuperAdmin",
        entity="Organization",
        entity_id=org.id,
        user_id=ctx.user.id,
        user_email=ctx.user.email,
        organization_id=org.id,
        details={"new_status": org.status, "is_active": org.is_active}
    )

    return {
        "id": org.id,
        "name": org.name,
        "status": org.status,
        "is_active": org.is_active,
        "message": f"Organization '{org.name}' {'activated' if new_active else 'deactivated'} successfully"
    }

# =========================================================================
# USERS MANAGEMENT (SUPER ADMIN)
# =========================================================================
ORGLESS_ROLES = {"SUPER_ADMIN", "CANDIDATE"}

# =========================================================================
# =========================================================================
@router.get("/users", response_model=List[dict])
def get_all_users_admin(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,  # membership-guard: ok (platform admin display)
            "organization_id": u.organization_id,  # membership-guard: ok (platform admin display)
            "organization_name": u.organization.name if u.organization else "None (Candidate / Admin)",
            "status": u.status or "Active",
            "is_active": u.is_active,
            "created_at": u.created_at.strftime("%Y-%m-%d") if u.created_at else "2025-01-01"
        }
        for u in users
    ]

@router.patch("/users/{user_id}", response_model=dict)
def update_user_admin(
    user_id: str,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_super_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.email is not None and payload.email != user.email:
        existing = db.query(User).filter(User.email == payload.email, User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email is already taken by another account")
        setattr(user, "email", payload.email)

    if payload.status is not None and payload.status not in ("Active", "Suspended"):
        raise HTTPException(status_code=400, detail="Status must be 'Active' or 'Suspended'")
    if payload.role is not None and payload.role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=400, detail=f"Unknown role. Valid roles: {', '.join(ROLE_PERMISSIONS)}")
    current_role = user.role  # membership-guard: ok (platform admin edit; default-org role)
    is_self = user.id == ctx.user.id
    if is_self and payload.role is not None and payload.role != current_role:
        raise HTTPException(status_code=400, detail="You cannot change your own role")
    wants_active = payload.is_active if payload.is_active is not None else (
        payload.status == "Active" if payload.status is not None else None)
    if is_self and wants_active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    if payload.full_name is not None:
        setattr(user, "full_name", payload.full_name)

    # Organization staff need an organization; platform admins and candidates have none.
    # Changes go through memberships; the users row only mirrors the default organization.
    if payload.role is not None or payload.organization_id is not None:
        new_role = payload.role or current_role
        clearing = payload.organization_id in ("", "none", "None")
        target_org_id = None if clearing else (payload.organization_id or user.organization_id)  # membership-guard: ok (default org)
        if new_role in ORGLESS_ROLES:
            if target_org_id:
                raise HTTPException(status_code=400, detail=f"{new_role} accounts cannot belong to an organization")
            if new_role != current_role:
                membership_service.assign_platform_role(db, user, new_role, ctx.user)
        else:
            if not target_org_id:
                raise HTTPException(status_code=400, detail=f"{new_role} accounts must belong to an organization")
            org = db.get(Organization, target_org_id)
            if not org:
                raise HTTPException(status_code=400, detail="Target organization does not exist")
            membership_service.set_staff_role(db, user, org, new_role, ctx.user)

    if wants_active is not None:
        setattr(user, "is_active", wants_active)
        setattr(user, "status", "Active" if wants_active else "Suspended")
        if not wants_active:
            revoke_tokens(db, user.id, REFRESH)  # end their sessions

    db.commit()
    db.refresh(user)

    log_audit_event(
        db=db,
        action="SUPERADMIN_USER_UPDATED",
        module="SuperAdmin",
        entity="User",
        entity_id=user.id,
        user_id=ctx.user.id,
        user_email=ctx.user.email,
        organization_id=user.organization_id,  # membership-guard: ok (platform admin display)
        details={"email": user.email, "role": user.role, "status": user.status}  # membership-guard: ok (platform admin display)
    )

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,  # membership-guard: ok (platform admin display)
        "organization_id": user.organization_id,  # membership-guard: ok (platform admin display)
        "status": user.status,
        "is_active": user.is_active,
        "message": f"User '{user.full_name}' updated successfully"
    }

@router.post("/users/{user_id}/toggle-status", response_model=dict)
def toggle_user_status_admin(
    user_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_super_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == ctx.user.id:
        raise HTTPException(status_code=400, detail="Super Admin cannot deactivate their own active account")

    new_active = not user.is_active
    setattr(user, "is_active", new_active)
    setattr(user, "status", "Active" if new_active else "Suspended")
    if not new_active:
        revoke_tokens(db, user.id, REFRESH)  # end their sessions

    db.commit()
    db.refresh(user)

    log_audit_event(
        db=db,
        action="SUPERADMIN_USER_ACTIVATED" if new_active else "SUPERADMIN_USER_DEACTIVATED",
        module="SuperAdmin",
        entity="User",
        entity_id=user.id,
        user_id=ctx.user.id,
        user_email=ctx.user.email,
        organization_id=user.organization_id,  # membership-guard: ok (platform admin display)
        details={"status": user.status, "is_active": user.is_active}
    )

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "status": user.status,
        "is_active": user.is_active,
        "message": f"User '{user.full_name}' {'activated' if new_active else 'deactivated'} successfully"
    }

# =========================================================================
# DATA ENCRYPTION & SECURITY TELEMETRY
# =========================================================================
@router.get("/encryption/status", response_model=EncryptionStatusOut)
def get_encryption_diagnostics():
    return EncryptionStatusOut(**get_encryption_status())

@router.post("/encryption/test", response_model=EncryptionTestResponse)
def test_encryption_engine(payload: EncryptionTestRequest):
    enc = encrypt_value(payload.text) or ""
    dec = decrypt_value(enc) or ""
    return EncryptionTestResponse(
        original=payload.text,
        encrypted=enc,
        decrypted=dec,
        is_valid=(dec == payload.text)
    )

# =========================================================================
# TAXONOMIES
# =========================================================================
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
        setattr(existing, "category", category)
        setattr(existing, "demand_level", demand_level)
        setattr(existing, "avg_salary_boost", avg_salary_boost)
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
