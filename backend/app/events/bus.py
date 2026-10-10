import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional

from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import WorkerSessionLocal, set_tenant
from app.models.db_models import EventDeadLetter, OutboxEvent

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5

Handler = Callable[[Session, OutboxEvent], None]
_handlers: Dict[str, List[Handler]] = defaultdict(list)


def on(event_type: str) -> Callable[[Handler], Handler]:
    """Register a handler. Handlers must be idempotent: an event may be delivered more than once."""
    def register(fn: Handler) -> Handler:
        _handlers[event_type].append(fn)
        return fn
    return register


def emit(
    db: Session,
    event_type: str,
    *,
    organization_id: Optional[str] = None,
    actor=None,
    payload: Optional[Dict[str, Any]] = None,
) -> OutboxEvent:
    """Record an event in the caller's transaction. Nothing is delivered until it commits."""
    record = OutboxEvent(
        id=f"evt_{uuid.uuid4().hex[:16]}",
        type=event_type,
        organization_id=organization_id,
        actor_user_id=getattr(actor, "id", None),
        payload_json=json.dumps(payload or {}, default=str),
    )
    db.add(record)
    db.info.setdefault("pending_event_ids", []).append(record.id)
    return record


def _org_mismatch(record: OutboxEvent) -> Optional[str]:
    """The row's organization_id is authoritative; a payload naming another organization is refused."""
    payload_org = record.payload.get("organization_id")
    if payload_org and payload_org != record.organization_id:
        return f"payload organization_id {payload_org!r} does not match the event's {record.organization_id!r}"
    return None


def _dead_letter(db: Session, record: OutboxEvent, reason: str) -> None:
    db.add(EventDeadLetter(id=f"dlq_{uuid.uuid4().hex[:16]}", event_id=record.id, type=record.type,
                           organization_id=record.organization_id, payload_json=record.payload_json, reason=reason))
    record.attempts = MAX_ATTEMPTS
    record.last_error = f"dead-lettered: {reason}"[:2000]
    logger.error("Event %s (%s) dead-lettered: %s", record.id, record.type, reason)


def _deliver(db: Session, event_id: str) -> None:
    """One event, one transaction, scoped (row-level security) to the event's own organization and actor."""
    set_tenant(db, org_id=None, user_id=None)
    record = db.get(OutboxEvent, event_id)  # worker role: may read any organization's events
    if record is None or record.dispatched_at is not None:
        db.rollback()
        return
    reason = _org_mismatch(record)
    if reason:
        _dead_letter(db, record, reason)
        db.commit()
        return
    org_id, actor_id = record.organization_id, record.actor_user_id
    set_tenant(db, org_id=org_id, user_id=actor_id)
    try:
        for handler in _handlers.get(record.type, []):
            handler(db, record)
        record.dispatched_at = datetime.utcnow()
        record.last_error = ""
    except Exception as exc:  # keep going; the event is retried later
        db.rollback()
        set_tenant(db, org_id=org_id, user_id=actor_id)
        record = db.get(OutboxEvent, event_id)
        logger.exception("Event %s (%s) failed", record.id, record.type)
        record.last_error = f"{type(exc).__name__}: {exc}"[:2000]
    record.attempts += 1
    db.commit()


def dispatch_ids(event_ids: Iterable[str]) -> None:
    with WorkerSessionLocal() as db:
        for event_id in event_ids:
            _deliver(db, event_id)


def dispatch_pending(limit: int = 100) -> int:
    """Deliver undelivered events (oldest first). Returns how many were attempted."""
    with WorkerSessionLocal() as db:
        ids = [
            event_id for (event_id,) in db.query(OutboxEvent.id)
            .filter(OutboxEvent.dispatched_at.is_(None), OutboxEvent.attempts < MAX_ATTEMPTS)
            .order_by(OutboxEvent.created_at)
            .limit(limit)
        ]
        db.rollback()
        for event_id in ids:
            _deliver(db, event_id)
        return len(ids)


# Inline delivery: right after the emitting transaction commits.
@sa_event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    ids = session.info.pop("pending_event_ids", None)
    if ids and settings.event_dispatch_mode == "inline":
        dispatch_ids(ids)


@sa_event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop("pending_event_ids", None)


def _load_handlers() -> None:
    # Import modules that register handlers with @on(...)
    import app.events.handlers  # noqa: F401


_load_handlers()
