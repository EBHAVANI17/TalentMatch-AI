"""Request hardening: rate limits, request IDs and security headers."""
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core import rate_limit as rl


def _limited_app(limit_text: str) -> TestClient:
    app = FastAPI()

    @app.get("/ping", dependencies=[Depends(rl.rate_limit("test-scope", limit_text))])
    def ping():
        return {"ok": True}

    return TestClient(app)


def test_limit_parsing():
    assert rl.Limit.parse("10/minute") == rl.Limit(10, 60)
    assert rl.Limit.parse("5/seconds") == rl.Limit(5, 1)
    assert rl.Limit.parse("1000/hour") == rl.Limit(1000, 3600)


def test_rate_limit_blocks_after_quota_and_sets_retry_after():
    rl.backend.reset()
    client = _limited_app("3/minute")
    codes = [client.get("/ping").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    blocked = client.get("/ping")
    assert blocked.status_code == 429
    assert 0 < int(blocked.headers["Retry-After"]) <= 60
    rl.backend.reset()


def test_rate_limit_can_be_disabled(monkeypatch):
    rl.backend.reset()
    monkeypatch.setattr(rl.settings, "rate_limit_enabled", False)
    client = _limited_app("1/minute")
    assert [client.get("/ping").status_code for _ in range(3)] == [200, 200, 200]


def test_auth_endpoints_are_rate_limited():
    from fastapi.routing import APIRoute

    from app.main import app

    auth_paths = {"/api/v1/auth/login", "/api/v1/auth/register/candidate", "/api/v1/auth/register/employer"}
    limited = {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path in auth_paths
        and any(d.call.__qualname__.startswith("rate_limit.") for d in route.dependant.dependencies)
    }
    assert limited == auth_paths


def test_api_responses_carry_security_headers(client):
    res = client.get("/api/v1/jobs")
    assert res.status_code == 200
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert res.headers["Cache-Control"] == "no-store"
    assert len(res.headers["X-Request-ID"]) >= 16


def test_request_id_is_propagated_when_valid(client):
    res = client.get("/health", headers={"X-Request-ID": "trace-abc_123"})
    assert res.headers["X-Request-ID"] == "trace-abc_123"
    bad = client.get("/health", headers={"X-Request-ID": "bad id!"})
    assert bad.headers["X-Request-ID"] != "bad id!"


def test_ui_page_is_not_given_api_csp(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Content-Security-Policy" not in res.headers  # legacy UI uses inline scripts and CDNs
