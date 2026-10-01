import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.tenancy import TenantContext, get_tenant, require_super_admin, can_view_org, not_found
from app.models.db_models import Organization, User
from app.models.schemas import OrganizationOut, OrganizationCreate, OrganizationUpdate, UserOut
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/organizations", tags=["Organizations (Tenants)"])

PLATFORM_CONTROLLED_FIELDS = {"plan_tier", "status", "max_recruiter_seats", "max_active_jobs", "monthly_ai_credits"}

@router.get("", response_model=List[OrganizationOut])
def get_organizations(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant),
    status_filter: Optional[str] = None
):
    query = db.query(Organization)
    if not ctx.is_super_admin:
        query = query.filter(Organization.id == ctx.org_id)
    if status_filter:
        query = query.filter(Organization.status == status_filter)
    return query.order_by(Organization.created_at.desc()).all()

@router.get("/{org_id}", response_model=OrganizationOut)
def get_organization_by_id(org_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org or not can_view_org(ctx, org_id):
        raise not_found("Organization")
    return org

@router.get("/{org_id}/users", response_model=List[UserOut])
def get_organization_users(
    org_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant)
):
    if not can_view_org(ctx, org_id):
        raise not_found("Organization")
    users = db.query(User).filter(User.organization_id == org_id).all()
    return users

@router.post("", response_model=OrganizationOut)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_super_admin)
):
    current_user = ctx.user
    existing = db.query(Organization).filter(Organization.domain == payload.domain).first()
    if existing:
        raise HTTPException(status_code=400, detail="Organization with this domain already exists")

    org_id = f"org_{uuid.uuid4().hex[:8]}"
    org = Organization(
        id=org_id,
        name=payload.name,
        domain=payload.domain,
        industry=payload.industry,
        plan_tier=payload.plan_tier,
        logo_icon=payload.logo_icon,
        website=payload.website or f"https://{payload.domain}",
        status="Active",
        is_active=True,
        max_recruiter_seats=15,
        max_active_jobs=50,
        monthly_ai_credits=10000,
        monthly_ai_credits_used=0
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    log_audit_event(
        db=db,
        action="ORGANIZATION_CREATED",
        module="Organizations",
        entity="Organization",
        entity_id=org.id,
        user_id=current_user.id,
        user_email=current_user.email,
        organization_id=org.id,
        details={"name": org.name, "domain": org.domain, "plan": org.plan_tier}
    )

    return org

@router.patch("/{org_id}", response_model=OrganizationOut)
def update_organization(
    org_id: str,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant)
):
    current_user = ctx.user
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org or not can_view_org(ctx, org_id):
        raise not_found("Organization")
    if not ctx.is_super_admin:
        if not ctx.is_org_admin:
            raise HTTPException(status_code=403, detail="Organization admin access required")
        # Plan, limits and status are platform-controlled (billing / super admin).
        attempted = sorted(f for f in PLATFORM_CONTROLLED_FIELDS if getattr(payload, f, None) is not None)
        if attempted:
            raise HTTPException(
                status_code=403,
                detail="Only platform administrators can change: " + ", ".join(attempted)
            )

    if payload.name is not None: org.name = payload.name
    if payload.industry is not None: org.industry = payload.industry
    if payload.plan_tier is not None: org.plan_tier = payload.plan_tier
    if payload.status is not None:
        org.status = payload.status
        org.is_active = (payload.status == "Active")
    if payload.max_recruiter_seats is not None: org.max_recruiter_seats = payload.max_recruiter_seats
    if payload.max_active_jobs is not None: org.max_active_jobs = payload.max_active_jobs
    if payload.monthly_ai_credits is not None: org.monthly_ai_credits = payload.monthly_ai_credits

    db.commit()
    db.refresh(org)

    log_audit_event(
        db=db,
        action="ORGANIZATION_UPDATED",
        module="Organizations",
        entity="Organization",
        entity_id=org.id,
        user_id=current_user.id,
        user_email=current_user.email,
        organization_id=org.id,
        details={"status": org.status, "plan": org.plan_tier}
    )

    return org
