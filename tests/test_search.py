"""Global search: query understanding, hybrid ranking, tenancy."""
import uuid

import pytest

from app.core.database import AdminSessionLocal as SessionLocal  # test setup bypasses RLS
from app.matching.ontology import load_skill_graph
from app.search.service import parse_query


@pytest.fixture(scope="module")
def graph():
    with SessionLocal() as db:
        return load_skill_graph(db)


def test_query_understanding(graph):
    p = parse_query("Find senior engineers with strong cloud experience who have built scalable SaaS platforms", graph)
    assert p.min_experience == 5
    assert "saas" in p.keywords and "scalable" in p.keywords

    p = parse_query("5+ years Python developers in Bangalore with k8s", graph)
    assert p.min_experience == 5 and p.location == "Bangalore"
    assert {"Python", "Kubernetes"} <= set(p.skills)

    p = parse_query("remote React developers", graph)
    assert p.remote_preference == "Remote" and "React" in p.skills and p.location is None


def test_candidate_search_ranks_and_explains(client, auth):
    res = client.get("/api/v1/search", headers=auth("anthropic"), params={"q": "PyTorch LLM inference engineers", "types": ["candidates"]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert "PyTorch" in body["interpreted"]["skills"]
    ids = [h["candidate"]["id"] for h in body["candidates"]]
    assert ids and ids[0] == "cand_001"
    assert any(r.startswith("Skills:") for r in body["candidates"][0]["reasons"])
    # contact details follow the usual privacy rule
    for hit in body["candidates"]:
        if hit["candidate"]["id"] == "cand_002":
            assert hit["candidate"]["email"] == ""


def test_structured_filters_from_language_are_applied(client, auth):
    body = client.get("/api/v1/search", headers=auth("admin"), params={"q": "engineers with 7+ years", "types": ["candidates"]}).json()
    assert body["interpreted"]["min_experience"] == 7
    assert all(h["candidate"]["experience_years"] >= 7 for h in body["candidates"])


def test_search_never_crosses_tenants(client, auth):
    marker = f"zyx{uuid.uuid4().hex[:6]}"
    created = client.post("/api/v1/candidates", headers=auth("anthropic"), json={
        "full_name": "Private Person", "email": f"{marker}@example.com", "title": f"{marker} specialist", "bio": f"Expert in {marker}.",
    })
    assert created.status_code == 201
    mine = client.get("/api/v1/search", headers=auth("anthropic"), params={"q": marker, "types": ["candidates"]}).json()
    theirs = client.get("/api/v1/search", headers=auth("stripe"), params={"q": marker, "types": ["candidates"]}).json()
    assert created.json()["id"] in [h["candidate"]["id"] for h in mine["candidates"]]
    assert created.json()["id"] not in [h["candidate"]["id"] for h in theirs["candidates"]]


def test_result_types_depend_on_role(client, auth):
    as_candidate = client.get("/api/v1/search", headers=auth("aarav"), params={"q": "engineer"}).json()
    assert as_candidate["candidates"] == [] and as_candidate["organizations"] == []
    assert all(j["status"] == "Active" for j in as_candidate["jobs"])
    as_admin = client.get("/api/v1/search", headers=auth("admin"), params={"q": "anthropic", "types": ["organizations"]}).json()
    assert [o["id"] for o in as_admin["organizations"]] == ["org_anthropic"]
    assert client.get("/api/v1/search", headers=auth("stripe"), params={"q": "anthropic", "types": ["organizations"]}).json()["organizations"] == []


def test_skill_search_uses_synonyms(client, auth):
    skills = client.get("/api/v1/search", headers=auth("stripe"), params={"q": "k8s", "types": ["skills"]}).json()["skills"]
    assert "Kubernetes" in [s["name"] for s in skills]
    assert client.get("/api/v1/search", params={"q": "x"}).status_code == 401
