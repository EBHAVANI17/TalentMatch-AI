"""Deterministic copilot behaviour, used when no AI provider is configured or available.

The planner routes on keywords and the page the user is on; the answer is a plain
summary of the records found. Both are honest about being rule-based.
"""
import re
from typing import List, Optional

from app.copilot.records import RefBook
from app.copilot.schemas import CopilotAnswer, CopilotPlan, ToolCall

_INTERVIEWS = re.compile(r"\binterview", re.I)
_PIPELINE = re.compile(r"\b(pipeline|funnel|how many|stats|statistics|overview|hires?|hired|progress|metrics|summary)\b", re.I)
_JOBS = re.compile(r"\b(jobs?|openings?|requisitions?|roles?|positions?|vacanc)", re.I)
_MATCH = re.compile(r"\b(best|top|match|matches|matching|fit|rank|ranked|shortlist|shortlisted|strongest|recommend)", re.I)
_SEARCH = re.compile(r"\b(find|search|look for|looking for|who (?:has|knows|can)|candidates? with)\b", re.I)


def _first(refs: List[str], prefix: str) -> Optional[str]:
    return next((r for r in refs if r.startswith(prefix)), None)


def plan(question: str, mentioned: List[str], context_job: Optional[str], context_candidate: Optional[str]) -> CopilotPlan:
    """question is in reference form; mentioned are refs that appear in it."""
    job = _first(mentioned, "J") or context_job
    candidate = _first(mentioned, "C")
    calls: List[ToolCall] = []
    if _INTERVIEWS.search(question):
        calls.append(ToolCall(tool="upcoming_interviews"))
    elif _PIPELINE.search(question):
        calls.append(ToolCall(tool="pipeline_summary", args={"job": job} if job else {}))
    elif candidate:
        calls.append(ToolCall(tool="candidate_overview", args={"candidate": candidate}))
    elif _MATCH.search(question) and job and not _SEARCH.search(question):
        status = "shortlisted" if re.search(r"shortlisted", question, re.I) else "active"
        calls.append(ToolCall(tool="top_matches", args={"job": job, "status": status}))
    elif _JOBS.search(question) and not _SEARCH.search(question) and not re.search(r"candidates?", question, re.I):
        calls.append(ToolCall(tool="list_jobs"))
    elif context_candidate and not _SEARCH.search(question):
        calls.append(ToolCall(tool="candidate_overview", args={"candidate": context_candidate}))
    elif job and not _SEARCH.search(question) and len(question.split()) <= 6:
        calls.append(ToolCall(tool="top_matches", args={"job": job}))
    else:
        calls.append(ToolCall(tool="search_candidates", args={"query": question}))
    return CopilotPlan(calls=calls)


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _skills(facts: dict, key: str = "skills", n: int = 5) -> str:
    return ", ".join((facts.get(key) or [])[:n])


def answer(book: RefBook, tools_used: List[str]) -> CopilotAnswer:
    records = list(book.records.values())
    candidates = [r for r in records if r.kind == "candidate"]
    jobs = [r for r in records if r.kind == "job"]
    summaries = [r for r in records if r.kind == "summary"]
    parts: List[str] = []
    follow_ups: List[str] = []

    for s in summaries:
        f = s.facts
        if "interviews" in f:
            entries = f["interviews"]
            if not entries:
                parts.append(f"No interviews are scheduled in the next {f['window_days']} days.")
            else:
                lines = [f"- {e['scheduled_for']}: [{e['candidate']}] for [{e['job']}] ({e['round']})" for e in entries]
                parts.append(f"Upcoming interviews (next {f['window_days']} days):\n" + "\n".join(lines))
        elif "funnel" in f:
            scope = f"[{f['job']}]" if f.get("job") else "your organization"
            funnel = ", ".join(f"{st['stage']} {st['count']}" for st in f["funnel"] if st["count"])
            avg = f.get("average_match_score")
            parts.append(
                f"Pipeline for {scope} [{s.ref}], last {f['period_days']} days: {_n(f['applications_total'], 'application')}, "
                f"{_n(f['candidates']['in_pipeline'], 'candidate')} in progress, {f['shortlisted']} shortlisted, "
                f"{f['interviewing']} interviewing, {f['hires']} hired"
                + (f", average match score {avg}%." if avg is not None else ".")
                + (f"\nBy stage: {funnel}." if funnel else "")
            )
            follow_ups.append("Who are the top matches for my newest job?")

    if "top_matches" in tools_used:
        ranked = sorted((c for c in candidates if "match" in c.facts), key=lambda c: c.facts["match"]["score"], reverse=True)
        job_ref = ranked[0].facts["match"]["job"] if ranked else _first([j.ref for j in jobs], "J")
        if ranked:
            lines = []
            for c in ranked:
                m = c.facts["match"]
                detail = f"; missing {', '.join(m['missing_skills'][:3])}" if m.get("missing_skills") else ""
                lines.append(f"- [{c.ref}] {m['score']}% ({m['fit']}): {c.facts.get('headline') or 'candidate'}, "
                             f"{c.facts.get('experience_years') or 0:g} yrs{detail}")
            parts.append(f"Best matches for [{job_ref}]:\n" + "\n".join(lines))
            follow_ups += [f"Tell me more about [{ranked[0].ref}]", "Show the pipeline for this job"]
        elif job_ref:
            parts.append(f"No candidates in your pool match [{job_ref}] yet.")

    if "search_candidates" in tools_used:
        found = sorted((c for c in candidates if "search_rank" in c.facts), key=lambda c: c.facts["search_rank"])
        if found:
            lines = [f"- [{c.ref}] {c.facts.get('headline') or 'candidate'}, {c.facts.get('experience_years') or 0:g} yrs, "
                     f"{c.facts.get('location') or 'location not set'} ({'; '.join(c.facts.get('search_reasons', []))})"
                     for c in found]
            parts.append("Candidates that fit your search:\n" + "\n".join(lines))
            follow_ups.append(f"Tell me more about [{found[0].ref}]")
        else:
            parts.append("No candidates in your pool fit that search. Try fewer or broader terms.")

    if "candidate_overview" in tools_used:
        for c in (c for c in candidates if "applications" in c.facts):
            f = c.facts
            apps = "; ".join(f"[{a['job']}] {a['stage']} (match {a['match_score']}%)" for a in f["applications"])
            parts.append(
                f"[{c.ref}]: {f.get('headline') or 'candidate'}, {f.get('experience_years') or 0:g} yrs, "
                f"{f.get('location') or 'location not set'}, {f.get('work_mode') or 'any work mode'}. "
                f"Skills: {_skills(f) or 'not listed'}. "
                + (f"Applications here: {apps}." if apps else "No applications to your jobs yet.")
            )

    if "list_jobs" in tools_used:
        if jobs:
            lines = [f"- [{j.ref}] {j.facts['title']} ({j.facts['status']}), {j.facts['applicants']} applicants" for j in jobs]
            parts.append("Your jobs:\n" + "\n".join(lines))
            follow_ups.append(f"Who are the best matches for [{jobs[0].ref}]?")
        else:
            parts.append("You have no jobs yet.")

    if not parts:
        parts.append("I couldn't find records for that. You can ask about your jobs, the best matches for a job, "
                     "a candidate, your pipeline, or upcoming interviews.")
    return CopilotAnswer(answer="\n\n".join(parts), cited_refs=[], follow_ups=follow_ups[:3])
