"""LLM provider clients and router, tested offline with mocked HTTP."""
import json

import httpx
import pytest

from app.adapters.llm import AllProvidersFailed, LLMError, LLMResult, LLMRouter, build_providers
from app.adapters.llm.providers import GeminiProvider, OpenAICompatibleProvider


def transport(handler):
    seen = []

    def wrapped(request: httpx.Request):
        seen.append(request)
        return handler(request)

    return httpx.MockTransport(wrapped), seen


def test_openai_compatible_request_and_parsing():
    mock, seen = transport(lambda r: httpx.Response(200, json={
        "model": "llama-3.3-70b-versatile",
        "choices": [{"message": {"content": '{"ok": true}'}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30},
    }))
    p = OpenAICompatibleProvider("groq", "https://api.groq.com/openai/v1", "gsk_test", "llama-3.3-70b-versatile", 5, transport=mock)
    result = p.complete_json("system text", "user text", temperature=0.1, max_tokens=500)

    request = seen[0]
    assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer gsk_test"
    body = json.loads(request.content)
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"] == [{"role": "system", "content": "system text"}, {"role": "user", "content": "user text"}]
    assert body["max_tokens"] == 500 and body["temperature"] == 0.1
    assert result.text == '{"ok": true}' and result.input_tokens == 120 and result.output_tokens == 30


def test_gemini_request_and_parsing():
    mock, seen = transport(lambda r: httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": '{"a":'}, {"text": " 1}"}]}}],
        "usageMetadata": {"promptTokenCount": 80, "candidatesTokenCount": 12},
        "modelVersion": "gemini-2.5-flash",
    }))
    p = GeminiProvider("AIza_test", "gemini-2.5-flash", 5, transport=mock)
    result = p.complete_json("sys", "usr", temperature=0.2, max_tokens=300)

    request = seen[0]
    assert str(request.url).endswith("/v1beta/models/gemini-2.5-flash:generateContent")
    assert request.headers["x-goog-api-key"] == "AIza_test"
    body = json.loads(request.content)
    assert body["systemInstruction"]["parts"][0]["text"] == "sys"
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert result.text == '{"a": 1}' and result.input_tokens == 80


@pytest.mark.parametrize("status,retryable", [(429, True), (503, True), (400, False), (401, False)])
def test_errors_are_classified(status, retryable):
    mock, _ = transport(lambda r: httpx.Response(status, json={"error": {"message": "nope"}}))
    p = OpenAICompatibleProvider("groq", "https://x/v1", "k", "m", 5, transport=mock)
    with pytest.raises(LLMError) as exc:
        p.complete_json("s", "u", temperature=0, max_tokens=10)
    assert exc.value.retryable is retryable and exc.value.status == status and "nope" in str(exc.value)


class Fake:
    def __init__(self, name, outcomes):
        self.name, self.model, self.outcomes, self.calls = name, f"{name}-model", list(outcomes), 0

    def complete_json(self, system, user, *, temperature, max_tokens):
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else "ok"
        if isinstance(outcome, Exception):
            raise outcome
        return LLMResult(text="{}", provider=self.name, model=self.model)


def test_router_falls_back_and_cools_down_rate_limited_provider():
    first = Fake("groq", [LLMError("groq", "rate limited", retryable=True, status=429)])
    second = Fake("gemini", [])
    router = LLMRouter([first, second], cooldown_seconds=60)

    attempts = []
    assert router.complete_json("s", "u", attempts=attempts).provider == "gemini"
    assert "rate limited" in attempts[0]
    # groq is cooling down, so the next call goes straight to gemini
    attempts = []
    router.complete_json("s", "u", attempts=attempts)
    assert first.calls == 1 and attempts == ["groq: skipped (cooling down)"]


def test_router_does_not_cool_down_on_bad_requests_and_reports_all_failures():
    bad = Fake("groq", [LLMError("groq", "bad prompt", retryable=False), LLMError("groq", "bad prompt", retryable=False)])
    router = LLMRouter([bad], cooldown_seconds=60)
    with pytest.raises(AllProvidersFailed) as exc:
        router.complete_json("s", "u")
    assert "bad prompt" in str(exc.value)
    with pytest.raises(AllProvidersFailed):
        router.complete_json("s", "u")
    assert bad.calls == 2  # still tried: non-retryable errors are request problems, not provider outages


def test_providers_without_keys_are_skipped(monkeypatch):
    from app.adapters import llm

    monkeypatch.setattr(llm.settings, "llm_provider_order", "gemini,groq,openrouter")
    monkeypatch.setattr(llm.settings, "groq_api_key", "gsk")
    monkeypatch.setattr(llm.settings, "gemini_api_key", "")
    monkeypatch.setattr(llm.settings, "openrouter_api_key", "or")
    assert [p.name for p in build_providers()] == ["groq", "openrouter"]
    monkeypatch.setattr(llm.settings, "groq_api_key", "")
    monkeypatch.setattr(llm.settings, "openrouter_api_key", "")
    assert build_providers() == []
