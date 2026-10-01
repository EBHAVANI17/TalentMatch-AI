from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user, get_current_user_optional, require_roles
from app.models.db_models import User, Organization
from app.models.schemas import UserOut, UserStatusUpdate
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/users", tags=["User Management"])

@router.get("", response_model=List[UserOut])
def get_all_users(
    db: Session = Depends(get_db),
    organization_id: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None)
):
    query = db.query(User)
    if organization_id:
        query = query.filter(User.organization_id == organization_id)
    if role and role != "all":
        query = query.filter(User.role == role)
    if status_filter and status_filter != "all":
        query = query.filter(User.status == status_filter)
    
    return query.order_by(User.created_at.desc()).all()

@router.get("/{user_id}", response_model=UserOut)
def get_user_by_id(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.patch("/{user_id}/status", response_model=UserOut)
def update_user_status(
    user_id: str,
    payload: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

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
        user_id=current_user.id if current_user else None,
        user_email=current_user.email if current_user else "admin",
        details={"new_status": user.status, "role": user.role}
    )

    return user
