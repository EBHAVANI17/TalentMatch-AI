from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenancy import TenantContext, get_tenant
from app.services.audit_service import log_audit_event
from app.services.pipeline_service import Stage, get_stages, save_org_pipeline

router = APIRouter(prefix="/pipeline", tags=["Hiring Pipeline"])


class StageOut(BaseModel):
    name: str
    kind: str


class PipelineUpdate(BaseModel):
    stages: List[StageOut] = Field(min_length=3, max_length=20)


def _target_org(ctx: TenantContext, organization_id: Optional[str]) -> str:
    if ctx.is_super_admin and organization_id:
        return organization_id
    if not ctx.is_org_member:
        raise HTTPException(status_code=403, detail="Pipelines belong to organizations")
    return ctx.org_id


@router.get("/stages", response_model=List[StageOut])
def list_stages(
    organization_id: Optional[str] = Query(None, description="Super admins only"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant),
):
    """The organization's pipeline stages in order (the default pipeline unless customized)."""
    if ctx.is_candidate:
        return [StageOut(name=s.name, kind=s.kind) for s in get_stages(db, None)]
    return [StageOut(name=s.name, kind=s.kind) for s in get_stages(db, _target_org(ctx, organization_id))]


@router.put("/stages", response_model=List[StageOut])
def update_stages(
    payload: PipelineUpdate,
    organization_id: Optional[str] = Query(None, description="Super admins only"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant),
):
    if not (ctx.is_super_admin or ctx.is_org_admin):
        raise HTTPException(status_code=403, detail="Organization admin access required")
    org_id = _target_org(ctx, organization_id)
    stages = save_org_pipeline(db, org_id, [Stage(s.name, s.kind) for s in payload.stages])
    log_audit_event(
        db=db, action="PIPELINE_UPDATED", module="Pipeline", entity="Organization", entity_id=org_id,
        user_id=ctx.user.id, user_email=ctx.user.email, organization_id=org_id,
        details={"stages": [s.name for s in stages]},
    )
    return [StageOut(name=s.name, kind=s.kind) for s in stages]
