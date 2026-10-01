import uuid
from sqlalchemy.orm import Session
from app.models.db_models import Notification

def create_notification(
    db: Session,
    user_id: str,
    title: str,
    message: str,
    notif_type: str = "system",
    link: str = ""
) -> Notification:
    try:
        notif = Notification(
            id=f"notif_{uuid.uuid4().hex[:10]}",
            user_id=user_id,
            title=title,
            message=message,
            type=notif_type,
            link=link,
            is_read=False
        )
        db.add(notif)
        db.commit()
        db.refresh(notif)
        return notif
    except Exception as e:
        db.rollback()
        print(f"Failed to create notification: {e}")
        return None
