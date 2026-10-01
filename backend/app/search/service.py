"""Global search: natural-language query understanding + hybrid keyword/semantic ranking.

Every result set is restricted to what the caller may see (tenancy) before ranking.
"""
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.tenancy import TenantContext, scope_candidates, scope_jobs
from app.matching import embeddings
from app.matching.ontology import SkillGraph, get_skill_graph
from app.models.db_models import CandidateProfile, Job, Organization, SkillAlias, SkillTaxonomy, User
from app.services import candidate_service

RRF_K = 60  # reciprocal rank fusion constant
_SENIORITY = {"intern": (0, 1), "junior": (0, 2), "entry": (0, 2), "mid": (3, None), "senior": (5, None),
              "lead": (6, None), "staff": (8, None), "principal": (8, None)}
_STOPWORDS = {"find", "show", "me", "with", "who", "have", "has", "and", "or", "the", "a", "an", "in", "of", "for",
              "strong", "experience", "experienced", "engineers", "engineer", "developers", "developer", "people",
              "candidates", "candidate", "that", "built", "building", "years", "year", "yrs", "plus", "based",
              "located", "near", "from", "good", "great", "deep", "solid", "remote", "hybrid", "onsite"}


@dataclass
class ParsedQuery:
    text: str
    skills: List[str] = field(default_factory=list)
    min_experience: Optional[float] = None
    max_experience: Optional[float] = None
    location: Optional[str] = None
    remote_preference: Optional[str] = None
    keywords: List[str] = field(default_factory=list)


def parse_query(q: str, graph: SkillGraph) -> ParsedQuery:
    parsed = ParsedQuery(text=q.strip())
    lower = q.lower()

    years = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years|yrs|year)", lower)
    if years:
        parsed.min_experience = float(years.group(1))
    else:
        for word, (low, high) in _SENIORITY.items():
            if re.search(rf"\b{word}\b", lower):
                parsed.min_experience = float(low) if low else None
                parsed.max_experience = float(high) if high is not None else None
                break

    location = re.search(r"\b(?:in|based in|located in|near|from)\s+([A-Z][A-Za-z.\- ]+?)(?=\s+(?:with|who|and|for|that|having)\b|[,.;]|$)", q)
    if location and not graph.mentions(location.group(1)):
        parsed.location = location.group(1).strip()

    for mode, pattern in (("Remote", r"\bremote\b"), ("Hybrid", r"\bhybrid\b"), ("Onsite", r"\b(?:onsite|on-site|in-office)\b")):
        if re.search(pattern, lower):
            parsed.remote_preference = mode
            break

    parsed.skills = graph.mentions(q)
    skill_words = {w for s in parsed.skills for w in s.lower().split()}
    location_words = set((parsed.location or "").lower().split())
    parsed.keywords = [
        w for w in re.findall(r"[a-z0-9+#.]+", lower)
        if len(w) > 2 and w not in _STOPWORDS and w not in skill_words and w not in location_words and not w.isdigit()
    ]
    return parsed


def _rrf(*rankings: Sequence[str]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking):
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
    return scores


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------
def search_candidates(db: Session, ctx: TenantContext, parsed: ParsedQuery, limit: int) -> List[dict]:
    base = candidate_service.filter_candidates(
        scope_candidates(db.query(CandidateProfile), ctx),
        location=parsed.location, min_experience=parsed.min_experience, max_experience=parsed.max_experience,
        remote_preference=parsed.remote_preference,
    )
    pool: List[CandidateProfile] = base.all()
    if not pool:
        return []
    graph = get_skill_graph(db)
    by_id = {c.id: c for c in pool}

    # 1) semantic: meaning of the whole query
    semantic = embeddings.nearest(db, "candidate", embeddings.embed_query(parsed.text), list(by_id), limit=200)
    sim = dict(semantic)
    # 2) skills mentioned in the query (ontology-aware)
    wanted = [s.lower() for s in parsed.skills]
    skill_hits: Dict[str, List[str]] = {}
    for c in pool:
        have = graph.canonical_set(c.skills)
        hits = [graph.display(s) for s in wanted if graph.best_evidence(have, s).score >= 0.5]
        if hits:
            skill_hits[c.id] = hits
    by_skills = sorted(skill_hits, key=lambda cid: len(skill_hits[cid]), reverse=True)
    # 3) plain keywords in name / headline / summary
    keyword_hits: Dict[str, int] = {}
    for c in pool:
        haystack = f"{c.user.full_name if c.user else ''} {c.title} {c.bio}".lower()
        n = sum(1 for k in parsed.keywords if k in haystack)
        if n:
            keyword_hits[c.id] = n
    by_keywords = sorted(keyword_hits, key=keyword_hits.get, reverse=True)

    fused = _rrf([cid for cid, _ in semantic], by_skills, by_keywords)
    ranked = sorted(fused, key=fused.get, reverse=True)[:limit]
    visible = candidate_service.contact_visible_ids(db, ctx, ranked)
    results = []
    for cid in ranked:
        reasons = []
        if skill_hits.get(cid):
            reasons.append("Skills: " + ", ".join(skill_hits[cid]))
        if sim.get(cid, 0) >= 0.5:
            reasons.append("Profile closely related to the search")
        if keyword_hits.get(cid):
            reasons.append("Matches search words")
        results.append({
            "candidate": candidate_service.to_summary(by_id[cid], cid in visible),
            "relevance": round(fused[cid] * RRF_K, 3),
            "reasons": reasons or ["Related profile"],
        })
    return results


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
def search_jobs(db: Session, ctx: Optional[TenantContext], parsed: ParsedQuery, limit: int) -> List[Job]:
    query = scope_jobs(db.query(Job), ctx).filter(Job.status != "Archived")
    if parsed.remote_preference:
        query = query.filter(Job.workplace_type == parsed.remote_preference)
    pool = query.all()
    if not pool:
        return []
    by_id = {j.id: j for j in pool}
    semantic = embeddings.nearest(db, "job", embeddings.embed_query(parsed.text), list(by_id), limit=100)
    terms = [*parsed.keywords, *(s.lower() for s in parsed.skills)] + ([parsed.location.lower()] if parsed.location else [])
    keyword_hits = {
        j.id: n for j in pool
        if (n := sum(1 for t in terms if t in f"{j.title} {j.department} {j.location} {j.required_skills_json} {j.description}".lower()))
    }
    fused = _rrf([jid for jid, sim in semantic if sim > 0.2], sorted(keyword_hits, key=keyword_hits.get, reverse=True))
    return [by_id[jid] for jid in sorted(fused, key=fused.get, reverse=True)[:limit]]


# ---------------------------------------------------------------------------
# Skills & organizations
# ---------------------------------------------------------------------------
def search_skills(db: Session, q: str, limit: int) -> List[dict]:
    like = f"%{q.strip()}%"
    found: Dict[str, SkillTaxonomy] = {s.id: s for s in db.query(SkillTaxonomy).filter(SkillTaxonomy.name.ilike(like)).limit(limit)}
    for alias in db.query(SkillAlias).filter(SkillAlias.alias.ilike(like.lower())).limit(limit):
        found.setdefault(alias.skill_id, alias.skill)
    skills = sorted(found.values(), key=lambda s: (not s.name.lower().startswith(q.strip().lower()), len(s.name)))[:limit]
    return [{"id": s.id, "name": s.name, "category": s.category} for s in skills]


def search_organizations(db: Session, ctx: TenantContext, q: str, limit: int) -> List[Organization]:
    if not ctx.is_super_admin:
        return []
    like = f"%{q.strip()}%"
    return db.query(Organization).filter(or_(Organization.name.ilike(like), Organization.domain.ilike(like))).limit(limit).all()


def interpreted(parsed: ParsedQuery) -> dict:
    data = asdict(parsed)
    data.pop("text")
    return {k: v for k, v in data.items() if v}
