"""Embeddings: coverage, freshness, privacy, tenant-scoped nearest-neighbour search."""
import os
from pathlib import Path

import pytest

from app.adapters.embeddings import get_embedder
from app.core.database import SessionLocal
from app.matching import embeddings
from app.models.db_models import CandidateProfile, Embedding, Job


def test_seeded_candidates_and_jobs_are_embedded():
    with SessionLocal() as db:
        model = get_embedder().name
        for entity_type, model_cls in (("candidate", CandidateProfile), ("job", Job)):
            ids = {obj.id for obj in db.query(model_cls).all()}
            embedded = {e.entity_id for e in db.query(Embedding).filter(Embedding.entity_type == entity_type, Embedding.model == model)}
            assert ids <= embedded, f"missing {entity_type} embeddings: {ids - embedded}"


def test_profile_edits_re_embed_only_when_text_changes(client, auth):
    h = auth("elena")
    with SessionLocal() as db:
        before = db.query(Embedding).filter(Embedding.entity_id == "cand_002").one().content_hash
    client.patch("/api/v1/candidates/me", headers=h, json={"bio": "Platform architect for real-time collaboration and CRDT sync engines."})
    with SessionLocal() as db:
        after = db.query(Embedding).filter(Embedding.entity_id == "cand_002").one().content_hash
        assert after != before
        assert embeddings.refresh(db, "candidate", [db.get(CandidateProfile, "cand_002")]) == 0  # unchanged -> skipped


def test_embedded_text_contains_no_personal_data():
    with SessionLocal() as db:
        cand = db.get(CandidateProfile, "cand_001")
        text = embeddings.candidate_text(cand)
        assert cand.user.full_name not in text
        assert cand.user.email not in text
        assert "Skills:" in text


def test_nearest_respects_allowed_ids():
    with SessionLocal() as db:
        cand = db.get(CandidateProfile, "cand_001")
        query = embeddings.embed_query(embeddings.candidate_text(cand))
        everyone = embeddings.nearest(db, "candidate", query, None, 3)
        assert everyone[0][0] == "cand_001" and everyone[0][1] > 0.99
        scoped = embeddings.nearest(db, "candidate", query, ["cand_002", "cand_003"], 3)
        assert {eid for eid, _ in scoped} <= {"cand_002", "cand_003"}
        assert embeddings.nearest(db, "candidate", query, [], 3) == []


_MODEL_CACHE = Path(__file__).resolve().parents[1] / "backend" / ".cache" / "fastembed"


@pytest.mark.skipif(
    not (_MODEL_CACHE.exists() or os.environ.get("RUN_MODEL_TESTS")),
    reason="local embedding model not downloaded (set RUN_MODEL_TESTS=1 to download it)",
)
def test_fastembed_understands_meaning_not_just_words():
    from app.adapters.embeddings.fastembed_provider import FastEmbedProvider

    model = FastEmbedProvider("BAAI/bge-small-en-v1.5", 384, str(_MODEL_CACHE))
    job, k8s, chef = [embeddings.np.asarray(v) for v in model.embed([
        "Cloud infrastructure and container orchestration",
        "Built AWS platforms with Kubernetes, Docker and Terraform",
        "Pastry chef specialising in French desserts",
    ])]
    assert embeddings.cosine(job, k8s) > embeddings.cosine(job, chef) + 0.15


def test_redaction_removes_identifiers():
    from app.matching.redaction import redact

    text = ("Aarav Sharma\naarav@stanford.edu | +1 (415) 555-0100 | linkedin.com/in/aarav | https://aarav.dev\n"
            "Aarav led a team of 6 for 4 years; cut costs 30% in 2023.")
    clean = redact(text, names=["Aarav Sharma"])
    for secret in ("Aarav", "Sharma", "aarav@stanford.edu", "555-0100", "linkedin.com/in/aarav", "aarav.dev"):
        assert secret.lower() not in clean.lower()
    # ordinary numbers are kept
    assert "team of 6 for 4 years" in clean and "30% in 2023" in clean
