import { useState } from "react";
import { Briefcase, MapPin } from "lucide-react";
import { Badge, Button, Card, EmptyState, ErrorState, Modal, PageHeader, Skeleton, useToast } from "@/components/ui";
import { MatchScore } from "@/features/dashboard/MatchScore";
import type { JobMatchItem } from "@/lib/api/types";
import { formatSalaryRange } from "@/lib/format";
import { useApply, useMyJobMatches } from "./api";
import { MatchExplanation, SkillEvidence } from "./MatchExplanation";

const CANDIDATE_DISCLAIMER = "The match reflects how your profile lines up with the job's listed requirements. Keeping your skills and experience up to date improves it.";

export function JobsForYouPage() {
  const toast = useToast();
  const { data, isLoading, isError, error, refetch } = useMyJobMatches();
  const apply = useApply();
  const [explaining, setExplaining] = useState<JobMatchItem | null>(null);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Jobs for you" description="Open roles ranked by how well they fit your profile." />
      {isLoading ? (
        <div className="flex flex-col gap-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-36" />)}</div>
      ) : isError ? (
        <Card><ErrorState message={error.message} onRetry={() => void refetch()} /></Card>
      ) : !data?.length ? (
        <Card><EmptyState title="No open jobs right now" description="New roles that match your profile will show up here and in your notifications." /></Card>
      ) : (
        <ul className="flex flex-col gap-3">
          {data.map((item) => (
            <li key={item.job.id} className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4 shadow-card">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-fg">{item.job.title}</p>
                  <p className="flex flex-wrap items-center gap-x-3 text-sm text-muted">
                    <span className="inline-flex items-center gap-1"><Briefcase className="size-3.5" aria-hidden />{item.job.company_name}</span>
                    <span className="inline-flex items-center gap-1"><MapPin className="size-3.5" aria-hidden />{item.job.location} · {item.job.workplace_type}</span>
                    <span>{formatSalaryRange(item.job.salary_min, item.job.salary_max)}</span>
                  </p>
                </div>
                <button type="button" onClick={() => setExplaining(item)} className="text-right" aria-label={`Why ${item.job.title} matches you`}>
                  <MatchScore value={item.match.score} className="text-sm" />
                  <span className="mt-1 block text-[11px] text-primary hover:underline">Why this match</span>
                </button>
              </div>
              <SkillEvidence match={item.match} limit={8} />
              <div className="flex items-center justify-between gap-2 border-t border-border pt-3">
                {item.applied ? <Badge tone="success">Applied · {item.application_stage}</Badge> : <span className="text-xs text-muted">{item.match.fit_level}</span>}
                {!item.applied && (
                  <Button size="sm" loading={apply.isPending && apply.variables === item.job.id}
                    onClick={() => apply.mutate(item.job.id, {
                      onSuccess: () => toast.success(`Applied to ${item.job.title}`),
                      onError: (e) => toast.error(e.message),
                    })}>
                    Apply
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      <Modal open={!!explaining} size="lg" title={explaining ? `How you match ${explaining.job.title}` : ""} onClose={() => setExplaining(null)}>
        {explaining && <MatchExplanation match={explaining.match} disclaimer={CANDIDATE_DISCLAIMER} />}
      </Modal>
    </div>
  );
}
