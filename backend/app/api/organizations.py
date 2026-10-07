import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.tenancy import TenantContext, get_tenant, require_super_admin, can_view_org, not_found, ORG_ROLES
from app.models.db_models import Membership, Organization, User, Invitation
from app.services import account_service, membership_service
from app.models.schemas import (
    ClientOrganizationCreate, MembershipCreate, MembershipOut, MembershipUpdate, OrganizationOut, OrganizationCreate,
    OrganizationUpdate, UserOut, InvitationCreate, InvitationOut,
)
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/organizations", tags=["Organizations (Tenants)"])

PLATFORM_CONTROLLED_FIELDS = {"plan_tier", "status", "is_active", "domain", "max_recruiter_seats", "max_active_jobs",
                              "monthly_ai_credits", "org_type"}

@router.get("", response_model=List[OrganizationOut])
def get_organizations(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant),
    status_filter: Optional[str] = None
):
    query = db.query(Organization).filter(Organization.status != membership_service.DELETED_STATUS)
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
    rows = db.query(User, Membership).join(Membership, Membership.user_id == User.id).filter(
        Membership.organization_id == org_id).order_by(User.full_name).all()
    return [_member_as_user(user, m) for user, m in rows]


def _member_as_user(user: User, membership: Membership) -> UserOut:
    """A member as seen from one organization: role and status are this organization's."""
    out = UserOut.model_validate(user)
    out.organization_id, out.role = membership.organization_id, membership.role
    out.status = "Active" if membership.status == membership_service.ACTIVE and user.is_active else "Suspended"
    out.is_active = membership.status == membership_service.ACTIVE and bool(user.is_active)
    return out

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

    if payload.domain is not None and payload.domain != org.domain:
        if not ctx.is_super_admin:
            raise HTTPException(status_code=403, detail="Only platform administrators can change domain")
        existing_domain = db.query(Organization).filter(Organization.domain == payload.domain, Organization.id != org.id).first()
        if existing_domain:
            raise HTTPException(status_code=400, detail="Domain is already in use by another organization")
        setattr(org, "domain", payload.domain)
    if payload.org_type is not None:
        membership_service.set_org_type(db, org, payload.org_type)
    if payload.allow_parent_access is not None:
        # The client decides; its parent's admins can't grant themselves access
        if org.org_type != "client":
            raise HTTPException(status_code=422, detail="Only client organizations have parent access settings")
        setattr(org, "allow_parent_access", payload.allow_parent_access)
    if payload.name is not None: setattr(org, "name", payload.name)
    if payload.industry is not None: setattr(org, "industry", payload.industry)
    if payload.plan_tier is not None: setattr(org, "plan_tier", payload.plan_tier)
    if payload.is_active is not None:
        setattr(org, "is_active", payload.is_active)
        setattr(org, "status", "Active" if payload.is_active else "Suspended")
    if payload.status is not None:
        setattr(org, "status", payload.status)
        setattr(org, "is_active", payload.status == "Active")
    if payload.max_recruiter_seats is not None: setattr(org, "max_recruiter_seats", payload.max_recruiter_seats)
    if payload.max_active_jobs is not None: setattr(org, "max_active_jobs", payload.max_active_jobs)
    if payload.monthly_ai_credits is not None: setattr(org, "monthly_ai_credits", payload.monthly_ai_credits)

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


# ---------------------------------------------------------------------------
# Team invitations
# ---------------------------------------------------------------------------
def _org_admin_scope(db: Session, ctx: TenantContext, org_id: str) -> Organization:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org or not can_view_org(ctx, org_id):
        raise not_found("Organization")
    if not (ctx.is_super_admin or ctx.is_org_admin):
        raise HTTPException(status_code=403, detail="Organization admin access required")
    return org


@router.get("/{org_id}/invitations", response_model=List[InvitationOut])
def list_invitations(org_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    _org_admin_scope(db, ctx, org_id)
    return (
        db.query(Invitation)
        .filter(Invitation.organization_id == org_id)
        .order_by(Invitation.created_at.desc())
        .all()
    )


@router.post("/{org_id}/invitations", response_model=InvitationOut, status_code=201)
def invite_member(
    org_id: str,
    payload: InvitationCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant)
):
    org = _org_admin_scope(db, ctx, org_id)
    if payload.role not in ORG_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of: {', '.join(sorted(ORG_ROLES))}")
    invitation = account_service.create_invitation(db, org, payload.email, payload.role, ctx.user)
    log_audit_event(
        db=db, action="MEMBER_INVITED", module="Organizations", entity="Invitation", entity_id=invitation.id,
        user_id=ctx.user.id, user_email=ctx.user.email, organization_id=org.id,
        details={"email": invitation.email, "role": invitation.role},
    )
    return invitation


@router.delete("/{org_id}/invitations/{invitation_id}", response_model=InvitationOut)
def revoke_invitation(
    org_id: str,
    invitation_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant)
):
    _org_admin_scope(db, ctx, org_id)
    invitation = db.query(Invitation).filter(
        Invitation.id == invitation_id, Invitation.organization_id == org_id
    ).first()
    if not invitation:
        raise not_found("Invitation")
    if invitation.status == "pending":
        setattr(invitation, "status", "revoked")
        db.commit()
        db.refresh(invitation)
    return invitation


@router.delete("/{org_id}", response_model=OrganizationOut)
def delete_organization(org_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_super_admin)):
    """Soft delete: the organization stops working; its data and memberships are kept."""
    org = db.get(Organization, org_id)
    if org is None or org.status == membership_service.DELETED_STATUS:
        raise not_found("Organization")
    membership_service.soft_delete_org(db, org)
    db.commit()
    log_audit_event(db=db, action="ORGANIZATION_DELETED", module="Organizations", entity="Organization",
                    entity_id=org.id, user_id=ctx.user.id, user_email=ctx.user.email, organization_id=org.id)
    db.refresh(org)
    return org


# ---------------------------------------------------------------------------
# Client organizations (parent companies managing client companies)
# ---------------------------------------------------------------------------
def _parent_scope(db: Session, ctx: TenantContext, parent_id: str) -> Organization:
    parent = db.get(Organization, parent_id)
    if parent is None or parent.status == membership_service.DELETED_STATUS:
        raise not_found("Organization")
    if ctx.is_super_admin:
        return parent
    if ctx.org_id != parent_id:
        raise not_found("Organization")
    ctx.require("org:manage_clients")
    return parent


@router.get("/{parent_id}/clients", response_model=List[OrganizationOut])
def list_clients(parent_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    _parent_scope(db, ctx, parent_id)
    return (
        db.query(Organization)
        .filter(Organization.parent_id == parent_id, Organization.status != membership_service.DELETED_STATUS)
        .order_by(Organization.name)
        .all()
    )


@router.post("/{parent_id}/clients", response_model=OrganizationOut, status_code=201)
def create_client(parent_id: str, payload: ClientOrganizationCreate, db: Session = Depends(get_db),
                  ctx: TenantContext = Depends(get_tenant)):
    parent = _parent_scope(db, ctx, parent_id)
    if db.query(Organization).filter(Organization.domain == payload.domain).first():
        raise HTTPException(status_code=400, detail="An organization with this domain already exists")
    # Each client has its own plan and seat limit; it starts with the parent's current values.
    org = membership_service.create_client_org(
        db, parent=parent, actor=ctx.user, name=payload.name, domain=payload.domain, industry=payload.industry,
        website=f"https://{payload.domain}", plan_tier=parent.plan_tier, max_recruiter_seats=parent.max_recruiter_seats,
        max_active_jobs=parent.max_active_jobs, monthly_ai_credits=parent.monthly_ai_credits,
    )
    db.commit()
    db.refresh(org)
    return org


# ---------------------------------------------------------------------------
# Memberships
# ---------------------------------------------------------------------------
def _membership_scope(db: Session, ctx: TenantContext, org_id: str) -> tuple:
    """(organization, via_parent). Org admins manage their own organization; parent admins manage a client
    only while it allows parent access. Being able to manage members never grants data access."""
    org = db.get(Organization, org_id)
    if org is None or org.status == membership_service.DELETED_STATUS:
        raise not_found("Organization")
    if ctx.is_super_admin:
        return org, False
    if ctx.is_org_admin and ctx.org_id == org.id:
        return org, False
    if org.parent_id and org.parent_id == ctx.org_id and ctx.has("org:manage_clients"):
        if not org.allow_parent_access:
            raise HTTPException(status_code=403, detail="This client organization doesn't allow its parent to manage members")
        return org, True
    raise not_found("Organization")


def _membership_out(m: Membership) -> MembershipOut:
    return MembershipOut(id=m.id, user_id=m.user_id, email=m.user.email, full_name=m.user.full_name,
                         organization_id=m.organization_id, role=m.role, status=m.status, created_at=m.created_at)


def _get_membership(db: Session, org_id: str, membership_id: str) -> Membership:
    m = db.query(Membership).filter(Membership.id == membership_id, Membership.organization_id == org_id).first()
    if m is None:
        raise not_found("Membership")
    return m


@router.get("/{org_id}/memberships", response_model=List[MembershipOut])
def list_memberships(org_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    _membership_scope(db, ctx, org_id)
    rows = db.query(Membership).filter(Membership.organization_id == org_id).order_by(Membership.created_at).all()
    return [_membership_out(m) for m in rows]


@router.post("/{org_id}/memberships", response_model=MembershipOut, status_code=201)
def add_membership(org_id: str, payload: MembershipCreate, db: Session = Depends(get_db),
                   ctx: TenantContext = Depends(get_tenant)):
    """Add an existing account (people without an account get an invitation instead)."""
    org, via_parent = _membership_scope(db, ctx, org_id)
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None:
        raise HTTPException(status_code=404, detail="No account with that email. Send an invitation instead.")
    m = membership_service.add_member(db, org=org, user=user, role=payload.role, actor=ctx.user, via_parent=via_parent)
    db.commit()
    db.refresh(m)
    return _membership_out(m)


@router.patch("/{org_id}/memberships/{membership_id}", response_model=MembershipOut)
def update_membership(org_id: str, membership_id: str, payload: MembershipUpdate, db: Session = Depends(get_db),
                      ctx: TenantContext = Depends(get_tenant)):
    _, via_parent = _membership_scope(db, ctx, org_id)
    m = _get_membership(db, org_id, membership_id)
    if payload.role is not None:
        membership_service.change_role(db, m, payload.role, ctx.user, via_parent=via_parent)
    if payload.status is not None:
        membership_service.set_status(db, m, payload.status, ctx.user, via_parent=via_parent)
    db.commit()
    db.refresh(m)
    return _membership_out(m)


@router.delete("/{org_id}/memberships/{membership_id}", status_code=204)
def delete_membership(org_id: str, membership_id: str, db: Session = Depends(get_db),
                      ctx: TenantContext = Depends(get_tenant)):
    _, via_parent = _membership_scope(db, ctx, org_id)
    membership_service.remove(db, _get_membership(db, org_id, membership_id), ctx.user, via_parent=via_parent)
    db.commit()
