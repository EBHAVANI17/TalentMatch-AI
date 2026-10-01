"""Domain events (transactional outbox).

    from app.events import emit
    emit(db, "application.created", organization_id=..., actor=user, payload={...})
    db.commit()   # the event is saved atomically with the change

Handlers subscribe with @on("application.created"). Delivery happens after commit:
inline (development/tests) or by the outbox worker (python -m app.workers.outbox).
See app/events/bus.py.
"""
from app.events.bus import dispatch_pending, emit, on

__all__ = ["dispatch_pending", "emit", "on"]
