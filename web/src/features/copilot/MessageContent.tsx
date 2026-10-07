import { Fragment, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { BarChart3, Briefcase, UserRound } from "lucide-react";
import type { CopilotCitation } from "@/lib/api/types";

const REF = /\[([CJS]\d{1,3})\]/g;

function Chip({ citation, onNavigate }: { citation: CopilotCitation; onNavigate?: () => void }) {
  const Icon = citation.kind === "job" ? Briefcase : citation.kind === "candidate" ? UserRound : BarChart3;
  const classes =
    "mx-0.5 inline-flex max-w-[16rem] items-center gap-1 rounded-md px-1.5 py-0.5 align-baseline text-xs font-semibold";
  const content = (
    <>
      <Icon className="size-3 shrink-0" aria-hidden />
      <span className="truncate">{citation.label}</span>
    </>
  );
  if (!citation.available) {
    return <span className={`${classes} bg-surface-2 text-muted`} title="You no longer have access to this record">{content}</span>;
  }
  if (!citation.url) return <span className={`${classes} bg-surface-2 text-fg`}>{content}</span>;
  return (
    <Link to={citation.url} onClick={onNavigate} className={`${classes} bg-primary-soft text-primary hover:underline`}>
      {content}
    </Link>
  );
}

/** Replaces [C1]-style references with links to the cited records. */
export function withCitations(text: string, citations: CopilotCitation[], onNavigate?: () => void): ReactNode[] {
  const byRef = new Map(citations.map((c) => [c.ref, c]));
  const out: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(REF)) {
    const citation = byRef.get(match[1]);
    out.push(text.slice(last, match.index));
    out.push(citation ? <Chip key={`${match.index}-${match[1]}`} citation={citation} onNavigate={onNavigate} /> : "");
    last = (match.index ?? 0) + match[0].length;
  }
  out.push(text.slice(last));
  return out;
}

/** Plain text with paragraphs and "- " bullet lists, plus citation chips. No HTML is ever injected. */
export function MessageContent({ text, citations, onNavigate }: { text: string; citations: CopilotCitation[]; onNavigate?: () => void }) {
  const blocks = text.split(/\n{2,}/);
  return (
    <div className="space-y-2 text-sm leading-relaxed">
      {blocks.map((block, i) => {
        const lines = block.split("\n");
        const bullets = lines.filter((l) => l.trim().startsWith("- "));
        if (bullets.length && bullets.length >= lines.length - 1) {
          const heading = lines[0].trim().startsWith("- ") ? null : lines[0];
          return (
            <Fragment key={i}>
              {heading && <p>{withCitations(heading, citations, onNavigate)}</p>}
              <ul className="list-disc space-y-1 pl-5">
                {bullets.map((l, j) => (
                  <li key={j}>{withCitations(l.trim().slice(2), citations, onNavigate)}</li>
                ))}
              </ul>
            </Fragment>
          );
        }
        return (
          <p key={i} className="whitespace-pre-line">
            {withCitations(block, citations, onNavigate)}
          </p>
        );
      })}
    </div>
  );
}
