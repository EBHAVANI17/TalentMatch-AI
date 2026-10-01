import logging
from typing import List

from app.adapters.email.base import EmailMessage

logger = logging.getLogger(__name__)


class ConsoleEmailSender:
    """Development/test sender: logs the email and keeps it in `outbox` instead of delivering it."""

    def __init__(self) -> None:
        self.outbox: List[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.outbox.append(message)
        logger.info("EMAIL to=%s subject=%r\n%s", message.to, message.subject, message.text)
