"""Embeddings for candidates and jobs: what text is embedded, storage, and similarity search.

Only professional content is embedded. Names, contact details, photos and other
personal attributes are never sent to the embedding model.
"""
import hashlib
import uuid
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.adapters.embeddings import get_embedder
from app.matching.redaction import redact
from app.models.db_models import CandidateProfile, Embedding, Job

CANDIDATE, JOB = "candidate", "job"
_MAX_CHARS = 6000  # long resumes are truncated; the start carries the most signal


def candidate_text(c: CandidateProfile) -> str:
    parts = [c.title or "", c.bio or "", "Skills: " + ", ".join(c.skills)]
    for w in c.work_experiences:
        parts.append(f"{w.job_title} at {w.company_name}. {w.description or ''} {' '.join(w.achievements)}")
    for p in c.projects:
        parts.append(f"Project: {p.title}. {p.description or ''} {', '.join(p.tech_stack)}")
    parts.extend(f"Certification: {cert.name}" for cert in c.certifications)
    if c.industry:
        parts.append(f"Industry: {c.industry}")
    if c.raw_resume_text:
        parts.append(c.raw_resume_text)
    text = "\n".join(p.strip() for p in parts if p and p.strip())[:_MAX_CHARS]
    return redact(text, names=[c.user.full_name] if c.user else [])


def job_text(j: Job) -> str:
    parts = [
        j.title, j.department, j.description,
        "Responsibilities: " + "; ".join(j.responsibilities),
        "Required skills: " + ", ".join(j.required_skills),
        "Preferred skills: " + ", ".join(j.preferred_skills),
    ]
    if j.industry:
        parts.append(f"Industry: {j.industry}")
    return "\n".join(p.strip() for p in parts if p and p.strip())[:_MAX_CHARS]


# ---------------------------------------------------------------------------
# Storage (pgvector on PostgreSQL, float32 bytes elsewhere)
# ---------------------------------------------------------------------------
def _is_pg(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _to_db(db: Session, vector: Sequence[float]):
    return list(map(float, vector)) if _is_pg(db) else np.asarray(vector, dtype=np.float32).tobytes()


def _from_db(value) -> np.ndarray:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return np.frombuffer(bytes(value), dtype=np.float32)
    return np.asarray(value, dtype=np.float32)


def _hash(model: str, content: str) -> str:
    return hashlib.sha256(f"{model}\n{content}".encode()).hexdigest()


def _owner_org(entity_type: str, obj) -> Optional[str]:
    return obj.organization_id if entity_type == JOB else obj.owner_org_id


def refresh(db: Session, entity_type: str, objects: Iterable) -> int:
    """(Re)embed objects whose text changed. Batches model calls. Returns how many were embedded. Caller commits."""
    embedder = get_embedder()
    build = candidate_text if entity_type == CANDIDATE else job_text
    objects = list(objects)
    if not objects:
        return 0
    existing = {
        e.entity_id: e for e in db.query(Embedding).filter(
            Embedding.entity_type == entity_type,
            Embedding.model == embedder.name,
            Embedding.entity_id.in_([o.id for o in objects]),
        )
    }
    todo: List[Tuple[object, str, str]] = []
    for obj in objects:
        content = build(obj)
        digest = _hash(embedder.name, content)
        current = existing.get(obj.id)
        if content and (current is None or current.content_hash != digest):
            todo.append((obj, content, digest))
    if not todo:
        return 0
    vectors = embedder.embed([content for _, content, _ in todo])
    for (obj, _, digest), vector in zip(todo, vectors):
        row = existing.get(obj.id)
        if row is None:
            row = Embedding(id=f"emb_{uuid.uuid4().hex[:16]}", entity_type=entity_type, entity_id=obj.id, model=embedder.name)
            db.add(row)
        row.organization_id = _owner_org(entity_type, obj)
        row.content_hash = digest
        row.vector = _to_db(db, vector)
        row.updated_at = datetime.utcnow()
    db.flush()
    return len(todo)


def vectors_for(db: Session, entity_type: str, ids: Iterable[str]) -> Dict[str, np.ndarray]:
    ids = list(ids)
    if not ids:
        return {}
    rows = db.query(Embedding.entity_id, Embedding.vector).filter(
        Embedding.entity_type == entity_type,
        Embedding.model == get_embedder().name,
        Embedding.entity_id.in_(ids),
    )
    return {entity_id: _from_db(vector) for entity_id, vector in rows}


def embed_query(query: str) -> np.ndarray:
    return np.asarray(get_embedder().embed([query])[0], dtype=np.float32)


def cosine(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> Optional[float]:
    if a is None or b is None:
        return None
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else None


def nearest(db: Session, entity_type: str, query_vec: np.ndarray, allowed_ids: Optional[Sequence[str]], limit: int) -> List[Tuple[str, float]]:
    """(entity_id, cosine similarity), best first, restricted to allowed_ids (the caller's tenant scope)."""
    if allowed_ids is not None and not allowed_ids:
        return []
    model = get_embedder().name
    if _is_pg(db):
        sql = (
            "SELECT entity_id, 1 - (vector <=> CAST(:q AS vector)) AS similarity FROM embeddings "
            "WHERE entity_type = :t AND model = :m"
            + (" AND entity_id = ANY(:ids)" if allowed_ids is not None else "")
            + " ORDER BY vector <=> CAST(:q AS vector) LIMIT :n"
        )
        params = {"q": "[" + ",".join(f"{x:.6f}" for x in query_vec) + "]", "t": entity_type, "m": model, "n": limit}
        if allowed_ids is not None:
            params["ids"] = list(allowed_ids)
        return [(row[0], float(row[1])) for row in db.execute(text(sql), params)]
    # SQLite / development: exact search in Python
    vectors = vectors_for(db, entity_type, allowed_ids) if allowed_ids is not None else {
        eid: _from_db(v) for eid, v in db.query(Embedding.entity_id, Embedding.vector)
        .filter(Embedding.entity_type == entity_type, Embedding.model == model)
    }
    scored = [(eid, cosine(query_vec, vec) or 0.0) for eid, vec in vectors.items()]
    return sorted(scored, key=lambda x: x[1], reverse=True)[:limit]
