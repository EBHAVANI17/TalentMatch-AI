import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Briefcase, CalendarClock, Gauge, ListChecks, Sparkles, UserCheck, Users } from "lucide-react";
import { DailyColumns } from "@/components/charts/DailyColumns";
import { FunnelBars } from "@/components/charts/FunnelBars";
import { StatTile } from "@/components/charts/StatTile";
import { Badge, ButtonLink, Card, CardBody, CardHeader, EmptyState, ErrorState, PageHeader, Select, Skeleton, cn } from "@/components/ui";
import { useJobs } from "@/features/jobs/api";
import { api } from "@/lib/api/client";
import type { Application, RecruiterDashboard } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { MatchScore } from "./MatchScore";

const PERIODS = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
];

function ApplicationRow({ app }: { app: Application }) {
  return (
    <li className="flex items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <Link to={`/candidates/${app.candidate_id}`} className="truncate text-sm font-semibold text-fg hover:text-primary">
          {app.candidate_name}
        </Link>
        <p className="truncate text-xs text-muted">
          {app.job_title} · {formatDate(app.created_at)}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Badge>{app.stage}</Badge>
        <MatchScore value={app.match_score} />
      </div>
    </li>
  );
}

export function DashboardPage() {
  const [days, setDays] = useState("30");
  const [jobId, setJobId] = useState("");
  const jobs = useJobs({ status: "all" });

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["dashboard", "recruiter", days, jobId],
    queryFn: () => api<RecruiterDashboard>("/dashboard/recruiter", { query: { days, job_id: jobId || undefined } }),
    placeholderData: (previous) => previous,
  });

  const jobOptions = [{ value: "", label: "All jobs" }, ...(jobs.data ?? []).map((j) => ({ value: j.id, label: j.title }))];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Dashboard"
        description="Hiring activity across your organization."
        actions={<ButtonLink to="/jobs/new">Create job</ButtonLink>}
      />

      {/* Filters scope everything below them */}
      <div className="flex flex-wrap gap-2">
        <Select aria-label="Time period" value={days} onChange={(e) => setDays(e.target.value)} options={PERIODS} className="w-40" />
        <Select aria-label="Job" value={jobId} onChange={(e) => setJobId(e.target.value)} options={jobOptions} className="w-64 max-w-full" />
      </div>

      {isError ? (
        <Card>
          <ErrorState message={error.message} onRetry={() => void refetch()} />
        </Card>
      ) : isLoading || !data ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : (
        <div className={cn("flex flex-col gap-6 transition-opacity", isFetching && "opacity-60")}>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile icon={Briefcase} label="Active jobs" value={data.jobs.active} hint={`${data.jobs.total} total, ${data.jobs.draft} ${data.jobs.draft === 1 ? "draft" : "drafts"}`} />
            <StatTile icon={Users} label="Candidates in pipeline" value={data.candidates.in_pipeline} />
            <StatTile icon={Sparkles} label="New candidates" value={data.candidates.new_in_period} hint={PERIODS.find((p) => p.value === days)?.label} />
            <StatTile icon={ListChecks} label="Shortlisted" value={data.shortlisted} />
            <StatTile icon={CalendarClock} label="In interview" value={data.interviewing} hint={`${data.upcoming_interviews} ${data.upcoming_interviews === 1 ? "interview" : "interviews"} scheduled`} />
            <StatTile icon={UserCheck} label="Hires" value={data.hires} />
            <StatTile icon={Gauge} label="Average match score" value={data.average_match_score === null || data.average_match_score === undefined ? null : `${data.average_match_score}%`} hint="Fit to each job's listed criteria" />
            <StatTile icon={Briefcase} label="Applications" value={data.applications_total} />
          </div>

          <div className="grid gap-6 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <CardHeader title="Applications per day" description={PERIODS.find((p) => p.value === days)?.label} />
              <CardBody>
                <DailyColumns data={data.applications_by_day} label="Applications per day" />
              </CardBody>
            </Card>
            <Card className="lg:col-span-2">
              <CardHeader title="Pipeline" description="Applications currently in each stage" />
              <CardBody>
                <FunnelBars stages={data.funnel} label="Applications by pipeline stage" />
              </CardBody>
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="Recent applications" />
              <CardBody className="py-0">
                {data.recent_applications.length ? (
                  <ul className="divide-y divide-border">
                    {data.recent_applications.map((a) => (
                      <ApplicationRow key={a.id} app={a} />
                    ))}
                  </ul>
                ) : (
                  <EmptyState title="No applications yet" description="Publish a job to start receiving applications." />
                )}
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Top matches in progress" description="Highest match scores among open applications" />
              <CardBody className="py-0">
                {data.top_matches.length ? (
                  <ul className="divide-y divide-border">
                    {data.top_matches.map((a) => (
                      <ApplicationRow key={a.id} app={a} />
                    ))}
                  </ul>
                ) : (
                  <EmptyState title="No open applications" />
                )}
              </CardBody>
            </Card>
          </div>
          <p className="text-xs text-muted">
            Match scores measure fit to each job's listed requirements (skills, experience, location, salary, education). They are not a measure of a candidate's quality.
          </p>
        </div>
      )}
    </div>
  );
}
