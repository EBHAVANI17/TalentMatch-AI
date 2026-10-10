"""Skill ontology: synonyms, compound skills and directional related-skill credit."""
from app.core.database import AdminSessionLocal as SessionLocal  # test setup bypasses RLS
from app.db.reference_data import ensure_reference_data
from app.matching.ontology import load_skill_graph
from app.models.db_models import SkillAlias, SkillRelation, SkillTaxonomy


def graph():
    with SessionLocal() as db:
        return load_skill_graph(db)


def test_synonyms_resolve_to_catalog_names():
    g = graph()
    assert g.canonical("k8s") == ["Kubernetes"]
    assert g.canonical("Postgres") == ["PostgreSQL"]
    assert g.canonical("  golang ") == ["Go"]
    assert g.canonical("Some Brand New Skill") == ["Some Brand New Skill"]


def test_compound_skills_are_split():
    g = graph()
    assert g.canonical("Docker & Kubernetes") == ["Docker", "Kubernetes"]
    assert g.canonical("Python / FastAPI") == ["Python", "FastAPI"]


def test_related_skill_credit_is_directional():
    g = graph()
    has_ts = g.canonical_set(["TypeScript"])
    has_js = g.canonical_set(["JavaScript"])
    strong = g.best_evidence(has_ts, "JavaScript")
    weak = g.best_evidence(has_js, "TypeScript")
    assert strong.score == 0.9 and strong.via == "TypeScript" and strong.kind == "parent"
    assert weak.score == 0.5
    assert g.best_evidence(g.canonical_set(["kubernetes"]), "k8s").score == 1.0
    assert g.best_evidence(g.canonical_set(["Excel"]), "Kubernetes").score == 0.0


def test_compound_requirement_scores_each_part():
    g = graph()
    half = g.best_evidence(g.canonical_set(["PostgreSQL"]), "PostgreSQL & pgvector")
    assert 0.5 <= half.score < 1.0


def test_mentions_in_free_text():
    g = graph()
    found = g.mentions("Senior engineers with k8s, AWS and strong Python experience")
    assert {"Kubernetes", "AWS", "Python"} <= set(found)


def test_reference_data_is_idempotent():
    with SessionLocal() as db:
        counts = lambda: (db.query(SkillTaxonomy).count(), db.query(SkillAlias).count(), db.query(SkillRelation).count())
        before = counts()
        ensure_reference_data(db)
        assert counts() == before
