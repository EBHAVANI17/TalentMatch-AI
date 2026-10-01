from dataclasses import dataclass, field
from typing import List, Protocol


@dataclass
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str = ""
    tags: List[str] = field(default_factory=list)  # e.g. ["password_reset"], useful for analytics/tests


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...
