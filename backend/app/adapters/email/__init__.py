from functools import lru_cache

from app.adapters.email.base import EmailMessage, EmailSender
from app.core.config import settings

__all__ = ["EmailMessage", "EmailSender", "get_email_sender"]


@lru_cache
def get_email_sender() -> EmailSender:
    backend = settings.email_backend.lower()
    if backend == "console":
        from app.adapters.email.console import ConsoleEmailSender
        return ConsoleEmailSender()
    raise ValueError(f"Unknown EMAIL_BACKEND {settings.email_backend!r} (supported: console)")
