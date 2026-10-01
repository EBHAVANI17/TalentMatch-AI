import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Archive, Copy, Pause, Pencil, Send, XCircle } from "lucide-react";
import {
  Badge, Button, ButtonLink, Card, CardBody, CardHeader, ConfirmDialog, EmptyState, ErrorState, FullPageSpinner,
  PageHeader, Select, useToast,
} from "@/components/ui";
import { MatchScore } from "@/features/dashboard/MatchScore";
import { api } from "@/lib/api/client";
import type { PipelineStage } from "@/lib/api/types";
import { experienceLabel, formatDate, formatSalaryRange } from "@/lib/format";
import {
  ACTIONS_BY_STATUS, JOB_STATUS_TONE, jobStatusLabel, useDuplicateJob, useJob, useJobAction, useJobApplicants,
  useMoveApplication, type JobAction,
} from "./api";

const ACTION_UI: Record<JobAction, { label: string; icon: typeof Send; confirm?: string; variant: "primary" | "secondary" | "danger" }> = {
  publish: { label: "Publish", icon: Send, variant: "primary" },
  pause: { label: "Pause", icon: Pause, variant: "secondary" },
  close: { label: "Close", icon: XCircle, variant: "secondary", confirm: "Closing removes the job from the job board and stops new applications. You can reopen it later." },
  archive: { label: "Archive", icon: Archive, variant: "secondary", confirm: "Archived jobs become read-only. You can still duplicate an archived job." },
};

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm text-fg">{children}</dd>
    </div>
  );
}

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const job = useJob(jobId);
  const applicants = useJobApplicants(jobId);
  const stages = useQuery({ queryKey: ["pipeline", "stages"], queryFn: () => api<PipelineStage[]>("/pipeline/stages") });
  const action = useJobAction(jobId);
  const duplicate = useDuplicateJob(jobId);
  const move = useMoveApplication(jobId);
  const [pending, setPending] = useState<JobAction | null>(null);

  if (job.isLoading) return <FullPageSpinner label="Loading job" />;
  if (job.isError || !job.data) return <ErrorState message={job.error?.message ?? "Job not found"} onRetry={() => void job.refetch()} />;
  const j = job.data;

  async function run(a: JobAction) {
    try {
      await action.mutateAsync(a);
      toast.success(`Job ${a === "publish" ? "published" : a === "pause" ? "paused" : a === "close" ? "closed" : "archived"}`);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setPending(null);
    }
  }

  async function copy() {
    try {
      const created = await duplicate.mutateAsync();
      toast.success("Draft copy created");
      navigate(`/jobs/${created.id}/edit`);
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  const stageOptions = (stages.data ?? []).map((s) => ({ value: s.name, label: s.name }));

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={j.title}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <Badge tone={JOB_STATUS_TONE[j.status] ?? "neutral"}>{jobStatusLabel(j.status)}</Badge>
            {j.department} · {j.location} · {j.workplace_type}
          </span>
        }
        actions={
          <>
            {j.status !== "Archived" && (
              <ButtonLink to={`/jobs/${j.id}/edit`} variant="secondary">
                <Pencil className="size-4" aria-hidden /> Edit
              </ButtonLink>
            )}
            <Button variant="secondary" icon={<Copy className="size-4" aria-hidden />} loading={duplicate.isPending} onClick={() => void copy()}>
              Duplicate
            </Button>
            {(ACTIONS_BY_STATUS[j.status] ?? []).map((a) => {
              const ui = ACTION_UI[a];
              const Icon = ui.icon;
              return (
                <Button
                  key={a}
                  variant={ui.variant}
                  icon={<Icon className="size-4" aria-hidden />}
                  loading={action.isPending && action.variables === a}
                  onClick={() => (ui.confirm ? setPending(a) : void run(a))}
                >
                  {a === "publish" && j.status === "Closed" ? "Reopen" : ui.label}
                </Button>
              );
            })}
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Applicants" description={`${applicants.data?.length ?? 0} in the pipeline`} />
          <CardBody className="py-0">
            {applicants.isLoading ? (
              <p className="py-4 text-sm text-muted">Loading applicants</p>
            ) : applicants.isError ? (
              <ErrorState message={applicants.error.message} onRetry={() => void applicants.refetch()} />
            ) : !applicants.data?.length ? (
              <EmptyState title="No applicants yet" description={j.status === "Active" ? "Candidates who apply will appear here." : "Publish the job to start receiving applications."} />
            ) : (
              <ul className="divide-y divide-border">
                {applicants.data.map((a) => (
                  <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                    <div className="min-w-0">
                      <Link to={`/candidates/${a.candidate_id}`} className="text-sm font-semibold text-fg hover:text-primary">
                        {a.candidate_name}
                      </Link>
                      <p className="text-xs text-muted">
                        {a.candidate_title || "Candidate"} · {experienceLabel(a.candidate_experience_years)} · applied {formatDate(a.created_at)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <MatchScore value={a.match_score} />
                      <Select
                        aria-label={`Stage for ${a.candidate_name}`}
                        value={a.stage}
                        options={stageOptions.some((o) => o.value === a.stage) ? stageOptions : [{ value: a.stage, label: a.stage }, ...stageOptions]}
                        disabled={move.isPending || j.status === "Archived"}
                        onChange={(e) =>
                          move.mutate(
                            { applicationId: a.id, stage: e.target.value },
                            {
                              onSuccess: (updated) => toast.success(`${a.candidate_name} moved to ${updated.stage}`),
                              onError: (err) => toast.error(err.message),
                            },
                          )
                        }
                        className="h-8 w-36 text-xs"
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Details" />
          <CardBody>
            <dl className="grid grid-cols-2 gap-4">
              <Fact label="Employment">{j.employment_type}</Fact>
              <Fact label="Openings">{j.openings}</Fact>
              <Fact label="Experience">
                {j.min_experience_years}
                {j.max_experience_years != null ? `–${j.max_experience_years}` : "+"} yrs
              </Fact>
              <Fact label="Education">{j.required_education}</Fact>
              <Fact label="Salary">{formatSalaryRange(j.salary_min, j.salary_max)}</Fact>
              <Fact label="Deadline">{j.application_deadline ? formatDate(j.application_deadline) : "None"}</Fact>
              <Fact label="Published">{j.published_at ? formatDate(j.published_at) : "Not yet"}</Fact>
              <Fact label="Applicants">{j.applicants_count}</Fact>
            </dl>
            <div className="mt-5 flex flex-col gap-3">
              <div>
                <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted">Required skills</p>
                <div className="flex flex-wrap gap-1.5">{j.required_skills.map((s) => <Badge key={s} tone="primary">{s}</Badge>)}</div>
              </div>
              {j.preferred_skills.length > 0 && (
                <div>
                  <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted">Preferred skills</p>
                  <div className="flex flex-wrap gap-1.5">{j.preferred_skills.map((s) => <Badge key={s}>{s}</Badge>)}</div>
                </div>
              )}
            </div>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Description" />
        <CardBody className="flex flex-col gap-4 text-sm text-fg">
          <p className="whitespace-pre-line">{j.description}</p>
          {j.key_responsibilities.length > 0 && (
            <ul className="list-disc pl-5 text-muted">
              {j.key_responsibilities.map((r) => <li key={r}>{r}</li>)}
            </ul>
          )}
        </CardBody>
      </Card>

      <ConfirmDialog
        open={pending !== null}
        title={pending ? `${ACTION_UI[pending].label} this job?` : ""}
        message={pending ? ACTION_UI[pending].confirm : ""}
        confirmLabel={pending ? ACTION_UI[pending].label : "Confirm"}
        destructive={pending === "close" || pending === "archive"}
        loading={action.isPending}
        onConfirm={() => pending && void run(pending)}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}
