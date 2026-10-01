"""Remove personal identifiers from text before it reaches a model (embeddings now, LLMs later).

Matching and AI features should judge the work, not the person: names, emails,
phone numbers and personal links are replaced with neutral placeholders.
"""
import re
from typing import Iterable

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_PROFILE = re.compile(r"\b(?:linkedin\.com|github\.com)/\S+", re.IGNORECASE)
# 7+ digits with optional separators / country code, e.g. +91 98765 43210, (415) 555-0100
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{6,}\d(?!\w)")


def redact(text: str, names: Iterable[str] = ()) -> str:
    if not text:
        return ""
    out = _EMAIL.sub("[email]", text)
    out = _URL.sub("[link]", out)
    out = _PROFILE.sub("[link]", out)
    out = _PHONE.sub(lambda m: "[phone]" if sum(c.isdigit() for c in m.group()) >= 7 else m.group(), out)
    for name in names:
        name = (name or "").strip()
        if not name:
            continue
        out = re.sub(re.escape(name), "[name]", out, flags=re.IGNORECASE)
        for part in name.split():
            if len(part) >= 3:  # also first/last names on their own
                out = re.sub(rf"\b{re.escape(part)}\b", "[name]", out, flags=re.IGNORECASE)
    return out
