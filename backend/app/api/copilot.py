"""Recruiter copilot: ask questions about your organization's jobs, candidates and pipeline.

Answers cite the records they use. Conversations are private to the user who started them.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.copilot import service
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.tenancy import TenantContext, not_found, require_permission
from app.models.db_models import CopilotMessage

router = APIRouter(prefix="/copilot", tags=["Copilot"])


def copilot_user(ctx: TenantContext = Depends(require_permission("candidates:search_pool"))) -> TenantContext:
    if not ctx.is_org_member:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The copilot is available to organization members")
    return ctx


class CopilotContext(BaseModel):
    job_id: Optional[str] = Field(None, max_length=64)
    candidate_id: Optional[str] = Field(None, max_length=64)


class AskIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    conversation_id: Optional[str] = Field(None, max_length=64)
    context: CopilotContext = CopilotContext()


class Citation(BaseModel):
    ref: str
    kind: str
    id: str
    label: str
    url: str
    available: bool


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    citations: List[Citation]
    follow_ups: List[str]
    method: str
    notice: str
    created_at: Optional[datetime]


class AskOut(BaseModel):
    conversation_id: str
    message: MessageOut


class ConversationSummary(BaseModel):
    id: str
    title: str
    updated_at: Optional[datetime]


class ConversationOut(ConversationSummary):
    messages: List[MessageOut]


def _message_out(db: Session, ctx: TenantContext, m: CopilotMessage) -> MessageOut:
    return MessageOut(
        id=m.id, role=m.role, content=m.content or "", citations=service.render_citations(db, ctx, m.citations),
        follow_ups=m.follow_ups, method=m.method or "", notice=m.notice or "", created_at=m.created_at,
    )


@router.post("/messages", response_model=AskOut,
             dependencies=[Depends(rate_limit("copilot", lambda: settings.rate_limit_copilot))])
def ask(payload: AskIn, db: Session = Depends(get_db), ctx: TenantContext = Depends(copilot_user)):
    turn = service.ask(db, ctx, message=payload.message, conversation_id=payload.conversation_id,
                       job_id=payload.context.job_id, candidate_id=payload.context.candidate_id)
    if turn is None:
        raise not_found("Conversation")
    return AskOut(conversation_id=turn.conversation.id, message=_message_out(db, ctx, turn.message))


@router.get("/conversations", response_model=List[ConversationSummary])
def conversations(db: Session = Depends(get_db), ctx: TenantContext = Depends(copilot_user)):
    return [ConversationSummary(id=c.id, title=c.title or "Conversation", updated_at=c.updated_at)
            for c in service.list_conversations(db, ctx)]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def conversation(conversation_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(copilot_user)):
    conv = service.get_conversation(db, ctx, conversation_id)
    if conv is None:
        raise not_found("Conversation")
    return ConversationOut(id=conv.id, title=conv.title or "Conversation", updated_at=conv.updated_at,
                           messages=[_message_out(db, ctx, m) for m in conv.messages])


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(copilot_user)):
    conv = service.get_conversation(db, ctx, conversation_id)
    if conv is None:
        raise not_found("Conversation")
    db.delete(conv)
    db.commit()
