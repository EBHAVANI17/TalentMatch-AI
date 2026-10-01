"""The single path every AI feature takes.

    outcome = run_structured(
        db, feature="job_generate", prompt_key="job_generate", variables={"brief": ...},
        schema=JobDraft, fallback=lambda: rules_based_draft(...), user=ctx.user, organization_id=ctx.org_id,
    )
    outcome.data      -> a validated JobDraft (from the model, or from the fallback)
    outcome.method    -> "ai" or "rules"
    outcome.notice    -> what to tell the user about how the draft was produced

Every call is recorded in ai_requests. Limits (per-user daily cap, organization
monthly credits) are enforced before any model is called. Callers must redact
personal data from `variables` first (app/matching/redaction.py).
"""
import json
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Generic, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.adapters.llm import AllProvidersFailed, get_llm_router
from app.ai.prompts import get_active_prompt
from app.core.config import settings
from app.models.db_models import AIRequest, Organization, User

T = TypeVar("T", bound=BaseModel)

RULES_NOTICE = "Created with built-in rules because no AI provider is configured. Review and edit before saving."


@dataclass
class AIOutcome(Generic[T]):
    data: T
    method: str          # ai | rules
    provider: str
    model: str
    request_id: str
    notice: str


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    if not cleaned.startswith("{"):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            cleaned = cleaned[start:end + 1]
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def _limit_reason(db: Session, user: Optional[User], org: Optional[Organization]) -> Optional[str]:
    if org is not None and org.monthly_ai_credits and (org.monthly_ai_credits_used or 0) >= org.monthly_ai_credits:
        return "Your organization has used all of this month's AI credits."
    if user is not None and settings.ai_user_daily_limit:
        start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        used = db.query(AIRequest).filter(
            AIRequest.user_id == user.id, AIRequest.created_at >= start, AIRequest.status == "success"
        ).count()
        if used >= settings.ai_user_daily_limit:
            return "You've reached today's AI limit."
    return None


def run_structured(
    db: Session,
    *,
    feature: str,
    prompt_key: str,
    variables: dict,
    schema: Type[T],
    fallback: Callable[[], T],
    user: Optional[User],
    organization_id: Optional[str],
    input_ref: str = "",
    store_output: bool = True,
    max_tokens: int = 2500,
    temperature: float = 0.2,
) -> AIOutcome[T]:
    org = db.get(Organization, organization_id) if organization_id else None
    prompt = get_active_prompt(db, prompt_key)
    record = AIRequest(
        id=f"air_{uuid.uuid4().hex[:16]}", organization_id=organization_id, user_id=user.id if user else None,
        feature=feature, prompt_key=prompt_key, prompt_version=prompt.version or None, input_ref=input_ref,
        input_chars=sum(len(str(v)) for v in variables.values()),
        input_tokens=0, output_tokens=0, latency_ms=0, credits=0,  # column defaults only apply on insert
    )
    attempts: list = []

    def finish(data: T, status: str, provider: str, model: str, notice: str, error: str = "") -> AIOutcome[T]:
        record.status, record.provider, record.model, record.error = status, provider, model, error[:2000]
        record.attempts = json.dumps(attempts)
        if store_output and settings.ai_log_outputs:
            record.output_json = data.model_dump_json()
        db.add(record)
        db.commit()
        method = "ai" if status == "success" else "rules"
        return AIOutcome(data=data, method=method, provider=provider, model=model, request_id=record.id, notice=notice)

    router = get_llm_router()
    blocked = _limit_reason(db, user, org) if router.available else None
    if blocked:
        return finish(fallback(), "blocked", "rules", "", f"{blocked} This draft was created with built-in rules; review it before saving.")
    if not router.available:
        return finish(fallback(), "fallback", "rules", "", RULES_NOTICE)

    user_message = prompt.user_template.format(**variables)
    last_error = ""
    for attempt in range(2):  # one retry with the validation error fed back
        try:
            result = router.complete_json(prompt.system, user_message, temperature=temperature, max_tokens=max_tokens, attempts=attempts)
        except AllProvidersFailed as exc:
            last_error = str(exc)
            break
        record.input_tokens += result.input_tokens
        record.output_tokens += result.output_tokens
        record.latency_ms += result.latency_ms
        try:
            data = schema.model_validate(_parse_json(result.text))
        except (ValueError, ValidationError) as exc:
            last_error = f"{result.provider} returned output that didn't match the expected format: {str(exc)[:300]}"
            attempts.append(last_error)
            user_message = (
                prompt.user_template.format(**variables)
                + f"\n\nYour previous answer was not valid for the required JSON format ({str(exc)[:200]}). "
                "Return only the JSON object with the exact keys requested."
            )
            continue
        tokens = record.input_tokens + record.output_tokens
        record.credits = max(1, math.ceil(tokens / 1000))
        if org is not None:
            org.monthly_ai_credits_used = (org.monthly_ai_credits_used or 0) + record.credits
        return finish(data, "success", result.provider, result.model,
                      f"Drafted with AI ({result.provider}). Review and edit before saving.")

    return finish(fallback(), "fallback", "rules", "",
                  "The AI service was unavailable, so this draft was created with built-in rules. Review and edit before saving.",
                  error=last_error)
