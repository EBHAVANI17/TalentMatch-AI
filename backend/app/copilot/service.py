"""Recruiter copilot: one question in, one grounded answer out.

    1. Names of candidates the user can see are swapped for references ([C3]);
       emails, phones and links are redacted. Nothing identifying reaches a model.
    2. Plan: a model (or the keyword rules) picks read-only tools.
    3. Look up: tools run inside the user's organization (app/copilot/tools.py).
    4. Answer: a model (or the rules) writes an answer citing only the records found.
       References that don't point at a found record are removed.
    5. Save: messages are stored in reference form; labels are resolved when read,
       through the tenancy rules, so access changes apply to old answers too.
"""
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.ai.orchestrator import run_structured
from app.copilot import rules
from app.copilot.records import RefBook, clean_refs, refs_in
from app.copilot.schemas import CopilotAnswer, CopilotPlan
from app.copilot.tools import TOOL_GUIDE, TOOLS, find_candidate
from app.core.tenancy import TenantContext, can_view_candidate, scope_candidates
from app.matching.redaction import redact
from app.models.db_models import CandidateProfile, CopilotConversation, CopilotMessage, Job, User, utc_now

logger = logging.getLogger(__name__)

MAX_CALLS = 3
HISTORY_MESSAGES = 6
_ARG_KEYS = {"query", "job", "status", "days", "candidate"}


@dataclass
class Turn:
    conversation: CopilotConversation
    message: CopilotMessage


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------
def get_conversation(db: Session, ctx: TenantContext, conversation_id: str) -> Optional[CopilotConversation]:
    conv = db.get(CopilotConversation, conversation_id)
    if conv is None or conv.user_id != ctx.user.id or conv.organization_id != ctx.org_id:
        return None
    return conv


def list_conversations(db: Session, ctx: TenantContext, limit: int = 30) -> List[CopilotConversation]:
    return (
        db.query(CopilotConversation)
        .filter(CopilotConversation.user_id == ctx.user.id, CopilotConversation.organization_id == ctx.org_id)
        .order_by(CopilotConversation.updated_at.desc())
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# Privacy: names -> references, then redaction
# ---------------------------------------------------------------------------
def _mentions(db: Session, ctx: TenantContext, book: RefBook, question: str) -> Tuple[str, List[str]]:
    """Replace names of visible candidates with references; note job titles mentioned."""
    text = question
    mentioned: List[str] = []
    people = (
        scope_candidates(db.query(CandidateProfile.id, User.full_name).join(User, CandidateProfile.user_id == User.id), ctx)
        .limit(5000)
        .all()
    )
    # Full names first (longest first so "Ann Lee" wins over "Ann")
    for cand_id, name in sorted(people, key=lambda p: -len(p[1] or "")):
        name = (name or "").strip()
        if len(name) >= 3 and re.search(rf"\b{re.escape(name)}\b", text, re.I):
            ref = book.ref_for("candidate", cand_id)
            text = re.sub(rf"\b{re.escape(name)}\b", f"[{ref}]", text, flags=re.I)
            mentioned.append(ref)
    # A capitalized first name on its own, when exactly one visible candidate has it
    by_first: Dict[str, List[str]] = {}
    for cand_id, name in people:
        first = (name or "").split()[0] if (name or "").split() else ""
        if len(first) >= 3:
            by_first.setdefault(first.lower(), []).append(cand_id)
    for word in set(re.findall(r"\b[A-Z][a-z]{2,}\b", text)):
        ids = by_first.get(word.lower(), [])
        if len(ids) == 1:
            ref = book.ref_for("candidate", ids[0])
            text = re.sub(rf"\b{word}\b", f"[{ref}]", text)
            mentioned.append(ref)
    # Job titles are not personal data; remember them so "matches for Backend Engineer" works offline
    lowered = text.lower()
    for job_id, title in db.query(Job.id, Job.title).filter(Job.organization_id == ctx.org_id, Job.status != "Archived"):
        if title and title.lower() in lowered:
            mentioned.append(book.ref_for("job", job_id))
    mentioned += [r for r in refs_in(text) if r in book.entries and r not in mentioned]
    return redact(text), mentioned


def _page_context(db: Session, ctx: TenantContext, book: RefBook, job_id: Optional[str],
                  candidate_id: Optional[str]) -> Tuple[str, Optional[str], Optional[str]]:
    parts, job_ref, cand_ref = [], None, None
    if job_id:
        job = db.query(Job).filter(Job.id == job_id, Job.organization_id == ctx.org_id).first()
        if job:
            job_ref = book.ref_for("job", job.id)
            parts.append(f"viewing job [{job_ref}] ({job.title})")
    if candidate_id:
        cand = find_candidate(db, ctx, book, candidate_id)
        if cand:
            cand_ref = book.ref_for("candidate", cand.id)
            parts.append(f"viewing candidate [{cand_ref}]")
    return ("; ".join(parts) or "general"), job_ref, cand_ref


def _history(messages: List[CopilotMessage]) -> str:
    lines = []
    for m in messages[-HISTORY_MESSAGES:]:
        who = "Recruiter" if m.role == "user" else "Copilot"
        lines.append(f"{who}: {(m.content or '')[:500]}")
    return "\n".join(lines) or "(none)"


def _known_refs(db: Session, book: RefBook) -> str:
    out = []
    for ref, entry in book.entries.items():
        if entry["kind"] == "job":
            job = db.get(Job, entry["id"])
            out.append(f"[{ref}] job: {job.title}" if job else f"[{ref}] job")
        else:
            out.append(f"[{ref}] {entry['kind']}")
    return "; ".join(out[-40:]) or "(none)"


def _clean_args(args: dict) -> dict:
    clean = {}
    for key, value in (args or {}).items():
        if key not in _ARG_KEYS or value is None:
            continue
        if key == "days":
            try:
                clean[key] = int(value)
            except (TypeError, ValueError):
                continue
        else:
            clean[key] = str(value)[:200]
    return clean


def _notice(method: str, provider: str, orchestrator_notice: str) -> str:
    if method == "ai":
        return (f"Answered with AI ({provider}) using only your organization's records. "
                "Check the linked records before acting on it.")
    reason = orchestrator_notice.split(" This draft")[0] if " This draft" in orchestrator_notice else ""
    return ((reason + " " if reason else "") +
            "Answered with built-in rules (no AI provider was available), from your organization's records.")


# ---------------------------------------------------------------------------
# One turn
# ---------------------------------------------------------------------------
def ask(db: Session, ctx: TenantContext, *, message: str, conversation_id: Optional[str] = None,
        job_id: Optional[str] = None, candidate_id: Optional[str] = None) -> Optional[Turn]:
    """Returns None when conversation_id doesn't belong to the caller."""
    conv = None
    if conversation_id:
        conv = get_conversation(db, ctx, conversation_id)
        if conv is None:
            return None
    previous: List[CopilotMessage] = list(conv.messages) if conv else []
    seed: Dict[str, dict] = {}
    for m in previous:
        seed.update(m.citations)
    book = RefBook(seed)

    page, context_job, context_candidate = _page_context(db, ctx, book, job_id, candidate_id)
    question, mentioned = _mentions(db, ctx, book, message.strip())
    history = _history(previous)

    # 2. Plan
    plan_outcome = run_structured(
        db, feature="copilot_plan", prompt_key="copilot_plan",
        variables={"tools": TOOL_GUIDE, "page_context": page, "known_refs": _known_refs(db, book),
                   "history": history, "question": question},
        schema=CopilotPlan, fallback=lambda: rules.plan(question, mentioned, context_job, context_candidate),
        user=ctx.user, organization_id=ctx.org_id, input_ref="copilot", max_tokens=400, temperature=0.0,
    )
    calls = [c for c in plan_outcome.data.calls if c.tool in TOOLS][:MAX_CALLS]
    if not calls:
        calls = rules.plan(question, mentioned, context_job, context_candidate).calls

    # 3. Look up
    notes, used = [], []
    for call in calls:
        try:
            notes.append(TOOLS[call.tool](db, ctx, book, **_clean_args(call.args)))
            used.append(call.tool)
        except Exception:  # a failed lookup shouldn't fail the whole answer
            logger.exception("Copilot tool %s failed", call.tool)
            db.rollback()
            notes.append(f"{call.tool}: failed")

    # 4. Answer
    records = "\n".join(json.dumps(r, default=str) for r in book.model_view()) or "(no records found)"
    outcome = run_structured(
        db, feature="copilot_answer", prompt_key="copilot_answer",
        variables={"history": history, "records": records, "lookups": "; ".join(notes) or "none", "question": question},
        schema=CopilotAnswer, fallback=lambda: rules.answer(book, used),
        user=ctx.user, organization_id=ctx.org_id, input_ref="copilot", max_tokens=900, temperature=0.2,
    )
    valid = set(book.entries)
    text = clean_refs(outcome.data.answer, valid).strip()[:4000] or "I couldn't put together an answer from the records."
    cited = [r for r in refs_in(text) + [c.strip("[]").upper() for c in outcome.data.cited_refs] if r in valid]
    follow_ups = [clean_refs(f, valid)[:160] for f in outcome.data.follow_ups if f][:3]

    # 5. Save
    now = utc_now()
    if conv is None:
        conv = CopilotConversation(id=f"conv_{uuid.uuid4().hex[:16]}", organization_id=ctx.org_id,
                                   user_id=ctx.user.id, title=message.strip()[:120])
        db.add(conv)
    db.add(CopilotMessage(
        id=f"cmsg_{uuid.uuid4().hex[:16]}", conversation_id=conv.id, role="user", content=question, created_at=now,
        organization_id=conv.organization_id, user_id=conv.user_id,
        citations_json=json.dumps({r: book.entries[r] for r in refs_in(question) if r in valid}),
    ))
    reply = CopilotMessage(
        id=f"cmsg_{uuid.uuid4().hex[:16]}", conversation_id=conv.id, role="assistant", content=text,
        organization_id=conv.organization_id, user_id=conv.user_id,
        created_at=now + timedelta(microseconds=1),
        citations_json=json.dumps({r: book.entries[r] for r in dict.fromkeys(cited)}),
        follow_ups_json=json.dumps(follow_ups), method=outcome.method,
        notice=_notice(outcome.method, outcome.provider, outcome.notice)[:300], ai_request_id=outcome.request_id,
    )
    db.add(reply)
    conv.updated_at = now
    db.commit()
    db.refresh(conv)
    db.refresh(reply)
    return Turn(conversation=conv, message=reply)


# ---------------------------------------------------------------------------
# Rendering: references -> labels and links, re-checked against current access
# ---------------------------------------------------------------------------
def render_citations(db: Session, ctx: TenantContext, citations: Dict[str, dict]) -> List[dict]:
    out = []
    for ref, entry in citations.items():
        kind, record_id = entry.get("kind"), entry.get("id", "")
        label, url, available = "Unavailable record", "", False
        if kind == "candidate":
            cand = db.get(CandidateProfile, record_id)
            if cand and can_view_candidate(db, ctx, cand):
                label, url, available = (cand.user.full_name if cand.user else "Candidate"), f"/candidates/{cand.id}", True
        elif kind == "job":
            job = db.get(Job, record_id)
            if job and job.organization_id == ctx.org_id:
                label, url, available = job.title, f"/jobs/{job.id}", True
        elif kind == "summary":
            label = "Upcoming interviews" if record_id.startswith("interviews:") else "Pipeline summary"
            available = True
        out.append({"ref": ref, "kind": kind, "id": record_id if available else "", "label": label,
                    "url": url, "available": available})
    return out
