from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.tenancy import TenantContext, get_tenant, can_manage_user, not_found, ORG_ROLES, SUPER_ADMIN
from app.models.db_models import Membership, User
from app.models.schemas import UserOut, UserStatusUpdate
from app.services import membership_service
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/users", tags=["User Management"])


def _as_member(user: User, membership: Membership) -> UserOut:
    """A user seen from the caller's organization: that organization's role and membership status."""
    out = UserOut.model_validate(user)
    out.organization_id, out.role = membership.organization_id, membership.role
    active = membership.status == membership_service.ACTIVE and bool(user.is_active)
    out.status, out.is_active = ("Active" if active else "Suspended"), active
    return out


@router.get("", response_model=List[UserOut])
def get_all_users(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant),
    organization_id: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None)
):
    if ctx.is_super_admin:
        query = db.query(User)
        if organization_id:
            query = query.join(Membership, Membership.user_id == User.id).filter(Membership.organization_id == organization_id)
        if role and role != "all":
            query = query.filter(User.role == role)  # membership-guard: ok (platform admin filter)
        if status_filter and status_filter != "all":
            query = query.filter(User.status == status_filter)
        return query.order_by(User.created_at.desc()).all()

    if not ctx.is_org_member:
        raise HTTPException(status_code=403, detail="Access denied")
    if organization_id and organization_id != ctx.org_id:
        return []  # other organizations' people are never listed
    rows = (
        db.query(User, Membership).join(Membership, Membership.user_id == User.id)
        .filter(Membership.organization_id == ctx.org_id)
        .order_by(User.created_at.desc())
        .all()
    )
    members = [_as_member(u, m) for u, m in rows]
    if role and role != "all":
        members = [m for m in members if m.role == role]
    if status_filter and status_filter != "all":
        members = [m for m in members if m.status == status_filter]
    return members


@router.get("/{user_id}", response_model=UserOut)
def get_user_by_id(user_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    user = db.get(User, user_id)
    if user is None:
        raise not_found("User")
    if ctx.is_super_admin or user.id == ctx.user.id:
        return user
    membership = db.query(Membership).filter(Membership.user_id == user.id, Membership.organization_id == ctx.org_id).first()
    if not ctx.is_org_member or membership is None:
        raise not_found("User")
    return _as_member(user, membership)


@router.patch("/{user_id}/status", response_model=UserOut)
def update_user_status(
    user_id: str,
    payload: UserStatusUpdate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant)
):
    """Platform admins change the account. Organization admins change the person's membership in
    their active organization (role and active/suspended); the account itself is untouched."""
    user = db.get(User, user_id)
    membership = None
    if user is not None and not ctx.is_super_admin:
        membership = db.query(Membership).filter(Membership.user_id == user.id, Membership.organization_id == ctx.org_id).first()
    if user is None or (not ctx.is_super_admin and membership is None):
        raise not_found("User")
    if not can_manage_user(ctx, user):
        raise HTTPException(status_code=403, detail="You cannot change this user's status or role")
    if payload.role and not ctx.is_super_admin and payload.role not in ORG_ROLES:
        raise HTTPException(status_code=403, detail="Organization admins can only assign organization roles")
    if payload.role == SUPER_ADMIN and not ctx.is_super_admin:
        raise HTTPException(status_code=403, detail="Only platform administrators can grant SUPER_ADMIN")

    if membership is not None:
        if payload.role:
            membership_service.change_role(db, membership, payload.role, ctx.user)
        membership_service.set_status(db, membership, "active" if payload.status == "Active" else "suspended", ctx.user)
        db.commit()
        db.refresh(membership)
        result = _as_member(user, membership)
    else:
        user.status = payload.status
        user.is_active = (payload.status == "Active")
        if payload.role:
            if payload.role in membership_service.PLATFORM_ROLES:
                membership_service.assign_platform_role(db, user, payload.role, ctx.user)
            else:
                default = membership_service.active_membership(db, user.id, user.organization_id)  # membership-guard: ok (default org)
                if default is None:
                    raise HTTPException(status_code=409, detail="This account has no organization; add a membership first")
                membership_service.change_role(db, default, payload.role, ctx.user)
        db.commit()
        db.refresh(user)
        result = UserOut.model_validate(user)

    log_audit_event(
        db=db, action="USER_STATUS_UPDATED", module="Users", entity="User", entity_id=user.id,
        user_id=ctx.user.id, user_email=ctx.user.email, organization_id=ctx.org_id,
        details={"new_status": payload.status, "role": result.role},
    )
    return result
