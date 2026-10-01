"""Platform AI administration: prompt versions (with rollback) and the AI request log."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai import prompts
from app.core.database import get_db
from app.core.tenancy import TenantContext, require_super_admin
from app.models.db_models import AIRequest, PromptTemplate
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/admin/ai", tags=["AI Administration"], dependencies=[Depends(require_super_admin)])


class PromptOut(BaseModel):
    key: str
    version: int
    status: str
    system: str
    user_template: str
    notes: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PromptIn(BaseModel):
    system: str = Field(min_length=20, max_length=20000)
    user_template: str = Field(min_length=5, max_length=20000)
    notes: str = Field("", max_length=2000)


class AIRequestOut(BaseModel):
    id: str
    organization_id: Optional[str] = None
    user_id: Optional[str] = None
    feature: str
    status: str
    provider: str
    model: str
    prompt_key: str
    prompt_version: Optional[int] = None
    input_ref: str
    input_tokens: int
    output_tokens: int
    credits: int
    latency_ms: int
    error: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/prompts", response_model=List[PromptOut])
def list_prompts(key: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(PromptTemplate)
    if key:
        q = q.filter(PromptTemplate.key == key)
    return q.order_by(PromptTemplate.key, PromptTemplate.version.desc()).all()


@router.post("/prompts/{key}/versions", response_model=PromptOut, status_code=201)
def create_prompt_version(key: str, payload: PromptIn, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_super_admin)):
    """Create a new draft version. It takes effect only when activated."""
    if key not in prompts.DEFAULT_PROMPTS:
        raise HTTPException(status_code=404, detail="Unknown prompt key")
    placeholders = {"resume_parse": "{resume_text}", "job_generate": "{brief}", "job_analyze": "{job_text}"}[key]
    if placeholders not in payload.user_template:
        raise HTTPException(status_code=422, detail=f"user_template must contain {placeholders}")
    version = prompts.create_version(db, key, payload.system, payload.user_template, payload.notes, ctx.user.id)
    log_audit_event(db=db, action="PROMPT_VERSION_CREATED", module="AI", entity="PromptTemplate", entity_id=version.id,
                    user_id=ctx.user.id, user_email=ctx.user.email, details={"key": key, "version": version.version})
    return version


@router.post("/prompts/{key}/versions/{version}/activate", response_model=PromptOut)
def activate_prompt_version(key: str, version: int, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_super_admin)):
    """Make a version live (also used to roll back to an earlier version)."""
    try:
        active = prompts.activate_version(db, key, version)
    except KeyError:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    log_audit_event(db=db, action="PROMPT_VERSION_ACTIVATED", module="AI", entity="PromptTemplate", entity_id=active.id,
                    user_id=ctx.user.id, user_email=ctx.user.email, details={"key": key, "version": version})
    return active


@router.get("/requests", response_model=List[AIRequestOut])
def list_requests(
    feature: Optional[str] = None,
    status: Optional[str] = None,
    organization_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(AIRequest)
    if feature:
        q = q.filter(AIRequest.feature == feature)
    if status:
        q = q.filter(AIRequest.status == status)
    if organization_id:
        q = q.filter(AIRequest.organization_id == organization_id)
    return q.order_by(AIRequest.created_at.desc()).limit(limit).all()
