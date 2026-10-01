import { useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Search } from "lucide-react";
import { Badge, ButtonLink, Card, EmptyState, ErrorState, PageHeader, Select, Skeleton, cn } from "@/components/ui";
import { formatDate, formatSalaryRange } from "@/lib/format";
import { JOB_STATUS_TONE, jobStatusLabel, useJobs } from "./api";

const STATUS_OPTIONS = [
  { value: "all", label: "All statuses" },
  { value: "Active", label: "Published" },
  { value: "Draft", label: "Draft" },
  { value: "Paused", label: "Paused" },
  { value: "Closed", label: "Closed" },
  { value: "Archived", label: "Archived" },
];

const WORKPLACE_OPTIONS = [
  { value: "", label: "Any work mode" },
  { value: "Remote", label: "Remote" },
  { value: "Hybrid", label: "Hybrid" },
  { value: "Onsite", label: "Onsite" },
];

export function JobsPage() {
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");
  const [workplace, setWorkplace] = useState("");
  const { data, isLoading, isError, error, refetch, isFetching } = useJobs({
    status, q: q.trim() || undefined, workplace_type: workplace || undefined,
  });

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Jobs"
        description="Create, publish and manage your organization's requisitions."
        actions={
          <ButtonLink to="/jobs/new">
            <Plus className="size-4" aria-hidden /> Create job
          </ButtonLink>
        }
      />

      <div className="flex flex-wrap gap-2">
        <label className="relative flex-1 sm:max-w-xs">
          <span className="sr-only">Search jobs</span>
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search title, department, location"
            className="h-10 w-full rounded-lg border border-border bg-surface pl-9 pr-3 text-sm text-fg placeholder:text-muted focus:border-primary focus:outline-none"
          />
        </label>
        <Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} options={STATUS_OPTIONS} className="w-40" />
        <Select aria-label="Work mode" value={workplace} onChange={(e) => setWorkplace(e.target.value)} options={WORKPLACE_OPTIONS} className="w-40" />
      </div>

      <Card className={cn("transition-opacity", isFetching && !isLoading && "opacity-60")}>
        {isLoading ? (
          <div className="flex flex-col gap-2 p-5">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : isError ? (
          <ErrorState message={error.message} onRetry={() => void refetch()} />
        ) : !data?.length ? (
          <EmptyState
            title={q || status !== "all" || workplace ? "No jobs match these filters" : "No jobs yet"}
            description="Create a requisition to start receiving and sourcing candidates."
            action={<ButtonLink to="/jobs/new" size="sm" variant="secondary">Create job</ButtonLink>}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-5 py-3 font-semibold">Job</th>
                  <th className="hidden px-3 py-3 font-semibold md:table-cell">Location</th>
                  <th className="hidden px-3 py-3 font-semibold lg:table-cell">Salary</th>
                  <th className="px-3 py-3 font-semibold">Applicants</th>
                  <th className="px-3 py-3 font-semibold">Status</th>
                  <th className="hidden px-5 py-3 font-semibold sm:table-cell">Updated</th>
                </tr>
              </thead>
              <tbody>
                {data.map((job) => (
                  <tr key={job.id} className="border-b border-border last:border-0 hover:bg-surface-2">
                    <td className="px-5 py-3">
                      <Link to={`/jobs/${job.id}`} className="font-semibold text-fg hover:text-primary">
                        {job.title}
                      </Link>
                      <p className="text-xs text-muted">
                        {job.department} · {job.employment_type}
                        {job.openings > 1 ? ` · ${job.openings} openings` : ""}
                      </p>
                    </td>
                    <td className="hidden px-3 py-3 text-muted md:table-cell">
                      {job.location} · {job.workplace_type}
                    </td>
                    <td className="hidden px-3 py-3 text-muted lg:table-cell">{formatSalaryRange(job.salary_min, job.salary_max)}</td>
                    <td className="px-3 py-3" style={{ fontVariantNumeric: "tabular-nums" }}>{job.applicants_count}</td>
                    <td className="px-3 py-3">
                      <Badge tone={JOB_STATUS_TONE[job.status] ?? "neutral"}>{jobStatusLabel(job.status)}</Badge>
                    </td>
                    <td className="hidden px-5 py-3 text-muted sm:table-cell">{formatDate(job.updated_at ?? job.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
