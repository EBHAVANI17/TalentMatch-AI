import json
import uuid
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.db_models import AuditLog

def log_audit_event(
    db: Session,
    action: str,
    module: str,
    entity: str,
    entity_id: str = "",
    user_id: Optional[str] = None,
    user_email: str = "anonymous",
    details: Optional[Dict[str, Any]] = None,
    ip_address: str = "127.0.0.1"
):
    try:
        audit = AuditLog(
            id=f"audit_{uuid.uuid4().hex[:10]}",
            user_id=user_id,
            user_email=user_email,
            action=action,
            module=module,
            entity=entity,
            entity_id=entity_id,
            details_json=json.dumps(details or {}),
            ip_address=ip_address
        )
        db.add(audit)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Audit log failed: {e}")
