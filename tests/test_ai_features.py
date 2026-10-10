"""AI features: orchestration (limits, validation, fallback, governance), privacy, drafts, prompts."""
import contextlib
import json
import uuid

import pytest

from app.adapters.llm import LLMError, LLMResult, LLMRouter
from app.ai import orchestrator
from app.core.database import AdminSessionLocal as SessionLocal  # test setup bypasses RLS
from app.models.db_models import AIRequest, CandidateProfile, Organization, Resume

RESUME = b"""Aarav Sharma
Staff AI Engineer
San Francisco, CA | aarav@stanford.edu | +1 (415) 555-0100 | github.com/aarav
Skills
Python, PyTorch, k8s, PostgreSQL
Experience
Staff AI Engineer - Anthropic (Jan 2022 - Present)
Scaled inference to 50k QPS with custom CUDA kernels
Education
M.S. in Computer Science - Stanford University, 2020
"""

LLM_RESUME = {
    "headline": "Staff AI Engineer", "summary": "Builds inference systems.", "total_experience_years": 6,
    "skills": ["python", "pytorch", "k8s"],
    "work_experience": [{"job_title": "Staff AI Engineer", "company_name": "Anthropic", "start_date": "2022-01", "is_current": True}],
    "education": [{"institution": "Stanford University", "degree": "M.S.", "field_of_study": "CS", "graduation_year": 2020}],
    "certifications": [], "projects": [], "languages": [], "industries": ["AI"],
}


class FakeProvider:
    def __init__(self, replies):
        self.name, self.model, self.replies, self.prompts = "groq", "llama-test", list(replies), []

    def complete_json(self, system, user, *, temperature, max_tokens):
        self.prompts.append(user)
        reply = self.replies.pop(0) if self.replies else "{}"
        if isinstance(reply, Exception):
            raise reply
        return LLMResult(text=reply if isinstance(reply, str) else json.dumps(reply), provider=self.name,
                         model=self.model, input_tokens=900, output_tokens=300, latency_ms=40)


@pytest.fixture
def fake_llm(monkeypatch):
    def install(*replies):
        provider = FakeProvider(replies)
        monkeypatch.setattr(orchestrator, "get_llm_router", lambda: LLMRouter([provider], cooldown_seconds=60))
        return provider
    return install


@contextlib.contextmanager
def org_credits(org_id, used, limit):
    with SessionLocal() as db:
        org = db.get(Organization, org_id)
        before = (org.monthly_ai_credits_used, org.monthly_ai_credits)
        org.monthly_ai_credits_used, org.monthly_ai_credits = used, limit
        db.commit()
    try:
        yield
    finally:
        with SessionLocal() as db:
            org = db.get(Organization, org_id)
            org.monthly_ai_credits_used, org.monthly_ai_credits = before
            db.commit()


def _parse(client, headers, data=RESUME, filename="cv.txt", **form):
    return client.post("/api/v1/ai/resume/parse", headers=headers, files={"file": (filename, data, "text/plain")}, data=form)


def _last_request(feature):
    with SessionLocal() as db:
        return db.query(AIRequest).filter(AIRequest.feature == feature).order_by(AIRequest.created_at.desc()).first()


# ---------------------------------------------------------------- resume parsing
def test_resume_parse_without_providers_uses_rules_and_does_not_change_profile(client, auth):
    with SessionLocal() as db:
        before = db.get(CandidateProfile, "cand_001").title
    res = _parse(client, auth("aarav"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["method"] == "rules" and "no AI provider is configured" in body["notice"]
    assert body["contact"]["email"] == "aarav@stanford.edu" and body["contact"]["name"] == "Aarav Sharma"
    assert {"Python", "PyTorch", "Kubernetes"} <= set(body["draft"]["skills"])
    assert body["draft"]["work_experience"][0]["company_name"] == "Anthropic"
    assert body["resume_id"] and body["candidate_id"] == "cand_001"
    with SessionLocal() as db:
        assert db.get(CandidateProfile, "cand_001").title == before  # a draft, not applied
        assert db.get(Resume, body["resume_id"]).document_id == body["document_id"]
    req = _last_request("resume_parse")
    assert req.status == "fallback" and req.provider == "rules" and req.output_json is None


def test_resume_parse_with_llm_never_sends_personal_details(client, auth, fake_llm):
    provider = fake_llm(LLM_RESUME)
    body = _parse(client, auth("aarav")).json()
    assert body["method"] == "ai" and body["provider"] == "groq"
    sent = provider.prompts[0]
    for secret in ("Aarav", "Sharma", "aarav@stanford.edu", "555-0100", "github.com/aarav"):
        assert secret not in sent
    assert "[email]" in sent and "Scaled inference" in sent
    assert body["draft"]["skills"] == ["Python", "PyTorch", "Kubernetes"]  # canonicalized
    req = _last_request("resume_parse")
    assert req.status == "success" and req.input_tokens == 900 and req.credits == 2 and req.output_json is None


def test_invalid_model_output_is_retried_then_falls_back(client, auth, fake_llm):
    provider = fake_llm("not json at all", {"title": "Platform Engineer", "required_skills": ["go"]})
    body = client.post("/api/v1/ai/jobs/generate", headers=auth("anthropic"), json={"brief": "Platform Engineer, Go"}).json()
    assert body["method"] == "ai" and body["draft"]["required_skills"] == ["Go"]
    assert "didn't match the expected format" in provider.prompts[1] or "not valid" in provider.prompts[1]

    fake_llm("nope", "still nope")
    body = client.post("/api/v1/ai/jobs/generate", headers=auth("anthropic"), json={"brief": "Platform Engineer, Go"}).json()
    assert body["method"] == "rules" and "unavailable" in body["notice"]
    req = _last_request("job_generate")
    assert req.status == "fallback" and "expected format" in req.error


def test_provider_outage_falls_back_to_rules(client, auth, fake_llm):
    fake_llm(LLMError("groq", "HTTP 429: rate limited", retryable=True, status=429))
    body = client.post("/api/v1/ai/jobs/analyze", headers=auth("anthropic"),
                       json={"text": "Senior Data Engineer\nRequirements:\n5+ years with Python and Spark\nNice to have: dbt"}).json()
    assert body["method"] == "rules"
    assert body["analysis"]["required_skills"][:2] == ["Python", "Spark"] and body["analysis"]["preferred_skills"] == ["dbt"]
    assert "rate limited" in _last_request("job_analyze").attempts


def test_org_credits_and_daily_limits_block_model_calls(client, auth, fake_llm, monkeypatch):
    provider = fake_llm({"title": "x"})
    with org_credits("org_anthropic", used=100, limit=100):
        body = client.post("/api/v1/ai/jobs/generate", headers=auth("anthropic"), json={"brief": "Data Analyst, SQL"}).json()
    assert body["method"] == "rules" and "AI credits" in body["notice"] and provider.prompts == []
    assert _last_request("job_generate").status == "blocked"

    monkeypatch.setattr(orchestrator.settings, "ai_user_daily_limit", 1)
    fake_llm({"title": "Data Analyst"})
    client.post("/api/v1/ai/jobs/generate", headers=auth("stripe"), json={"brief": "Data Analyst, SQL"})
    blocked = client.post("/api/v1/ai/jobs/generate", headers=auth("stripe"), json={"brief": "Data Analyst, SQL"}).json()
    assert blocked["method"] == "rules" and "today's AI limit" in blocked["notice"]


def test_successful_calls_consume_org_credits(client, auth, fake_llm):
    fake_llm({"title": "ML Engineer", "required_skills": ["Python"]})
    with org_credits("org_stripe", used=0, limit=1000):
        client.post("/api/v1/ai/jobs/generate", headers=auth("stripe"), json={"brief": "ML Engineer, Python"})
        with SessionLocal() as db:
            assert db.get(Organization, "org_stripe").monthly_ai_credits_used == 2
        usage = client.get("/api/v1/ai/usage", headers=auth("stripe")).json()
        assert usage["credits_used"] == 2 and any(r["feature"] == "job_generate" and r["status"] == "success" for r in usage["rows"])


def test_recruiter_parses_resume_then_creates_candidate_with_it(client, auth):
    stripe = auth("stripe")
    parsed = _parse(client, stripe).json()
    assert parsed["candidate_id"] is None and parsed["resume_id"] is None
    email = f"parsed.{uuid.uuid4().hex[:6]}@example.com"
    payload = {"full_name": "Parsed Person", "email": email, "title": parsed["draft"]["headline"],
               "skills": parsed["draft"]["skills"], "resume_document_id": parsed["document_id"]}
    # another organization can't claim the file
    other = client.post("/api/v1/candidates", headers=auth("anthropic"), json={**payload, "email": f"x{email}"})
    assert other.status_code == 404
    created = client.post("/api/v1/candidates", headers=stripe, json=payload)
    assert created.status_code == 201, created.text
    resumes = client.get(f"/api/v1/resumes/candidate/{created.json()['id']}", headers=stripe).json()
    assert resumes and resumes[0]["document_id"] == parsed["document_id"]


def test_candidates_cannot_parse_for_others_or_generate_jobs(client, auth):
    assert _parse(client, auth("aarav"), candidate_id="cand_002").status_code == 403
    assert client.post("/api/v1/ai/jobs/generate", headers=auth("aarav"), json={"brief": "x role"}).status_code == 403


# ---------------------------------------------------------------- job drafts
def test_job_generation_from_brief_without_ai(client, auth):
    body = client.post("/api/v1/ai/jobs/generate", headers=auth("anthropic"),
                       json={"brief": "Senior Backend Developer, 5+ years, Node.js, AWS"}).json()
    d = body["draft"]
    assert body["method"] == "rules"
    assert d["title"] == "Senior Backend Developer" and d["seniority"] == "Senior" and d["min_experience_years"] == 5
    assert set(d["required_skills"]) == {"Node.js", "AWS"}
    assert "GCP" not in d["preferred_skills"] and "Azure" not in d["preferred_skills"]
    assert d["screening_questions"] and d["interview_criteria"]


def test_job_drafts_carry_screening_questions_into_the_job(client, auth):
    res = client.post("/api/v1/jobs", headers=auth("stripe"), json={
        "title": "Payments Engineer", "description": "Build payments.", "status": "Draft",
        "screening_questions": ["Describe a payments system you built."], "interview_criteria": ["Depth in Go"],
    })
    assert res.status_code == 200
    assert res.json()["screening_questions"] == ["Describe a payments system you built."]


def test_legacy_job_spec_endpoint_uses_the_real_generator(client, auth):
    spec = client.post("/api/v1/ai/generate-job-spec", headers=auth("anthropic"), json={"title": "Frontend Engineer, React, TypeScript"}).json()
    assert spec["title"] == "Frontend Engineer" and {"React", "TypeScript"} <= set(spec["required_skills"])


# ---------------------------------------------------------------- prompt versions
def test_prompt_versions_and_rollback(client, auth, fake_llm):
    admin = auth("admin")
    prompts = client.get("/api/v1/admin/ai/prompts", headers=admin, params={"key": "job_analyze"}).json()
    assert prompts[0]["version"] == 1 and prompts[0]["status"] == "active"
    assert client.get("/api/v1/admin/ai/prompts", headers=auth("anthropic")).status_code == 403
    assert client.post("/api/v1/admin/ai/prompts/job_analyze/versions", headers=admin,
                       json={"system": "x" * 30, "user_template": "no placeholder here"}).status_code == 422

    v2 = client.post("/api/v1/admin/ai/prompts/job_analyze/versions", headers=admin,
                     json={"system": prompts[0]["system"] + " Be concise.", "user_template": "JD:\n{job_text}", "notes": "shorter"}).json()
    assert v2["version"] == 2 and v2["status"] == "draft"
    client.post("/api/v1/admin/ai/prompts/job_analyze/versions/2/activate", headers=admin)

    provider = fake_llm({"title": "Analyst", "required_skills": ["SQL"]})
    client.post("/api/v1/ai/jobs/analyze", headers=auth("anthropic"), json={"text": "Analyst role needing SQL and dashboards."})
    assert provider.prompts[0].startswith("JD:\n") and _last_request("job_analyze").prompt_version == 2

    client.post("/api/v1/admin/ai/prompts/job_analyze/versions/1/activate", headers=admin)  # rollback
    states = {p["version"]: p["status"] for p in client.get("/api/v1/admin/ai/prompts", headers=admin, params={"key": "job_analyze"}).json()}
    assert states == {1: "active", 2: "retired"}
