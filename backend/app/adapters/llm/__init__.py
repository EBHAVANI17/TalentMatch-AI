"""LLM access with automatic provider fallback.

    router = get_llm_router()
    result = router.complete_json(system, user)   # tries Groq -> Gemini -> OpenRouter (configurable)

Providers without an API key are skipped. A provider that hits a rate limit or an
outage is skipped for LLM_COOLDOWN_SECONDS, then tried again.
"""
import threading
import time
from functools import lru_cache
from typing import Dict, List, Optional

from app.adapters.llm.base import AllProvidersFailed, LLMError, LLMProvider, LLMResult
from app.core.config import settings

__all__ = ["AllProvidersFailed", "LLMError", "LLMProvider", "LLMResult", "LLMRouter", "get_llm_router"]


class LLMRouter:
    def __init__(self, providers: List[LLMProvider], cooldown_seconds: int):
        self.providers = providers
        self.cooldown_seconds = cooldown_seconds
        self._cooling: Dict[str, float] = {}
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return bool(self.providers)

    def _is_cooling(self, name: str) -> bool:
        with self._lock:
            until = self._cooling.get(name, 0)
            return until > time.monotonic()

    def _cool(self, name: str) -> None:
        with self._lock:
            self._cooling[name] = time.monotonic() + self.cooldown_seconds

    def complete_json(self, system: str, user: str, *, temperature: float = 0.2, max_tokens: int = 2000,
                      attempts: Optional[List[str]] = None) -> LLMResult:
        attempts = attempts if attempts is not None else []
        for provider in self.providers:
            if self._is_cooling(provider.name):
                attempts.append(f"{provider.name}: skipped (cooling down)")
                continue
            try:
                return provider.complete_json(system, user, temperature=temperature, max_tokens=max_tokens)
            except LLMError as exc:
                attempts.append(str(exc))
                if exc.retryable:
                    self._cool(provider.name)
        raise AllProvidersFailed(attempts)


def build_providers() -> List[LLMProvider]:
    from app.adapters.llm.providers import GeminiProvider, OpenAICompatibleProvider

    timeout = settings.llm_timeout_seconds
    factories = {
        "groq": lambda: OpenAICompatibleProvider(
            "groq", "https://api.groq.com/openai/v1", settings.groq_api_key, settings.groq_model, timeout)
        if settings.groq_api_key else None,
        "gemini": lambda: GeminiProvider(settings.gemini_api_key, settings.gemini_model, timeout)
        if settings.gemini_api_key else None,
        "openrouter": lambda: OpenAICompatibleProvider(
            "openrouter", "https://openrouter.ai/api/v1", settings.openrouter_api_key, settings.openrouter_model, timeout,
            extra_headers={"HTTP-Referer": settings.app_base_url, "X-Title": settings.app_name})
        if settings.openrouter_api_key else None,
    }
    providers = []
    for name in [n.strip().lower() for n in settings.llm_provider_order.split(",") if n.strip()]:
        factory = factories.get(name)
        provider = factory() if factory else None
        if provider is not None:
            providers.append(provider)
    return providers


@lru_cache
def get_llm_router() -> LLMRouter:
    return LLMRouter(build_providers(), settings.llm_cooldown_seconds)
