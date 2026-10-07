"""Records the copilot can show to a model, and the short references ([C1], [J2]) that stand in for them.

A model only ever sees references and non-identifying facts. Names, emails, phone
numbers and links stay on the server; the UI turns references back into links.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

REF_PATTERN = re.compile(r"\[([CJS]\d{1,3})\]")
_PREFIX = {"candidate": "C", "job": "J", "summary": "S"}


@dataclass
class Record:
    kind: str                 # candidate | job | summary
    id: str
    facts: dict = field(default_factory=dict)
    ref: str = ""


class RefBook:
    """Assigns stable references within one conversation.

    Seeded with the references used in earlier turns, so "[C2]" keeps meaning the
    same candidate in follow-up questions.
    """

    def __init__(self, seed: Optional[Dict[str, dict]] = None):
        self.entries: Dict[str, dict] = {}          # ref -> {"kind", "id"}
        self._by_key: Dict[Tuple[str, str], str] = {}
        self._counters: Dict[str, int] = {}
        self.records: Dict[str, Record] = {}        # records retrieved in this turn
        for ref, entry in (seed or {}).items():
            self._register(ref, entry["kind"], entry["id"])

    def _register(self, ref: str, kind: str, record_id: str) -> None:
        self.entries[ref] = {"kind": kind, "id": record_id}
        self._by_key[(kind, record_id)] = ref
        prefix, number = ref[0], int(ref[1:])
        self._counters[prefix] = max(self._counters.get(prefix, 0), number)

    def ref_for(self, kind: str, record_id: str) -> str:
        key = (kind, record_id)
        if key not in self._by_key:
            prefix = _PREFIX[kind]
            self._register(f"{prefix}{self._counters.get(prefix, 0) + 1}", kind, record_id)
        return self._by_key[key]

    def add(self, record: Record) -> str:
        record.ref = self.ref_for(record.kind, record.id)
        existing = self.records.get(record.ref)
        if existing:
            existing.facts.update(record.facts)
        else:
            self.records[record.ref] = record
        return record.ref

    def resolve(self, ref: Optional[str], kind: str) -> Optional[str]:
        """"C2" or "[C2]" -> record id, if it refers to a record of that kind."""
        if not ref:
            return None
        entry = self.entries.get(str(ref).strip().strip("[]").upper())
        return entry["id"] if entry and entry["kind"] == kind else None

    def model_view(self) -> List[dict]:
        return [{"ref": r.ref, "kind": r.kind, **r.facts} for r in self.records.values()]


def clean_refs(text: str, valid: set) -> str:
    """Remove reference tokens that don't point at a known record (a model may invent them)."""
    return REF_PATTERN.sub(lambda m: m.group(0) if m.group(1) in valid else "", text)


def refs_in(text: str) -> List[str]:
    seen: List[str] = []
    for ref in REF_PATTERN.findall(text or ""):
        if ref not in seen:
            seen.append(ref)
    return seen
