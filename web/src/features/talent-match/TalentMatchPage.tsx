import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FileText, MapPin, Search, Sparkles, ThumbsDown, ThumbsUp, Undo2 } from "lucide-react";
import {
  Avatar, Badge, Button, ButtonLink, Card, EmptyState, ErrorState, Modal, PageHeader, Select, Skeleton, TagInput, cn, useToast,
} from "@/components/ui";
import { openDocument } from "@/features/candidates/api";
import { MatchScore } from "@/features/dashboard/MatchScore";
import { useJobs } from "@/features/jobs/api";
import type { CandidateMatchItem } from "@/lib/api/types";
import { experienceLabel } from "@/lib/format";
import { useJobMatches, useMatchDecision, type MatchFilters } from "./api";
import { MatchExplanation, SkillEvidence } from "./MatchExplanation";

const MIN_SCORE = [
  { value: "0", label: "Any match" }, { value: "50", label: "50%+" }, { value: "65", label: "65%+" }, { value: "80", label: "80%+" },
];
const EXPERIENCE = [{ value: "", label: "Any experience" }, { value: "2", label: "2+ years" }, { value: "5", label: "5+ years" }, { value: "8", label: "8+ years" }];
const EDUCATION = [{ value: "", label: "Any education" }, { value: "Bachelor", label: "Bachelor's" }, { value: "Master", label: "Master's" }, { value: "PhD", label: "PhD" }];
const AVAILABILITY = [{ value: "", label: "Any availability" }, { value: "open", label: "Open to opportunities" }, { value: "passive", label: "Open to the right role" }];
const WORK_MODE = [{ value: "", label: "Any work mode" }, { value: "Remote", label: "Remote" }, { value: "Hybrid", label: "Hybrid" }, { value: "Onsite", label: "Onsite" }];
const SORT = [{ value: "score", label: "Best match" }, { value: "experience", label: "Most experience" }, { value: "active", label: "Recently active" }, { value: "recent", label: "Recently added" }];
const STATUS_TABS: Array<{ value: NonNullable<MatchFilters["status"]>; label: string }> = [
  { value: "active", label: "Matches" }, { value: "shortlisted", label: "Shortlisted" }, { value: "dismissed", label: "Dismissed" },
];

function MatchCard({ item, onExplain, onDecide, busy }: {
  item: CandidateMatchItem; onExplain: () => void; busy: boolean;
  onDecide: (action: "shortlist" | "reject" | "restore") => void;
}) {
  const toast = useToast();
  const c = item.candidate;
  const decided = item.status !== "new";
  return (
    <li className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4 shadow-card">
      <div className="flex items-start gap-3">
        <Avatar name={c.name} src={c.avatar_url} />
        <div className="min-w-0 flex-1">
          <Link to={`/candidates/${c.id}`} className="block truncate font-semibold text-fg hover:text-primary">{c.name}</Link>
          <p className="truncate text-sm text-muted">{c.title || "No headline yet"}</p>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
            <span>{experienceLabel(c.experience_years)}</span>
            <span className="inline-flex items-center gap-1"><MapPin className="size-3" aria-hidden />{c.location || "Location not set"}</span>
            <span>{c.remote_preference}</span>
          </p>
        </div>
        <button type="button" onClick={onExplain} className="shrink-0 rounded-lg text-right hover:opacity-80" aria-label={`Why ${c.name} matches`}>
          <MatchScore value={item.match.score} className="text-sm" />
          <span className="mt-1 block text-[11px] text-primary underline-offset-2 hover:underline">Why this match</span>
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5" aria-label="Top skills">
        {c.skills.slice(0, 6).map((s) => <Badge key={s}>{s}</Badge>)}
      </div>
      <SkillEvidence match={item.match} limit={6} />

      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
        <div className="flex items-center gap-2 text-xs text-muted">
          {item.application ? <Badge tone="primary">{item.application.stage}</Badge> : <span>Not in pipeline</span>}
          {item.status === "dismissed" && <Badge>Dismissed</Badge>}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {item.resume_document_id && (
            <Button size="sm" variant="ghost" icon={<FileText className="size-4" aria-hidden />}
              onClick={() => openDocument(item.resume_document_id as string).catch((e: Error) => toast.error(e.message))}>
              Resume
            </Button>
          )}
          <ButtonLink to={`/candidates/${c.id}`} size="sm" variant="ghost">View profile</ButtonLink>
          {item.status === "dismissed" ? (
            <Button size="sm" variant="secondary" icon={<Undo2 className="size-4" aria-hidden />} loading={busy} onClick={() => onDecide("restore")}>Restore</Button>
          ) : (
            <>
              <Button size="sm" variant="secondary" icon={<ThumbsDown className="size-4" aria-hidden />} disabled={busy} onClick={() => onDecide("reject")}>Reject</Button>
              <Button size="sm" icon={<ThumbsUp className="size-4" aria-hidden />} loading={busy} disabled={decided && item.status === "shortlisted"} onClick={() => onDecide("shortlist")}>
                {item.status === "shortlisted" ? "Shortlisted" : "Shortlist"}
              </Button>
            </>
          )}
        </div>
      </div>
    </li>
  );
}

export function TalentMatchPage() {
  const [params, setParams] = useSearchParams();
  const toast = useToast();
  const jobs = useJobs({ status: "Active" });
  const jobId = params.get("job") ?? jobs.data?.[0]?.id;
  const [filters, setFilters] = useState<MatchFilters>({ status: "active", sort: "score" });
  const [skills, setSkills] = useState<string[]>([]);
  const query = useMemo(() => ({ ...filters, skills }), [filters, skills]);
  const matches = useJobMatches(jobId, query);
  const decide = useMatchDecision(jobId ?? "");
  const [explaining, setExplaining] = useState<CandidateMatchItem | null>(null);
  const update = (patch: Partial<MatchFilters>) => setFilters((f) => ({ ...f, ...patch }));

  function onDecide(item: CandidateMatchItem, action: "shortlist" | "reject" | "restore") {
    decide.mutate(
      { candidateId: item.candidate.id, action },
      {
        onSuccess: () => toast.success(
          action === "shortlist" ? `${item.candidate.name} shortlisted and added to the pipeline`
            : action === "reject" ? (item.application ? `${item.candidate.name} moved to Rejected` : `${item.candidate.name} dismissed from this list`)
              : `${item.candidate.name} restored`,
        ),
        onError: (err) => toast.error(err.message),
      },
    );
  }

  if (jobs.isLoading) return <Skeleton className="h-40" />;
  if (!jobs.data?.length) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Talent Match" />
        <Card><EmptyState title="No published jobs" description="Publish a job to see matching candidates." action={<ButtonLink to="/jobs/new" size="sm">Create job</ButtonLink>} /></Card>
      </div>
    );
  }

  const data = matches.data;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Talent Match" description="Candidates ranked by fit to the job's requirements, with the reasons behind each score." />

      <div className="flex flex-wrap items-center gap-3">
        <Select aria-label="Job" value={jobId} onChange={(e) => setParams({ job: e.target.value })}
          options={jobs.data.map((j) => ({ value: j.id, label: j.title }))} className="w-80 max-w-full" />
        {data && (
          <p className="flex items-center gap-2 text-sm text-muted">
            <Sparkles className="size-4 text-primary" aria-hidden />
            <span><span className="font-semibold text-fg">{data.summary.potential}</span> potentially relevant candidates found ·{" "}
              <span className="font-semibold text-fg">{data.summary.strong}</span> strong matches (80%+) of {data.summary.considered} reviewed</span>
          </p>
        )}
      </div>

      <Card className="flex flex-col gap-3 p-4">
        <div className="flex flex-wrap gap-2">
          <Select aria-label="Minimum match" value={String(filters.min_score ?? 0)} onChange={(e) => update({ min_score: Number(e.target.value) || undefined })} options={MIN_SCORE} className="w-32" />
          <Select aria-label="Experience" value={String(filters.min_experience ?? "")} onChange={(e) => update({ min_experience: e.target.value ? Number(e.target.value) : undefined })} options={EXPERIENCE} className="w-36" />
          <label className="relative w-44">
            <span className="sr-only">Location</span>
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
            <input value={filters.location ?? ""} onChange={(e) => update({ location: e.target.value || undefined })} placeholder="Location"
              className="h-10 w-full rounded-lg border border-border bg-surface pl-9 pr-3 text-sm text-fg placeholder:text-muted focus:border-primary focus:outline-none" />
          </label>
          <Select aria-label="Education" value={filters.education ?? ""} onChange={(e) => update({ education: e.target.value || undefined })} options={EDUCATION} className="w-36" />
          <Select aria-label="Availability" value={filters.availability ?? ""} onChange={(e) => update({ availability: e.target.value || undefined })} options={AVAILABILITY} className="w-48" />
          <Select aria-label="Work mode" value={filters.remote_preference ?? ""} onChange={(e) => update({ remote_preference: e.target.value || undefined })} options={WORK_MODE} className="w-36" />
          <input aria-label="Maximum expected salary" type="number" min={0} value={filters.max_salary ?? ""} onChange={(e) => update({ max_salary: e.target.value ? Number(e.target.value) : undefined })}
            placeholder="Max salary" className="h-10 w-32 rounded-lg border border-border bg-surface px-3 text-sm text-fg placeholder:text-muted focus:border-primary focus:outline-none" />
          <Select aria-label="Sort by" value={filters.sort} onChange={(e) => update({ sort: e.target.value as MatchFilters["sort"] })} options={SORT} className="w-40" />
        </div>
        <TagInput label="Must have skills" value={skills} onChange={setSkills} placeholder="Type a skill and press Enter" />
      </Card>

      <div role="tablist" aria-label="Match status" className="flex gap-1 border-b border-border">
        {STATUS_TABS.map((t) => (
          <button key={t.value} role="tab" type="button" aria-selected={filters.status === t.value} onClick={() => update({ status: t.value })}
            className={cn("-mb-px border-b-2 px-3 py-2 text-sm font-medium", filters.status === t.value ? "border-primary text-primary" : "border-transparent text-muted hover:text-fg")}>
            {t.label}
          </button>
        ))}
      </div>

      {matches.isLoading ? (
        <div className="grid gap-3 lg:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-56" />)}</div>
      ) : matches.isError ? (
        <Card><ErrorState message={matches.error.message} onRetry={() => void matches.refetch()} /></Card>
      ) : !data?.items.length ? (
        <Card><EmptyState title="No candidates here" description={filters.status === "active" ? "Try lowering the minimum match or removing a filter." : "Nothing in this list yet."} /></Card>
      ) : (
        <ul className={cn("grid gap-3 lg:grid-cols-2 transition-opacity", matches.isFetching && "opacity-60")}>
          {data.items.map((item) => (
            <MatchCard key={item.candidate.id} item={item} onExplain={() => setExplaining(item)}
              busy={decide.isPending && decide.variables?.candidateId === item.candidate.id}
              onDecide={(action) => onDecide(item, action)} />
          ))}
        </ul>
      )}
      {data && <p className="text-xs text-muted">{data.disclaimer}</p>}

      <Modal open={!!explaining} size="lg" title={explaining ? `Why ${explaining.candidate.name} matches ${data?.job.title ?? "this job"}` : ""} onClose={() => setExplaining(null)}>
        {explaining && data && <MatchExplanation match={explaining.match} disclaimer={data.disclaimer} />}
      </Modal>
    </div>
  );
}
