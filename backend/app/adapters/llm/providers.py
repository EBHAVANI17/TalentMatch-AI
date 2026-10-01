"""HTTP clients for free-tier-friendly LLM providers.

Groq and OpenRouter speak the OpenAI chat-completions format; Gemini has its own.
All requests ask for JSON output. Clients are thin: no retries here (the router
handles fallback), and an injectable httpx transport makes them testable offline.
"""
import time
from typing import Optional

import httpx

from app.adapters.llm.base import LLMError, LLMResult


def _raise_for(provider: str, response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    retryable = response.status_code in (408, 409, 425, 429) or response.status_code >= 500
    try:
        detail = response.json()
        detail = detail.get("error", detail)
        detail = detail.get("message", detail) if isinstance(detail, dict) else detail
    except ValueError:
        detail = response.text[:200]
    raise LLMError(provider, f"HTTP {response.status_code}: {detail}", retryable=retryable, status=response.status_code)


class OpenAICompatibleProvider:
    """Groq (https://api.groq.com/openai/v1) and OpenRouter (https://openrouter.ai/api/v1)."""

    def __init__(self, name: str, base_url: str, api_key: str, model: str, timeout: float,
                 extra_headers: Optional[dict] = None, transport: Optional[httpx.BaseTransport] = None):
        self.name = name
        self.model = model
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", **(extra_headers or {})}
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def complete_json(self, system: str, user: str, *, temperature: float, max_tokens: int) -> LLMResult:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        started = time.perf_counter()
        try:
            response = self._client.post(self._url, headers=self._headers, json=body)
        except httpx.HTTPError as exc:
            raise LLMError(self.name, f"network error: {exc.__class__.__name__}") from exc
        _raise_for(self.name, response)
        data = response.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(self.name, "unexpected response shape") from exc
        usage = data.get("usage") or {}
        return LLMResult(
            text=text, provider=self.name, model=data.get("model", self.model),
            input_tokens=int(usage.get("prompt_tokens") or 0), output_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


class GeminiProvider:
    """Google Gemini (generativelanguage.googleapis.com, v1beta generateContent)."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str, timeout: float, transport: Optional[httpx.BaseTransport] = None):
        self.name = "gemini"
        self.model = model
        self._url = f"{self.BASE_URL}/{model}:generateContent"
        self._headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def complete_json(self, system: str, user: str, *, temperature: float, max_tokens: int) -> LLMResult:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens, "responseMimeType": "application/json"},
        }
        started = time.perf_counter()
        try:
            response = self._client.post(self._url, headers=self._headers, json=body)
        except httpx.HTTPError as exc:
            raise LLMError(self.name, f"network error: {exc.__class__.__name__}") from exc
        _raise_for(self.name, response)
        data = response.json()
        try:
            candidate = data["candidates"][0]
            text = "".join(part.get("text", "") for part in candidate["content"]["parts"])
        except (KeyError, IndexError, TypeError) as exc:
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise LLMError(self.name, f"no content returned{f' (blocked: {reason})' if reason else ''}", retryable=not reason) from exc
        usage = data.get("usageMetadata") or {}
        return LLMResult(
            text=text, provider=self.name, model=data.get("modelVersion", self.model),
            input_tokens=int(usage.get("promptTokenCount") or 0), output_tokens=int(usage.get("candidatesTokenCount") or 0),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
