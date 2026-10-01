"""Skill graph: canonical names, synonyms and related-skill credit, loaded from the database.

    graph = get_skill_graph(db)
    graph.canonical("k8s")                       -> ["Kubernetes"]
    graph.canonical("PostgreSQL & pgvector")     -> ["PostgreSQL", "pgvector"]
    graph.best_evidence({"TypeScript"}, "JavaScript") -> Evidence(score=0.9, via="TypeScript", kind="parent")
"""
import re
import threading
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.db_models import SkillAlias, SkillRelation, SkillTaxonomy

_SPLIT = re.compile(r"\s*(?:&|/|,|\+|\band\b)\s*", re.IGNORECASE)
_CACHE_SECONDS = 60


@dataclass(frozen=True)
class Evidence:
    score: float           # 1.0 exact/synonym, < 1 related skill
    via: Optional[str]     # the candidate's skill that provided the evidence
    kind: str              # exact | synonym | parent | related | transferable | none


NO_EVIDENCE = Evidence(0.0, None, "none")


class SkillGraph:
    def __init__(self, names: Dict[str, str], relations: Dict[Tuple[str, str], Tuple[float, str]]):
        self._names = names          # lower-case name or alias -> canonical name
        self._relations = relations  # (has, wanted) canonical -> (weight, kind)

    def _one(self, text: str) -> Optional[str]:
        key = " ".join(text.lower().split())
        return self._names.get(key) or self._names.get(key.rstrip("."))

    def canonical(self, name: str) -> List[str]:
        """Canonical skills a free-text skill refers to. Unknown skills keep their own name."""
        name = (name or "").strip()
        if not name:
            return []
        # Compound labels ("PostgreSQL & pgvector") count as their parts when the parts are known
        # skills, even if the compound itself is also in the catalog.
        parts = [p for p in _SPLIT.split(name) if p.strip()]
        if len(parts) > 1 and any(self._one(p) for p in parts):
            out: List[str] = []
            for part in parts:
                for c in self.canonical(part):
                    if c not in out:
                        out.append(c)
            return out
        return [self._one(name) or name]

    def canonical_set(self, names: Iterable[str]) -> Set[str]:
        out: Set[str] = set()
        for n in names:
            out.update(c.lower() for c in self.canonical(n))
        return out

    def display(self, lower_name: str) -> str:
        return self._names.get(lower_name, lower_name)

    def best_evidence(self, candidate_skills: Set[str], wanted: str) -> Evidence:
        """How well a candidate's (canonical, lower-case) skills cover one wanted skill."""
        targets = [c.lower() for c in self.canonical(wanted)]
        if not targets:
            return NO_EVIDENCE
        # A compound requirement ("PostgreSQL & pgvector") is covered as the average of its parts.
        parts = [self._evidence_one(candidate_skills, t) for t in targets]
        if len(parts) == 1:
            return parts[0]
        score = sum(p.score for p in parts) / len(parts)
        best = max(parts, key=lambda p: p.score)
        return Evidence(round(score, 3), best.via, best.kind if score > 0 else "none")

    def _evidence_one(self, candidate_skills: Set[str], target: str) -> Evidence:
        if target in candidate_skills:
            return Evidence(1.0, self.display(target), "exact")
        best = NO_EVIDENCE
        for have in candidate_skills:
            rel = self._relations.get((have, target))
            if rel and rel[0] > best.score:
                best = Evidence(rel[0], self.display(have), rel[1])
        return best

    def mentions(self, text: str) -> List[str]:
        """Catalog skills (and synonyms) mentioned in free text, as canonical names."""
        lowered = f" {re.sub(r'[^a-z0-9+#./ -]', ' ', text.lower())} "
        found: List[str] = []
        for key, canonical in self._names.items():
            if len(key) < 2:
                continue
            if f" {key} " in lowered and canonical not in found:
                found.append(canonical)
        return found


_lock = threading.Lock()
_cached: Optional[Tuple[float, SkillGraph]] = None


def load_skill_graph(db: Session) -> SkillGraph:
    skills = {s.id: s.name for s in db.query(SkillTaxonomy).all()}
    names: Dict[str, str] = {name.lower(): name for name in skills.values()}
    for alias in db.query(SkillAlias).all():
        if alias.skill_id in skills:
            names.setdefault(alias.alias.lower(), skills[alias.skill_id])
    relations: Dict[Tuple[str, str], Tuple[float, str]] = {}
    for r in db.query(SkillRelation).all():
        if r.skill_id in skills and r.related_skill_id in skills:
            relations[(skills[r.skill_id].lower(), skills[r.related_skill_id].lower())] = (float(r.weight), r.kind)
    return SkillGraph(names, relations)


def get_skill_graph(db: Session) -> SkillGraph:
    """Cached for a minute; call invalidate_skill_graph() after editing the ontology."""
    global _cached
    with _lock:
        if _cached and time.monotonic() - _cached[0] < _CACHE_SECONDS:
            return _cached[1]
    graph = load_skill_graph(db)
    with _lock:
        _cached = (time.monotonic(), graph)
    return graph


def invalidate_skill_graph() -> None:
    global _cached
    with _lock:
        _cached = None
