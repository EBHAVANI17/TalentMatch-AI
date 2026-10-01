"""Deterministic, offline implementations of the AI features.

Used when no AI provider is configured or available. They are honest about their
limits (pattern-based), and their output always goes to a review step.
Contact details are ALWAYS extracted here, locally, never by an AI model.
"""
import re
from datetime import date
from typing import List, Optional, Tuple

from app.ai.schemas import (
    CertificationDraft, ContactInfo, EducationDraft, ExperienceDraft, JobAnalysis, JobDraft, LanguageDraft, ResumeDraft,
)
from app.matching.ontology import SkillGraph

# ---------------------------------------------------------------------------
# Shared patterns
# ---------------------------------------------------------------------------
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\w)(\+?\d[\d\s().-]{7,}\d)(?!\w)")
_URL = re.compile(r"(?:https?://)?(?:www\.)?([a-z0-9-]+\.[a-z.]{2,}(?:/[^\s|,]*)?)", re.IGNORECASE)
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE = r"(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{4}|\d{1,2}/\d{4}|\d{4})"
_RANGE = re.compile(rf"({_DATE})\s*(?:-|–|—|to)\s*({_DATE}|present|current|now|today)", re.IGNORECASE)
_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years|yrs)", re.IGNORECASE)
_YEAR_RANGE = re.compile(r"(\d+)\s*(?:-|–|to)\s*(\d+)\s*(?:years|yrs)", re.IGNORECASE)
_SECTIONS = {
    "summary": ["summary", "profile", "about me", "about", "objective", "professional summary"],
    "experience": ["experience", "work experience", "professional experience", "employment", "employment history", "work history"],
    "education": ["education", "academics", "academic background", "qualifications"],
    "skills": ["skills", "technical skills", "core skills", "key skills", "technologies", "tech stack"],
    "certifications": ["certifications", "certification", "certificates", "licenses"],
    "projects": ["projects", "personal projects", "selected projects"],
    "languages": ["languages", "language"],
}
_ROLE_WORDS = ("engineer", "developer", "manager", "designer", "analyst", "scientist", "architect", "consultant",
               "specialist", "lead", "director", "administrator", "recruiter", "accountant", "executive", "intern", "officer")
_DEGREES = [("phd", "PhD"), ("ph.d", "PhD"), ("doctor", "PhD"), ("mba", "MBA"), ("m.tech", "M.Tech"), ("mtech", "M.Tech"),
            ("m.s.", "M.S."), ("msc", "M.Sc"), ("m.sc", "M.Sc"), ("master", "Master's"), ("m.e.", "M.E."),
            ("b.tech", "B.Tech"), ("btech", "B.Tech"), ("b.e.", "B.E."), ("b.sc", "B.Sc"), ("bsc", "B.Sc"), ("b.s.", "B.S."),
            ("bca", "BCA"), ("bachelor", "Bachelor's"), ("associate", "Associate"), ("diploma", "Diploma")]
_LANGUAGES = ["English", "Hindi", "Tamil", "Telugu", "Kannada", "Malayalam", "Marathi", "Bengali", "Gujarati", "Punjabi", "Urdu",
              "Spanish", "French", "German", "Mandarin", "Chinese", "Japanese", "Korean", "Arabic", "Portuguese", "Russian", "Italian"]


def _lines(text: str) -> List[str]:
    return [l.strip(" \t•·*-–—▪●") for l in text.splitlines() if l.strip(" \t•·*-–—▪●")]


def _heading(line: str) -> Optional[str]:
    key = line.lower().strip(" :").strip()
    if len(key) > 40:
        return None
    for section, names in _SECTIONS.items():
        if key in names:
            return section
    return None


def _sections(lines: List[str]) -> dict:
    out = {"_top": []}
    current = "_top"
    for line in lines:
        name = _heading(line)
        if name:
            current = name
            out.setdefault(current, [])
        else:
            out.setdefault(current, []).append(line)
    return out


def _to_month(token: str) -> Optional[Tuple[int, int]]:
    token = token.strip().lower()
    if token in {"present", "current", "now", "today"}:
        return date.today().year, date.today().month
    m = re.match(r"([a-z]+)\.?\s+(\d{4})", token)
    if m and m.group(1)[:3] in _MONTHS:
        return int(m.group(2)), _MONTHS[m.group(1)[:3]]
    m = re.match(r"(\d{1,2})/(\d{4})", token)
    if m:
        return int(m.group(2)), max(1, min(12, int(m.group(1))))
    m = re.match(r"(\d{4})", token)
    return (int(m.group(1)), 1) if m else None


def _fmt(ym: Optional[Tuple[int, int]]) -> str:
    return f"{ym[0]:04d}-{ym[1]:02d}" if ym else ""


# ---------------------------------------------------------------------------
# Contact details (local only)
# ---------------------------------------------------------------------------
def extract_contact(text: str) -> ContactInfo:
    lines = _lines(text)[:15]
    contact = ContactInfo()
    if m := _EMAIL.search(text):
        contact.email = m.group(0)
    for m in _PHONE.finditer(text):
        if sum(c.isdigit() for c in m.group(1)) >= 9:
            contact.phone = m.group(1).strip()
            break
    for m in _URL.finditer(_EMAIL.sub(" ", text)):  # emails removed so "name.surname@" isn't read as a site
        url = m.group(0)
        lower = url.lower()
        if "@" in url or lower.endswith((".pdf", ".docx")):
            continue
        full = url if url.startswith("http") else f"https://{url}"
        if "linkedin.com" in lower and not contact.linkedin_url:
            contact.linkedin_url = full
        elif "github.com" in lower and not contact.github_url:
            contact.github_url = full
        elif not contact.portfolio_url and not _EMAIL.search(url) and "." in lower.split("/")[0] and any(
                k in lower for k in (".dev", ".io", ".me", "portfolio", ".site")):
            contact.portfolio_url = full
    for line in lines:
        words = line.split()
        if (2 <= len(words) <= 4 and not any(c.isdigit() for c in line) and "@" not in line
                and all(w[:1].isupper() for w in words) and not any(r in line.lower() for r in _ROLE_WORDS)
                and not _heading(line)):
            contact.name = line
            break
    for line in lines:
        for part in re.split(r"\s*[|·•]\s*", line):
            if (re.fullmatch(r"[A-Z][A-Za-z .'-]+,\s*[A-Z][A-Za-z .'-]+", part.strip()) and "@" not in part
                    and part.strip() != contact.name):
                contact.location = part.strip()
                break
        if contact.location:
            break
    return contact


# ---------------------------------------------------------------------------
# Resume parsing
# ---------------------------------------------------------------------------
def _experience(lines: List[str]) -> List[ExperienceDraft]:
    entries: List[ExperienceDraft] = []
    for i, line in enumerate(lines):
        m = _RANGE.search(line)
        if not m:
            continue
        start, end = _to_month(m.group(1)), _to_month(m.group(2))
        header = (line[:m.start()] + line[m.end():]).strip(" ()|,-–—")
        if len(header) < 3 and i > 0:
            header = lines[i - 1]
        title, company = header, ""
        for sep in (" at ", " @ ", " - ", " – ", " — ", " | ", ", "):
            if sep in header:
                a, b = header.split(sep, 1)
                title, company = a.strip(" ()"), b.strip(" ()")
                break
        if company and any(r in company.lower() for r in _ROLE_WORDS) and not any(r in title.lower() for r in _ROLE_WORDS):
            title, company = company, title
        details = []
        for nxt in lines[i + 1:i + 8]:
            if _RANGE.search(nxt) or _heading(nxt):
                break
            details.append(nxt)
        is_current = m.group(2).lower() in {"present", "current", "now", "today"}
        entries.append(ExperienceDraft(
            job_title=title[:128], company_name=company[:128], start_date=_fmt(start),
            end_date="" if is_current else _fmt(end), is_current=is_current,
            achievements=[d for d in details if re.search(r"\d", d)][:5],
            description=" ".join(d for d in details if not re.search(r"\d", d))[:600],
        ))
    return entries


def _total_years(entries: List[ExperienceDraft], text: str) -> Optional[float]:
    spans = []
    for e in entries:
        if e.start_date:
            s = (int(e.start_date[:4]), int(e.start_date[5:7]))
            end = (date.today().year, date.today().month) if e.is_current or not e.end_date else (int(e.end_date[:4]), int(e.end_date[5:7]))
            spans.append((s[0] * 12 + s[1], end[0] * 12 + end[1]))
    if spans:
        spans.sort()
        merged, total = [list(spans[0])], 0
        for a, b in spans[1:]:
            if a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        total = sum(max(0, b - a) for a, b in merged)
        return round(total / 12, 1)
    m = _YEARS.search(text)
    return float(m.group(1)) if m else None


def _education(lines: List[str]) -> List[EducationDraft]:
    out: List[EducationDraft] = []
    for line in lines:
        low = line.lower()
        degree = next((label for key, label in _DEGREES if key in low), None)
        if not degree:
            continue
        year = re.findall(r"\b(19[5-9]\d|20\d{2})\b", line)
        parts = [p.strip() for p in re.split(r"\s+(?:-|–|—|\||from|at|,)\s+|,\s*", line) if p.strip()]
        institution = next((p for p in parts if re.search(r"universit|institute|college|school|iit|nit|academy", p, re.I)), "")
        field = ""
        if m := re.search(r"\bin\s+([A-Za-z &]+?)(?:\s+(?:from|at)\b|[,|(-]|$)", line):
            field = m.group(1).strip()
        out.append(EducationDraft(institution=institution, degree=degree, field_of_study=field,
                                  graduation_year=int(year[-1]) if year else None))
    return out


def parse_resume(text: str, graph: SkillGraph, redacted_text: Optional[str] = None) -> ResumeDraft:
    """Pattern-based resume parsing. `redacted_text` (if given) is used for everything except contacts."""
    body = redacted_text or text
    lines = _lines(body)
    sections = _sections(lines)

    skills: List[str] = []
    for line in sections.get("skills", []):
        for item in re.split(r"[,;|/]|\s{2,}", line.split(":", 1)[-1]):
            item = item.strip(" .")
            if 1 < len(item) <= 40:
                skills.extend(graph.canonical(item))
    skills.extend(graph.mentions(body))
    skills = list(dict.fromkeys(s for s in skills if s))

    experience = _experience(sections.get("experience") or lines)
    education = _education(sections.get("education") or lines)
    certs = [CertificationDraft(name=l[:160]) for l in sections.get("certifications", [])][:15]
    certs += [CertificationDraft(name=l[:160]) for l in lines if re.search(r"\bcertified\b|\bcertification\b", l, re.I)
              and l not in {c.name for c in certs} and "certification" != l.lower()][:5]
    languages = [LanguageDraft(language=lang) for lang in _LANGUAGES
                 if re.search(rf"\b{lang}\b", " ".join(sections.get("languages", [])) or "", re.I)]

    top = [l for l in sections.get("_top", []) if "[" not in l and "@" not in l][:6]
    headline = next((l for l in top if any(r in l.lower() for r in _ROLE_WORDS) and len(l) < 120), "")
    if not headline and experience:
        headline = experience[0].job_title
    summary = " ".join(sections.get("summary", []))[:1500]

    return ResumeDraft(
        headline=headline, summary=summary, total_experience_years=_total_years(experience, body),
        skills=skills[:60], work_experience=experience[:15], education=education[:6],
        certifications=certs[:15], languages=languages,
    )


# ---------------------------------------------------------------------------
# Job description analysis
# ---------------------------------------------------------------------------
_PREFERRED_HEADINGS = re.compile(r"nice to have|preferred|bonus|good to have|plus|desirable", re.I)
_REQUIRED_HEADINGS = re.compile(r"requirements|required|must have|qualifications|what you.?ll need|you have|skills", re.I)
_RESP_HEADINGS = re.compile(r"responsibilit|what you.?ll do|the role|your impact|duties", re.I)


def _salary(text: str) -> Tuple[Optional[int], Optional[int]]:
    t = text.lower().replace(",", "")
    lpa = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?)", t)
    if lpa:
        return int(float(lpa.group(1)) * 100_000), int(float(lpa.group(2)) * 100_000)
    m = re.search(r"[$₹€£]?\s*(\d+(?:\.\d+)?)\s*(k)?\s*(?:-|–|to)\s*[$₹€£]?\s*(\d+(?:\.\d+)?)\s*(k)?", t)
    if m and re.search(r"salary|compensation|ctc|pay|[$₹€£]|\bk\b", t):
        lo, hi = float(m.group(1)), float(m.group(3))
        if m.group(2) or m.group(4):
            lo, hi = lo * 1000, hi * 1000
        if hi >= 1000 and lo <= hi:
            return int(lo), int(hi)
    return None, None


def _workplace(text: str) -> str:
    t = text.lower()
    if "hybrid" in t:
        return "Hybrid"
    if re.search(r"\bremote\b", t):
        return "Remote"
    if re.search(r"on-?site|in[- ]office|office-based", t):
        return "Onsite"
    return ""


def _employment_type(text: str) -> str:
    t = text.lower()
    for key, label in (("intern", "Internship"), ("contract", "Contract"), ("part-time", "Part-time"),
                       ("part time", "Part-time"), ("temporary", "Temporary"), ("full-time", "Full-time"), ("full time", "Full-time")):
        if key in t:
            return label
    return ""


def _seniority(text: str) -> str:
    t = text.lower()
    for word in ("principal", "staff", "lead", "senior", "mid", "junior", "intern"):
        if re.search(rf"\b{word}\b", t):
            return word.title()
    return ""


def _education_requirement(text: str) -> str:
    t = text.lower()
    for key, label in (("phd", "PhD"), ("master", "Master's"), ("bachelor", "Bachelor's"), ("b.tech", "Bachelor's"),
                       ("b.e.", "Bachelor's"), ("degree", "Bachelor's")):
        if key in t:
            return label
    return ""


def analyze_job(text: str, graph: SkillGraph) -> JobAnalysis:
    lines = _lines(text)
    required: List[str] = []
    preferred: List[str] = []
    responsibilities: List[str] = []
    mode = "required"
    for line in lines:
        # "Nice to have: dbt, Kafka" is a heading and content on one line
        head, _, rest = line.partition(":") if ":" in line[:40] else (line, "", "")
        is_heading = bool(rest.strip()) or (len(line) < 60 and line.endswith(":")) or (len(line.split()) <= 5 and not line.endswith("."))
        new_mode = None
        if is_heading and _PREFERRED_HEADINGS.search(head):
            new_mode = "preferred"
        elif is_heading and _RESP_HEADINGS.search(head):
            new_mode = "responsibilities"
        elif is_heading and _REQUIRED_HEADINGS.search(head):
            new_mode = "required"
        if new_mode:
            mode = new_mode
            if not rest.strip():
                continue
            line = rest.strip()
        found = graph.mentions(line)
        if mode == "responsibilities":
            if len(line) > 15:
                responsibilities.append(line[:300])
            required.extend(found)
        elif mode == "preferred" or _PREFERRED_HEADINGS.search(line):
            preferred.extend(found)
        else:
            required.extend(found)
    required = list(dict.fromkeys(required))
    preferred = [s for s in dict.fromkeys(preferred) if s not in required]

    lo = hi = None
    if m := _YEAR_RANGE.search(text):
        lo, hi = float(m.group(1)), float(m.group(2))
    elif m := _YEARS.search(text):
        lo = float(m.group(1))
    salary_min, salary_max = _salary(text)
    location = ""
    if m := re.search(r"location\s*:\s*([^\n|]+)", text, re.I):
        location = re.sub(r"\s*\([^)]*\)", "", m.group(1)).strip()
    elif m := re.search(r"\b(?:based in|located in|office in)\s+([A-Z][A-Za-z .-]+?)(?:[,.\n]|$)", text):
        location = m.group(1).strip()
    title = ""
    if m := re.search(r"(?:job title|title|position|role)\s*:\s*([^\n]+)", text, re.I):
        title = m.group(1).strip()
    elif lines and len(lines[0]) <= 80:
        title = lines[0]
    certifications = [l[:120] for l in lines if re.search(r"certif", l, re.I)][:5]
    return JobAnalysis(
        title=title, seniority=_seniority(title or text[:200]), employment_type=_employment_type(text),
        workplace_type=_workplace(text), location=location, required_skills=required, preferred_skills=preferred,
        min_experience_years=lo, max_experience_years=hi, required_education=_education_requirement(text),
        certifications=certifications, salary_min=salary_min, salary_max=salary_max, responsibilities=responsibilities[:12],
    )


# ---------------------------------------------------------------------------
# Job description generation from a brief
# ---------------------------------------------------------------------------
_FAMILIES = [
    ("Data & AI", ("machine learning", "ml ", "ai ", "llm", "data scien", "nlp", "computer vision", "deep learning"), [
        "Design, train and evaluate models that solve real product problems",
        "Build reliable data and model pipelines from experimentation to production",
        "Monitor model quality in production and drive improvements",
    ]),
    ("Data", ("data engineer", "analytics", "etl", "data platform", "bi "), [
        "Build and maintain reliable data pipelines and models",
        "Partner with analysts and product teams on trustworthy metrics",
        "Improve data quality, observability and cost",
    ]),
    ("Infrastructure", ("devops", "sre", "site reliability", "platform", "cloud", "infrastructure"), [
        "Build and operate scalable, secure cloud infrastructure",
        "Automate deployments, monitoring and incident response",
        "Improve reliability, performance and cost across services",
    ]),
    ("Engineering", ("frontend", "front-end", "ui engineer", "react", "web developer"), [
        "Build accessible, fast and well-tested user interfaces",
        "Work with design and product to ship features end to end",
        "Improve front-end performance, tooling and component libraries",
    ]),
    ("Engineering", ("backend", "back-end", "api", "server", "full stack", "full-stack", "software engineer", "developer"), [
        "Design, build and maintain reliable services and APIs",
        "Write well-tested, maintainable code and review others' work",
        "Improve performance, scalability and observability of production systems",
    ]),
    ("Design", ("designer", "ux", "ui/ux", "product design"), [
        "Design intuitive, accessible experiences from research to polished UI",
        "Run user research and turn insights into design decisions",
        "Maintain and evolve the design system with engineering",
    ]),
    ("Product", ("product manager", "product owner"), [
        "Own the roadmap for your area based on customer and business outcomes",
        "Work with engineering and design to deliver and measure features",
        "Turn customer research and data into clear priorities",
    ]),
    ("Sales", ("sales", "account executive", "business development"), [
        "Build and manage a healthy pipeline of qualified opportunities",
        "Run discovery, demos and negotiations through to close",
        "Work with customer success to grow long-term accounts",
    ]),
]


def generate_job(brief: str, graph: SkillGraph) -> JobDraft:
    text = " ".join(brief.split())
    lower = f" {text.lower()} "
    title = re.split(r"[,(;]|\bwith\b|\busing\b", text, maxsplit=1)[0].strip(" .") or "New role"
    title = title[:1].upper() + title[1:]
    department, responsibilities = "Engineering", [
        "Deliver high-quality work in your area of ownership",
        "Collaborate across teams to plan, build and improve",
        "Share knowledge and help raise the bar for the team",
    ]
    for family, keys, resp in _FAMILIES:
        if any(k in lower for k in keys):
            department, responsibilities = family, resp
            break

    skills = graph.mentions(text)
    lo = hi = None
    if m := _YEAR_RANGE.search(text):
        lo, hi = float(m.group(1)), float(m.group(2))
    elif m := _YEARS.search(text):
        lo = float(m.group(1))
    seniority = _seniority(title)
    if lo is None:
        lo = {"Intern": 0, "Junior": 0, "Mid": 2, "Senior": 5, "Lead": 6, "Staff": 8, "Principal": 10}.get(seniority, 2)

    # Suggest preferred skills from the ontology: strongly related to what's required, not already required.
    required_lower = {s.lower() for s in skills}
    related: List[Tuple[float, str]] = []
    for (have, wanted), (weight, kind) in graph._relations.items():  # noqa: SLF001 - ontology is ours
        # "transferable" means an alternative (AWS vs GCP), not something to ask for in addition
        if have in required_lower and wanted not in required_lower and weight >= 0.5 and kind != "transferable":
            related.append((weight, graph.display(wanted)))
    preferred = list(dict.fromkeys(name for _, name in sorted(related, reverse=True)))[:4]

    location = ""
    if m := re.search(r"\b(?:in|based in)\s+([A-Z][A-Za-z .-]+?)(?=[,.;]|$|\s+(?:with|for|and)\b)", text):
        if not graph.mentions(m.group(1)):
            location = m.group(1).strip()
    workplace = _workplace(text) or "Remote"
    skill_list = ", ".join(skills[:5]) if skills else "the skills this role needs"
    description = (
        f"We're looking for a {title} to join our {department.lower()} team"
        + (f" in {location}" if location else "") + ". "
        + f"You'll work with {skill_list} to build and improve the products our customers rely on. "
        "This description was drafted from a short brief; edit it to describe the team, the problems "
        "they're solving and what success looks like in the first months."
    )
    criteria = [f"Practical depth in {s}" for s in skills[:4]] + [
        "Problem solving: breaks down ambiguous problems and explains trade-offs",
        "Collaboration and communication with technical and non-technical colleagues",
    ]
    questions = [f"Tell us about a recent project where you used {s}. What was your role and the outcome?" for s in skills[:3]]
    questions.append(f"What interests you about this {title} role?")
    return JobDraft(
        title=title, department=department, seniority=seniority, employment_type=_employment_type(text) or "Full-time",
        workplace_type=workplace, location=location, description=description, responsibilities=responsibilities,
        required_skills=skills, preferred_skills=preferred, min_experience_years=lo, max_experience_years=hi,
        required_education="Bachelor's", interview_criteria=criteria, screening_questions=questions,
    )
