"""Explainable candidate-to-job scoring.

Pure functions over whitelisted facts (no database, no personal attributes), so the
same inputs always give the same result and every point of the score is traceable:

    result = score_match(candidate_facts, job_facts, graph, weights, semantic_similarity)
    result.score       -> 0-100
    result.factors     -> each factor's score, weight, and a plain-language reason

Factors without data are left out (and the remaining weights renormalized) rather
than counted as zero, so incomplete profiles aren't silently penalized.
"""
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

from app.matching.ontology import SkillGraph

ENGINE_VERSION = "2.0"

# Platform defaults. Organizations can override these (matching/service.py).
DEFAULT_WEIGHTS: Dict[str, float] = {
    "skills": 0.35,
    "experience": 0.15,
    "semantic": 0.15,
    "title": 0.05,
    "location": 0.10,
    "work_mode": 0.05,
    "salary": 0.05,
    "education": 0.04,
    "industry": 0.03,
    "notice": 0.03,
}

FACTOR_LABELS = {
    "skills": "Skills",
    "experience": "Experience",
    "semantic": "Profile relevance",
    "title": "Job title",
    "location": "Location",
    "work_mode": "Work mode",
    "salary": "Salary",
    "education": "Education",
    "industry": "Industry",
    "notice": "Availability",
}


# ---------------------------------------------------------------------------
# Inputs: only what the match is allowed to consider
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CandidateFacts:
    """Professional facts only. Deliberately excludes name, photo, age, gender, contact details."""
    skills: Tuple[str, ...]
    certifications: Tuple[str, ...]
    experience_years: float
    titles: Tuple[str, ...]  # headline + past job titles
    location: str
    preferred_locations: Tuple[str, ...]
    remote_preference: str
    expected_salary: Optional[int]
    education_levels: Tuple[str, ...]
    industry: str
    notice_period_days: Optional[int]


@dataclass(frozen=True)
class JobFacts:
    required_skills: Tuple[str, ...]
    preferred_skills: Tuple[str, ...]
    min_experience_years: float
    max_experience_years: Optional[float]
    title: str
    location: str
    workplace_type: str
    salary_min: Optional[int]
    salary_max: Optional[int]
    required_education: str
    industry: str


@dataclass
class FactorScore:
    key: str
    label: str
    score: Optional[float]  # 0-1, None when not applicable
    weight: float           # share of the total after renormalization (0-1)
    detail: str

    @property
    def applicable(self) -> bool:
        return self.score is not None


@dataclass
class SkillEvidence:
    skill: str               # the job's skill
    importance: str          # required | preferred
    score: float             # 0-1
    kind: str                # exact | synonym | parent | related | transferable | none
    via: Optional[str] = None


@dataclass
class MatchResult:
    score: int
    fit_level: str
    factors: List[FactorScore]
    skills: List[SkillEvidence] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    explanation: str = ""

    @property
    def matching_skills(self) -> List[dict]:
        return [asdict(s) for s in self.skills if s.score > 0]

    @property
    def missing_skills(self) -> List[dict]:
        return [{"skill": s.skill, "importance": s.importance} for s in self.skills if s.score == 0]


# ---------------------------------------------------------------------------
# Factors
# ---------------------------------------------------------------------------
_STOP = {"and", "of", "the", "for", "a", "an", "in", "to", "with", "&", "-", "/", "senior", "junior", "lead",
         "staff", "principal", "sr", "jr", "ii", "iii", "i", "head"}
_EDU_RANKS = [("phd", 4), ("doctor", 4), ("master", 3), ("m.s", 3), ("msc", 3), ("mba", 3), ("m.tech", 3),
              ("bachelor", 2), ("b.s", 2), ("bsc", 2), ("b.tech", 2), ("b.e", 2), ("associate", 1), ("diploma", 1),
              ("self-taught", 0), ("high school", 0)]


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9+#.]+", (text or "").lower()) if w not in _STOP}


def _edu_rank(text: str) -> Optional[int]:
    t = (text or "").lower()
    if not t or t in {"any", "none", "not required"}:
        return None
    for key, rank in _EDU_RANKS:
        if key in t:
            return rank
    return None


def _city(location: str) -> str:
    return (location or "").split(",")[0].strip().lower()


def _country(location: str) -> str:
    parts = [p.strip().lower() for p in (location or "").split(",") if p.strip()]
    return parts[-1] if len(parts) > 1 else ""


def skills_factor(c: CandidateFacts, j: JobFacts, graph: SkillGraph) -> Tuple[Optional[float], str, List[SkillEvidence]]:
    have = graph.canonical_set(c.skills)
    # canonical skill -> how the candidate actually wrote it (to show "k8s" as a synonym of Kubernetes)
    written = {}
    for raw in c.skills:
        for canonical in graph.canonical(raw):
            written.setdefault(canonical.lower(), raw)
    for cert in c.certifications:  # "AWS Solutions Architect" is evidence of AWS
        for skill in graph.mentions(cert):
            have.add(skill.lower())
            written.setdefault(skill.lower(), cert)

    evidence: List[SkillEvidence] = []
    for importance, wanted in (("required", j.required_skills), ("preferred", j.preferred_skills)):
        for skill in wanted:
            e = graph.best_evidence(have, skill)
            kind, via = e.kind, e.via
            if kind == "exact":
                via = written.get((e.via or "").lower(), e.via)
                if via and via.lower() != skill.lower():
                    kind = "synonym"
            evidence.append(SkillEvidence(skill=skill, importance=importance, score=e.score, kind=kind, via=via))

    req = [e.score for e in evidence if e.importance == "required"]
    pref = [e.score for e in evidence if e.importance == "preferred"]
    if not req and not pref:
        return None, "The job lists no skills", evidence
    parts = []
    if req:
        parts.append((0.75, sum(req) / len(req)))
    if pref:
        parts.append((0.25, sum(pref) / len(pref)))
    score = sum(w * s for w, s in parts) / sum(w for w, _ in parts)

    full = sum(1 for e in evidence if e.importance == "required" and e.score >= 0.999)
    partial = sum(1 for e in evidence if e.importance == "required" and 0 < e.score < 0.999)
    detail = f"Has {full} of {len(req)} required skills" if req else "No required skills listed"
    if partial:
        detail += f", plus related experience for {partial} more"
    if pref:
        detail += f"; {sum(1 for s in pref if s > 0)} of {len(pref)} preferred"
    return score, detail, evidence


def experience_factor(c: CandidateFacts, j: JobFacts) -> Tuple[Optional[float], str]:
    years, low, high = c.experience_years or 0.0, j.min_experience_years or 0.0, j.max_experience_years
    wanted = f"{low:g}-{high:g}" if high is not None else f"{low:g}+"
    if years < low:
        score = years / low if low else 1.0
        return max(0.0, score), f"{years:g} years vs {wanted} required ({low - years:g} below)"
    if high is not None and years > high:
        return 0.85, f"{years:g} years vs {wanted} wanted (more senior than the range)"
    return 1.0, f"{years:g} years, within the {wanted} years asked for"


def semantic_factor(similarity: Optional[float]) -> Tuple[Optional[float], str]:
    if similarity is None:
        return None, "No profile text to compare yet"
    score = min(1.0, max(0.0, (similarity - 0.35) / 0.5))
    level = "closely" if score >= 0.75 else "partly" if score >= 0.4 else "loosely"
    return score, f"Profile and job description are {level} related in meaning"


def title_factor(c: CandidateFacts, j: JobFacts) -> Tuple[Optional[float], str]:
    target = _words(j.title)
    if not target or not any(c.titles):
        return None, "No current title to compare"
    best, best_title = 0.0, ""
    for t in c.titles:
        overlap = len(target & _words(t)) / len(target)
        if overlap > best:
            best, best_title = overlap, t
    if best == 0:
        return 0.0, "No past title resembles this role"
    return best, f'Has held a similar title: "{best_title}"'


def location_factor(c: CandidateFacts, j: JobFacts) -> Tuple[Optional[float], str]:
    workplace = (j.workplace_type or "").lower()
    if workplace == "remote":
        return 1.0, "Remote role"
    places = [c.location, *c.preferred_locations]
    job_city, job_country = _city(j.location), _country(j.location)
    if job_city and any(job_city in _city(p) or (_city(p) and _city(p) in job_city) for p in places if p):
        return 1.0, f"Based in or open to {j.location}"
    if job_country and any(_country(p) == job_country for p in places if p):
        return 0.6, f"Same country as {j.location}; would need to relocate"
    if not any(places):
        return None, "Candidate location not set"
    return 0.3, f"Located in {c.location or 'another area'}; role is in {j.location}"


_MODE_FIT = {
    ("remote", "hybrid"): 0.5, ("remote", "onsite"): 0.2,
    ("hybrid", "remote"): 0.9, ("hybrid", "onsite"): 0.6,
    ("onsite", "remote"): 0.8, ("onsite", "hybrid"): 0.9,
}


def work_mode_factor(c: CandidateFacts, j: JobFacts) -> Tuple[Optional[float], str]:
    pref, mode = (c.remote_preference or "").lower(), (j.workplace_type or "").lower()
    if not pref or not mode:
        return None, "Work mode preference not set"
    if pref == "flexible" or pref == mode:
        return 1.0, f"Prefers {c.remote_preference}; role is {j.workplace_type}"
    return _MODE_FIT.get((pref, mode), 0.5), f"Prefers {c.remote_preference}; role is {j.workplace_type}"


def salary_factor(c: CandidateFacts, j: JobFacts) -> Tuple[Optional[float], str]:
    expected, top = c.expected_salary or 0, j.salary_max or 0
    if not expected or not top:
        return None, "Salary expectation or budget not provided"
    if expected <= top:
        return 1.0, "Expectation is within the budgeted range"
    over = (expected - top) / top
    return max(0.0, 1 - 2 * over), f"Expectation is {over:.0%} above the top of the range"


def education_factor(c: CandidateFacts, j: JobFacts) -> Tuple[Optional[float], str]:
    required = _edu_rank(j.required_education)
    if required is None:
        return None, "No education requirement"
    ranks = [r for r in (_edu_rank(e) for e in c.education_levels) if r is not None]
    if not ranks:
        return None, "Education not provided"
    have = max(ranks)
    if have >= required:
        return 1.0, f"Meets the {j.required_education} requirement"
    return (0.6 if required - have == 1 else 0.3), f"Below the {j.required_education} requirement"


def industry_factor(c: CandidateFacts, j: JobFacts) -> Tuple[Optional[float], str]:
    if not c.industry or not j.industry:
        return None, "Industry not provided"
    a, b = c.industry.lower(), j.industry.lower()
    if a in b or b in a:
        return 1.0, f"Experience in {j.industry}"
    return 0.5, f"Background in {c.industry}; role is in {j.industry}"


def notice_factor(c: CandidateFacts) -> Tuple[Optional[float], str]:
    days = c.notice_period_days
    if days is None:
        return None, "Notice period not provided"
    score = 1.0 if days <= 30 else 0.8 if days <= 60 else 0.6 if days <= 90 else 0.4
    return score, "Available immediately" if days == 0 else f"{days} days notice"


# ---------------------------------------------------------------------------
# Combining
# ---------------------------------------------------------------------------
def fit_level(score: int) -> str:
    return "Strong fit" if score >= 80 else "Good fit" if score >= 65 else "Partial fit" if score >= 50 else "Low fit"


def score_match(
    c: CandidateFacts,
    j: JobFacts,
    graph: SkillGraph,
    weights: Optional[Dict[str, float]] = None,
    semantic_similarity: Optional[float] = None,
) -> MatchResult:
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    skill_score, skill_detail, evidence = skills_factor(c, j, graph)
    raw = {
        "skills": (skill_score, skill_detail),
        "experience": experience_factor(c, j),
        "semantic": semantic_factor(semantic_similarity),
        "title": title_factor(c, j),
        "location": location_factor(c, j),
        "work_mode": work_mode_factor(c, j),
        "salary": salary_factor(c, j),
        "education": education_factor(c, j),
        "industry": industry_factor(c, j),
        "notice": notice_factor(c),
    }
    used = {k: weights[k] for k, (s, _) in raw.items() if s is not None and weights.get(k, 0) > 0}
    total_weight = sum(used.values()) or 1.0
    factors = [
        FactorScore(key=k, label=FACTOR_LABELS[k], score=s, weight=used.get(k, 0.0) / total_weight, detail=d)
        for k, (s, d) in raw.items()
    ]
    score = round(100 * sum(f.score * f.weight for f in factors if f.applicable and f.weight > 0))

    ranked = sorted((f for f in factors if f.applicable and f.weight > 0), key=lambda f: f.weight * (f.score or 0), reverse=True)
    strengths = [f"{f.label}: {f.detail}" for f in ranked if (f.score or 0) >= 0.85][:4]
    missing_required = [e.skill for e in evidence if e.importance == "required" and e.score == 0]
    gaps = []
    if missing_required:
        gaps.append(f"Missing required skills: {', '.join(missing_required)}")
    gaps += [f"{f.label}: {f.detail}" for f in sorted(factors, key=lambda f: f.weight, reverse=True)
             if f.applicable and f.weight > 0 and (f.score or 0) <= 0.5 and f.key != "skills"][:3]

    level = fit_level(score)
    top = ", ".join(f.label.lower() for f in ranked[:2]) or "the available information"
    explanation = f"{score}% match ({level.lower()}) based on {len(used)} factors. Strongest: {top}."
    if gaps:
        explanation += f" Main gap: {gaps[0][0].lower() + gaps[0][1:]}."
    return MatchResult(score=score, fit_level=level, factors=factors, skills=evidence,
                       strengths=strengths, gaps=gaps, explanation=explanation)
