import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Briefcase, Building2, Sparkles, Tag } from "lucide-react";
import { Avatar, Badge, Card, CardBody, CardHeader, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui";
import { api } from "@/lib/api/client";
import type { SearchResults } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/AuthProvider";
import { isCandidate } from "@/lib/auth/roles";
import { experienceLabel } from "@/lib/format";

function Interpreted({ data }: { data: Record<string, unknown> }) {
  const chips: string[] = [];
  if (Array.isArray(data.skills) && data.skills.length) chips.push(`Skills: ${(data.skills as string[]).join(", ")}`);
  if (data.min_experience != null) chips.push(`${data.min_experience}+ years`);
  if (data.max_experience != null) chips.push(`Up to ${data.max_experience} years`);
  if (data.location) chips.push(`Location: ${data.location}`);
  if (data.remote_preference) chips.push(`Work mode: ${data.remote_preference}`);
  if (Array.isArray(data.keywords) && data.keywords.length) chips.push(`Words: ${(data.keywords as string[]).join(", ")}`);
  if (!chips.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
      <Sparkles className="size-4 text-primary" aria-hidden /> Understood as:
      {chips.map((c) => <Badge key={c} tone="primary">{c}</Badge>)}
    </div>
  );
}

export function SearchPage() {
  const [params] = useSearchParams();
  const { user } = useAuth();
  const q = (params.get("q") ?? "").trim();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["search", q],
    queryFn: () => api<SearchResults>("/search", { query: { q, limit: 12 } }),
    enabled: q.length > 0,
  });

  if (!q) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Search" />
        <Card><EmptyState title="Search in plain language" description={'For example: "senior engineers with strong cloud experience in Bangalore".'} /></Card>
      </div>
    );
  }

  const total = data ? data.candidates.length + data.jobs.length + data.skills.length + data.organizations.length : 0;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={`Results for "${q}"`} description={data ? `${total} results` : undefined} />
      {data && <Interpreted data={data.interpreted as Record<string, unknown>} />}

      {isLoading ? (
        <Skeleton className="h-64" />
      ) : isError ? (
        <Card><ErrorState message={error.message} onRetry={() => void refetch()} /></Card>
      ) : !data || total === 0 ? (
        <Card><EmptyState title="Nothing found" description="Try different words, fewer requirements, or a broader location." /></Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="flex flex-col gap-6 lg:col-span-2">
            {!isCandidate(user) && data.candidates.length > 0 && (
              <Card>
                <CardHeader title="Candidates" />
                <CardBody className="py-0">
                  <ul className="divide-y divide-border">
                    {data.candidates.map(({ candidate: c, reasons }) => (
                      <li key={c.id} className="flex items-start gap-3 py-3">
                        <Avatar name={c.name} src={c.avatar_url} size="sm" />
                        <div className="min-w-0 flex-1">
                          <Link to={`/candidates/${c.id}`} className="font-semibold text-fg hover:text-primary">{c.name}</Link>
                          <p className="truncate text-sm text-muted">{c.title} · {experienceLabel(c.experience_years)} · {c.location}</p>
                          <p className="mt-1 text-xs text-muted">{reasons.join(" · ")}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </CardBody>
              </Card>
            )}
            {data.jobs.length > 0 && (
              <Card>
                <CardHeader title="Jobs" />
                <CardBody className="py-0">
                  <ul className="divide-y divide-border">
                    {data.jobs.map((j) => (
                      <li key={j.id} className="flex items-center gap-3 py-3">
                        <Briefcase className="size-4 shrink-0 text-muted" aria-hidden />
                        <div className="min-w-0 flex-1">
                          {isCandidate(user) ? (
                            <span className="font-semibold text-fg">{j.title}</span>
                          ) : (
                            <Link to={`/jobs/${j.id}`} className="font-semibold text-fg hover:text-primary">{j.title}</Link>
                          )}
                          <p className="truncate text-sm text-muted">{j.company_name} · {j.location} · {j.workplace_type}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </CardBody>
              </Card>
            )}
          </div>
          <div className="flex flex-col gap-6">
            {data.skills.length > 0 && (
              <Card>
                <CardHeader title="Skills" />
                <CardBody className="flex flex-wrap gap-1.5">
                  {data.skills.map((s) => (
                    <span key={s.id} className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-xs text-fg" title={s.category}>
                      <Tag className="size-3 text-muted" aria-hidden />{s.name}
                    </span>
                  ))}
                </CardBody>
              </Card>
            )}
            {data.organizations.length > 0 && (
              <Card>
                <CardHeader title="Organizations" />
                <CardBody className="flex flex-col gap-2">
                  {data.organizations.map((o) => (
                    <p key={o.id} className="flex items-center gap-2 text-sm text-fg"><Building2 className="size-4 text-muted" aria-hidden />{o.name}<span className="text-muted">{o.domain}</span></p>
                  ))}
                </CardBody>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
