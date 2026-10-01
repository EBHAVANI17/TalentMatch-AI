"""Hiring pipeline: stage configuration and moving applications between stages."""
import uuid
from dataclasses import dataclass
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.events import emit
from app.models.db_models import Application, ApplicationStageHistory, PipelineStage, User


@dataclass(frozen=True)
class Stage:
    name: str
    kind: str  # active | hired | rejected


DEFAULT_PIPELINE: List[Stage] = [
    Stage("Applied", "active"),
    Stage("Screening", "active"),
    Stage("Shortlisted", "active"),
    Stage("Interview", "active"),
    Stage("Selected", "active"),
    Stage("Hired", "hired"),
    Stage("Rejected", "rejected"),
]

# Names used by older clients and data, mapped to the default stage that replaced them.
STAGE_ALIASES = {
    "ai screened": "Screening",
    "screened": "Screening",
    "interviewing": "Interview",
    "assessment": "Interview",
    "offered": "Selected",
    "offer": "Selected",
}

STAGE_KINDS = {"active", "hired", "rejected"}


def get_stages(db: Session, org_id: Optional[str]) -> List[Stage]:
    if org_id:
        rows = db.query(PipelineStage).filter(PipelineStage.organization_id == org_id).order_by(PipelineStage.position).all()
        if rows:
            return [Stage(r.name, r.kind) for r in rows]
    return list(DEFAULT_PIPELINE)


def resolve_stage(db: Session, org_id: Optional[str], requested: str) -> Stage:
    stages = get_stages(db, org_id)
    by_name = {s.name.lower(): s for s in stages}
    key = (requested or "").strip().lower()
    stage = by_name.get(key) or by_name.get(STAGE_ALIASES.get(key, "").lower())
    if stage is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Unknown stage '{requested}'. Valid stages: {', '.join(s.name for s in stages)}",
        )
    return stage


def move_application(db: Session, app: Application, requested_stage: str, actor: User, reason: str = "") -> bool:
    """Move an application to a stage, recording history and an event. Returns False if nothing changed."""
    stage = resolve_stage(db, app.organization_id, requested_stage)
    if stage.name == app.stage:
        return False
    old_stage = app.stage
    app.stage = stage.name
    db.add(ApplicationStageHistory(
        id=f"hist_{uuid.uuid4().hex[:10]}",
        application_id=app.id,
        from_stage=old_stage,
        to_stage=stage.name,
        changed_by_user_id=actor.id,
        reason=(reason or "")[:256],
    ))
    emit(db, "application.stage_changed", organization_id=app.organization_id, actor=actor, payload={
        "application_id": app.id, "job_id": app.job_id, "candidate_id": app.candidate_id,
        "from_stage": old_stage, "to_stage": stage.name, "stage_kind": stage.kind,
    })
    return True


def save_org_pipeline(db: Session, org_id: str, stages: List[Stage]) -> List[Stage]:
    """Replace an organization's pipeline. Stages that still hold applications can't be removed."""
    names = [s.name.strip() for s in stages]
    if any(not n or len(n) > 48 for n in names):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Stage names must be 1-48 characters")
    if len({n.lower() for n in names}) != len(names):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Stage names must be unique")
    kinds = [s.kind for s in stages]
    if any(k not in STAGE_KINDS for k in kinds):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Stage kind must be active, hired or rejected")
    if kinds.count("hired") != 1 or kinds.count("rejected") != 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A pipeline needs exactly one hired stage and one rejected stage")

    keep = {n.lower() for n in names}
    in_use = {
        stage for (stage,) in db.query(Application.stage).filter(Application.organization_id == org_id).distinct()
        if stage and stage.lower() not in keep
    }
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Move applications out of these stages first: {', '.join(sorted(in_use))}",
        )

    db.query(PipelineStage).filter(PipelineStage.organization_id == org_id).delete(synchronize_session=False)
    for position, stage in enumerate(stages):
        db.add(PipelineStage(
            id=f"stg_{uuid.uuid4().hex[:10]}", organization_id=org_id,
            name=stage.name.strip(), kind=stage.kind, position=position,
        ))
    db.commit()
    return get_stages(db, org_id)
