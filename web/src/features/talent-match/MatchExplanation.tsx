import { CheckCircle2, CircleAlert, Info } from "lucide-react";
import { Badge } from "@/components/ui";
import type { MatchDetail } from "@/lib/api/types";

const KIND_LABEL: Record<string, string> = {
  exact: "Listed",
  synonym: "Listed under another name",
  parent: "Related skill",
  related: "Related skill",
  transferable: "Transferable skill",
};

/** Every factor's score, its share of the total, and why. Not-applicable factors are shown as not used. */
export function FactorBreakdown({ match }: { match: MatchDetail }) {
  const used = match.factors.filter((f) => f.score !== null && f.score !== undefined && f.weight > 0);
  const unused = match.factors.filter((f) => !(f.score !== null && f.score !== undefined && f.weight > 0));
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-3">
        {used
          .sort((a, b) => b.weight - a.weight)
          .map((f) => {
            const pct = Math.round((f.score ?? 0) * 100);
            return (
              <li key={f.key} className="grid gap-1">
                <div className="flex items-baseline justify-between gap-2 text-sm">
                  <span className="font-medium text-fg">{f.label}</span>
                  <span className="text-xs text-muted" style={{ fontVariantNumeric: "tabular-nums" }}>
                    <span className="font-semibold text-fg">{pct}%</span> · {Math.round(f.weight * 100)}% of score
                  </span>
                </div>
                <div className="h-2 rounded-full bg-primary-soft" aria-hidden>
                  <div className="h-2 rounded-r-[4px] rounded-l-full bg-viz-1" style={{ width: `${pct}%` }} />
                </div>
                <p className="text-xs text-muted">{f.detail}</p>
              </li>
            );
          })}
      </ul>
      {unused.length > 0 && (
        <p className="flex items-start gap-1.5 text-xs text-muted">
          <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          Not used (no data): {unused.map((f) => f.label).join(", ")}.
        </p>
      )}
    </div>
  );
}

export function SkillEvidence({ match, limit }: { match: MatchDetail; limit?: number }) {
  const matching = limit ? match.matching_skills.slice(0, limit) : match.matching_skills;
  const missing = limit ? match.missing_skills.slice(0, limit) : match.missing_skills;
  return (
    <div className="flex flex-col gap-2">
      {matching.length > 0 && (
        <div className="flex flex-wrap gap-1.5" aria-label="Matching skills">
          {matching.map((s) => (
            <span
              key={s.skill}
              title={s.kind === "exact" ? "Listed on the profile" : `${KIND_LABEL[s.kind] ?? s.kind}: ${s.via ?? ""} (${Math.round(s.score * 100)}% credit)`}
              className="nowrap inline-flex items-center gap-1 rounded-full bg-success-soft px-2 py-0.5 text-xs font-medium text-success"
            >
              <CheckCircle2 className="size-3" aria-hidden />
              {s.skill}
              {s.kind !== "exact" && s.via && <span className="text-muted">via {s.via}</span>}
            </span>
          ))}
        </div>
      )}
      {missing.length > 0 && (
        <div className="flex flex-wrap gap-1.5" aria-label="Missing skills">
          {missing.map((s) => (
            <span key={s.skill} className="nowrap inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs text-muted">
              <CircleAlert className="size-3" aria-hidden />
              {s.skill}
              {s.importance === "preferred" && <span>(preferred)</span>}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function MatchExplanation({ match, disclaimer }: { match: MatchDetail; disclaimer: string }) {
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-3">
        <span className="font-display text-4xl font-semibold text-fg">{match.score}%</span>
        <Badge tone={match.score >= 80 ? "success" : match.score >= 65 ? "primary" : "neutral"}>{match.fit_level}</Badge>
      </div>
      <p className="text-sm text-fg">{match.explanation}</p>
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">How the score is made</h3>
        <FactorBreakdown match={match} />
      </section>
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Skills</h3>
        <SkillEvidence match={match} />
      </section>
      {(match.strengths.length > 0 || match.gaps.length > 0) && (
        <div className="grid gap-4 sm:grid-cols-2">
          <section>
            <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">Strong matches</h3>
            <ul className="list-disc pl-5 text-sm text-fg">{match.strengths.map((s) => <li key={s}>{s}</li>)}</ul>
          </section>
          <section>
            <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">Gaps to explore</h3>
            <ul className="list-disc pl-5 text-sm text-fg">{match.gaps.map((g) => <li key={g}>{g}</li>)}</ul>
          </section>
        </div>
      )}
      <p className="rounded-lg bg-surface-2 p-3 text-xs text-muted">{disclaimer}</p>
    </div>
  );
}
