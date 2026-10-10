"""Matching engine v2: explainable, deterministic, ontology-aware, no protected attributes."""
import dataclasses

import pytest

from app.core.database import AdminSessionLocal as SessionLocal  # test setup bypasses RLS
from app.matching.engine import DEFAULT_WEIGHTS, CandidateFacts, JobFacts, score_match
from app.matching.ontology import load_skill_graph


@pytest.fixture(scope="module")
def graph():
    with SessionLocal() as db:
        return load_skill_graph(db)


def cand(**over):
    base = dict(
        skills=("Python", "Kubernetes", "AWS", "PostgreSQL"), certifications=(), experience_years=6.0,
        titles=("Senior Backend Engineer",), location="Bangalore, India", preferred_locations=(),
        remote_preference="Hybrid", expected_salary=4_000_000, education_levels=("Bachelor's in CS",),
        industry="Fintech", notice_period_days=30,
    )
    base.update(over)
    return CandidateFacts(**base)


def job(**over):
    base = dict(
        required_skills=("Python", "Kubernetes", "AWS"), preferred_skills=("Terraform",),
        min_experience_years=5, max_experience_years=10, title="Backend Engineer", location="Bangalore, India",
        workplace_type="Hybrid", salary_min=3_000_000, salary_max=4_500_000, required_education="Bachelor's",
        industry="Fintech",
    )
    base.update(over)
    return JobFacts(**base)


def test_score_is_the_weighted_sum_of_the_factors_shown(graph):
    r = score_match(cand(), job(), graph, semantic_similarity=0.8)
    shown = round(100 * sum(f.score * f.weight for f in r.factors if f.applicable))
    assert r.score == shown
    assert abs(sum(f.weight for f in r.factors) - 1.0) < 1e-6
    assert all(f.detail for f in r.factors)
    assert r.fit_level == "Strong fit" and r.score >= 80


def test_deterministic(graph):
    a = score_match(cand(), job(), graph, semantic_similarity=0.6)
    b = score_match(cand(), job(), graph, semantic_similarity=0.6)
    assert a.score == b.score and [f.score for f in a.factors] == [f.score for f in b.factors]


def test_missing_data_is_excluded_not_penalized(graph):
    r = score_match(cand(expected_salary=None, notice_period_days=None, industry=""), job(), graph, semantic_similarity=None)
    by_key = {f.key: f for f in r.factors}
    for key in ("salary", "notice", "industry", "semantic"):
        assert not by_key[key].applicable and by_key[key].weight == 0
    assert abs(sum(f.weight for f in r.factors) - 1.0) < 1e-6
    assert r.score >= 80  # still a strong match on what we know


def test_related_skills_get_partial_credit_with_explanation(graph):
    r = score_match(cand(skills=("TypeScript",)), job(required_skills=("JavaScript",), preferred_skills=()), graph)
    evidence = r.skills[0]
    assert evidence.score == 0.9 and evidence.via == "TypeScript" and evidence.kind == "parent"
    synonym = score_match(cand(skills=("k8s",)), job(required_skills=("Kubernetes",), preferred_skills=()), graph).skills[0]
    assert synonym.score == 1.0 and synonym.kind == "synonym"


def test_certifications_count_as_skill_evidence(graph):
    without = score_match(cand(skills=("Python",)), job(required_skills=("AWS",), preferred_skills=()), graph)
    with_cert = score_match(cand(skills=("Python",), certifications=("AWS Certified Solutions Architect",)),
                            job(required_skills=("AWS",), preferred_skills=()), graph)
    assert without.skills[0].score == 0 and with_cert.skills[0].score == 1.0


def test_missing_required_skills_are_reported(graph):
    r = score_match(cand(skills=("Python",)), job(), graph)
    assert {"skill": "Kubernetes", "importance": "required"} in r.missing_skills
    assert any(g.startswith("Missing required skills") for g in r.gaps)


def test_experience_is_graded(graph):
    exp = lambda years: next(f for f in score_match(cand(experience_years=years), job(), graph).factors if f.key == "experience")
    assert exp(6).score == 1.0
    assert exp(2.5).score == pytest.approx(0.5)
    assert exp(15).score == 0.85


def test_location_and_work_mode(graph):
    loc = lambda **c: next(f for f in score_match(cand(**c), job(workplace_type="Onsite"), graph).factors if f.key == "location")
    assert loc().score == 1.0
    assert loc(location="Pune, India").score == 0.6
    assert loc(location="Pune, India", preferred_locations=("Bangalore",)).score == 1.0
    assert loc(location="Berlin, Germany").score == 0.3
    remote = next(f for f in score_match(cand(location="Berlin, Germany"), job(workplace_type="Remote"), graph).factors if f.key == "location")
    assert remote.score == 1.0


def test_org_weights_change_the_result(graph):
    weak_skills = cand(skills=("Python",))
    default = score_match(weak_skills, job(), graph).score
    skills_heavy = score_match(weak_skills, job(), graph, weights={**DEFAULT_WEIGHTS, "skills": 1.0}).score
    assert skills_heavy < default


def test_engine_cannot_see_protected_or_identifying_attributes():
    fields = {f.name for f in dataclasses.fields(CandidateFacts)}
    for forbidden in ("name", "full_name", "email", "phone", "photo", "avatar_url", "age", "date_of_birth", "gender", "nationality", "religion", "marital_status"):
        assert forbidden not in fields
