from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.tenancy import TenantContext, get_tenant, can_manage_user, not_found, ORG_ROLES, SUPER_ADMIN
from app.models.db_models import User, Organization
from app.models.schemas import UserOut, UserStatusUpdate
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/users", tags=["User Management"])

@router.get("", response_model=List[UserOut])
def get_all_users(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant),
    organization_id: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None)
):
    query = db.query(User)
    if not ctx.is_super_admin:
        if not ctx.is_org_member:
            raise HTTPException(status_code=403, detail="Access denied")
        query = query.filter(User.organization_id == ctx.org_id)
    if organization_id:
        query = query.filter(User.organization_id == organization_id)
    if role and role != "all":
        query = query.filter(User.role == role)
    if status_filter and status_filter != "all":
        query = query.filter(User.status == status_filter)
    
    return query.order_by(User.created_at.desc()).all()

@router.get("/{user_id}", response_model=UserOut)
def get_user_by_id(user_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    user = db.query(User).filter(User.id == user_id).first()
    visible = user is not None and (
        ctx.is_super_admin
        or user.id == ctx.user.id
        or (ctx.is_org_member and user.organization_id == ctx.org_id)
    )
    if not visible:
        raise not_found("User")
    return user

@router.patch("/{user_id}/status", response_model=UserOut)
def update_user_status(
    user_id: str,
    payload: UserStatusUpdate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant)
):
    current_user = ctx.user
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not (ctx.is_super_admin or user.organization_id == ctx.org_id):
        raise not_found("User")
    if not can_manage_user(ctx, user):
        raise HTTPException(status_code=403, detail="You cannot change this user's status or role")
    if payload.role and not ctx.is_super_admin and payload.role not in ORG_ROLES:
        raise HTTPException(status_code=403, detail="Organization admins can only assign organization roles")
    if payload.role == SUPER_ADMIN and not ctx.is_super_admin:
        raise HTTPException(status_code=403, detail="Only platform administrators can grant SUPER_ADMIN")

    user.status = payload.status
    user.is_active = (payload.status == "Active")
    if payload.role:
        user.role = payload.role

    db.commit()
    db.refresh(user)

    log_audit_event(
        db=db,
        action="USER_STATUS_UPDATED",
        module="Users",
        entity="User",
        entity_id=user.id,
        user_id=current_user.id,
        user_email=current_user.email,
        organization_id=user.organization_id,
        details={"new_status": user.status, "role": user.role}
    )

    return user
