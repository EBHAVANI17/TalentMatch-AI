"""Notifications: one call, several delivery channels.

    notify(db, user, title=..., message=..., kind="stage_change", link=..., event_id=evt.id)

The in-app channel always runs. Email runs when NOTIFICATION_EMAIL_ENABLED is on.
SMS/WhatsApp providers plug in by implementing NotificationChannel and adding
themselves to CHANNELS.
"""
import logging
import uuid
from dataclasses import dataclass
from typing import Any, List, Optional, Protocol

from sqlalchemy.orm import Session

from app.adapters.email import EmailMessage, get_email_sender
from app.core.config import settings
from app.models.db_models import Notification, User

logger = logging.getLogger(__name__)


@dataclass
class NotificationMessage:
    user: User
    title: str
    message: str
    kind: str = "system"  # application | stage_change | job | interview | system
    link: str = ""
    event_id: Optional[str] = None


class NotificationChannel(Protocol):
    name: str

    def enabled_for(self, msg: NotificationMessage) -> bool: ...

    def send(self, db: Session, msg: NotificationMessage) -> None: ...


class InAppChannel:
    name = "in_app"

    def enabled_for(self, msg: NotificationMessage) -> bool:
        return True

    def send(self, db: Session, msg: NotificationMessage) -> None:
        if msg.event_id and db.query(Notification).filter(
            Notification.event_id == msg.event_id, Notification.user_id == msg.user.id
        ).first():
            return  # already delivered for this event (retry)
        db.add(Notification(
            id=f"notif_{uuid.uuid4().hex[:10]}",
            user_id=msg.user.id,
            title=msg.title[:128],
            message=msg.message,
            type=msg.kind,
            link=msg.link,
            event_id=msg.event_id,
            is_read=False,
        ))


class EmailChannel:
    name = "email"

    def enabled_for(self, msg: NotificationMessage) -> bool:
        user: Any = msg.user
        return bool(settings.notification_email_enabled and user.is_active and msg.kind != "system")

    def send(self, db: Session, msg: NotificationMessage) -> None:
        user: Any = msg.user
        link = f"{settings.app_base_url.rstrip('/')}{msg.link}" if msg.link else settings.app_base_url
        get_email_sender().send(EmailMessage(
            to=str(user.email), subject=msg.title, text=f"{msg.message}\n\n{link}", tags=[f"notification:{msg.kind}"],
        ))


CHANNELS: List[NotificationChannel] = [InAppChannel(), EmailChannel()]


def notify(db: Session, user: Optional[User], *, title: str, message: str, kind: str = "system",
           link: str = "", event_id: Optional[str] = None) -> None:
    """Queue a notification on every enabled channel. The caller commits."""
    if user is None:
        return
    msg = NotificationMessage(user=user, title=title, message=message, kind=kind, link=link, event_id=event_id)
    for channel in CHANNELS:
        if not channel.enabled_for(msg):
            continue
        try:
            channel.send(db, msg)
        except Exception:  # one failing channel must not block the others
            logger.exception("Notification channel %s failed", channel.name)


def create_notification(db: Session, user_id: str, title: str, message: str,
                        notif_type: str = "system", link: str = "") -> Optional[Notification]:
    """Backward-compatible helper: write an in-app notification and commit immediately."""
    try:
        notif = Notification(
            id=f"notif_{uuid.uuid4().hex[:10]}", user_id=user_id, title=title, message=message,
            type=notif_type, link=link, is_read=False,
        )
        db.add(notif)
        db.commit()
        db.refresh(notif)
        return notif
    except Exception:
        db.rollback()
        logger.exception("Failed to create notification")
        return None
