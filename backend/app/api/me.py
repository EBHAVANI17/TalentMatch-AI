"""The signed-in user's own memberships (for the organization switcher)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import security_bearer
from app.core.tenancy import resolve_context
from app.models.db_models import Membership, Organization
from app.services import membership_service

router = APIRouter(prefix="/me", tags=["Authentication & Access"])


class MyOrganization(BaseModel):
    organization_id: str
    name: str
    org_type: str
    parent_id: Optional[str]
    role: str
    status: str
    organization_active: bool
    is_current: bool


@router.get("/organizations", response_model=List[MyOrganization])
def my_organizations(db: Session = Depends(get_db),
                     auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)):
    ctx = resolve_context(db, auth.credentials if auth else None)
    if ctx is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Could not validate credentials or token expired",
                            headers={"WWW-Authenticate": "Bearer"})
    rows = (
        db.query(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .filter(Membership.user_id == ctx.user.id, Organization.status != membership_service.DELETED_STATUS)
        .order_by(Organization.name)
        .all()
    )
    return [
        MyOrganization(
            organization_id=org.id, name=org.name, org_type=org.org_type, parent_id=org.parent_id,
            role=m.role, status=m.status, organization_active=membership_service.is_org_usable(org),
            is_current=org.id == ctx.org_id,
        )
        for m, org in rows
    ]
