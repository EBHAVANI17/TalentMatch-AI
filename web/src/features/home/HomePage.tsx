import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowUpRight, BadgeCheck, Briefcase, Building2, Cpu, MailWarning, Users } from "lucide-react";
import { Badge, Button, Card, CardBody, CardHeader, ErrorState, Skeleton, useToast } from "@/components/ui";
import { CLASSIC_WORKSPACE_URL } from "@/app/navigation";
import { api } from "@/lib/api/client";
import type { MessageResponse, Organization } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/AuthProvider";
import { isCandidate, isOrgMember, roleLabel } from "@/lib/auth/roles";

function Stat({ icon: Icon, label, value, hint }: { icon: typeof Users; label: string; value: string; hint?: string }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border p-4">
      <div className="rounded-lg bg-primary-soft p-2 text-primary">
        <Icon className="size-4" aria-hidden />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
        <p className="font-display text-lg font-semibold text-fg">{value}</p>
        {hint && <p className="text-xs text-muted">{hint}</p>}
      </div>
    </div>
  );
}

function EmailVerificationNotice() {
  const toast = useToast();
  const resend = useMutation({
    mutationFn: () => api<MessageResponse>("/auth/resend-verification", { method: "POST" }),
    onSuccess: (res) => toast.success(res.message),
    onError: (err) => toast.error(err.message),
  });
  return (
    <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning/30 bg-warning-soft px-4 py-3">
      <p className="flex items-center gap-2 text-sm text-warning">
        <MailWarning className="size-4 shrink-0" aria-hidden />
        Please confirm your email address. We sent you a link when you signed up.
      </p>
      <Button size="sm" variant="secondary" loading={resend.isPending} onClick={() => resend.mutate()}>
        Resend email
      </Button>
    </div>
  );
}

function OrganizationCard({ orgId }: { orgId: string }) {
  const { data: org, isLoading, isError, refetch } = useQuery({
    queryKey: ["organization", orgId],
    queryFn: () => api<Organization>(`/organizations/${orgId}`),
  });

  return (
    <Card>
      <CardHeader
        title="Your organization"
        description={org ? `${org.name} · ${org.domain}` : undefined}
        actions={org && <Badge tone={org.is_active ? "success" : "danger"}>{org.status}</Badge>}
      />
      <CardBody>
        {isLoading ? (
          <div className="grid gap-3 sm:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
        ) : isError || !org ? (
          <ErrorState message="Couldn't load your organization." onRetry={() => void refetch()} />
        ) : (
          <div className="grid gap-3 sm:grid-cols-3">
            <Stat icon={Building2} label="Plan" value={org.plan_tier} hint={org.industry} />
            <Stat icon={Users} label="Seats" value={String(org.max_recruiter_seats)} hint="Team members included" />
            <Stat
              icon={Cpu}
              label="AI credits"
              value={`${org.monthly_ai_credits_used.toLocaleString()} / ${org.monthly_ai_credits.toLocaleString()}`}
              hint="Used this month"
            />
          </div>
        )}
      </CardBody>
    </Card>
  );
}

const CLASSIC_LINKS_BY_AUDIENCE = {
  org: ["Recruiting dashboard", "Job requisitions", "Candidate pipeline", "Talent match results", "AI sourcing and outreach"],
  candidate: ["Recommended jobs", "Applications", "Resume studio", "Interview preparation", "Learning roadmap"],
  admin: ["Platform health", "Organizations and plans", "Users", "Audit logs", "Skill taxonomy"],
};

export function HomePage() {
  const { user } = useAuth();
  if (!user) return null;

  const audience = isCandidate(user) ? "candidate" : isOrgMember(user) ? "org" : "admin";
  const firstName = user.full_name.split(" ")[0];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl font-semibold text-fg">Welcome, {firstName}</h1>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
          {roleLabel(user.role)}
          {user.email_verified && (
            <span className="inline-flex items-center gap-1 text-success">
              <BadgeCheck className="size-4" aria-hidden /> Email verified
            </span>
          )}
        </p>
      </div>

      {!user.email_verified && <EmailVerificationNotice />}

      {user.organization_id && <OrganizationCard orgId={user.organization_id} />}

      <Card>
        <CardHeader
          title="Your workspace"
          description="These tools are in the classic workspace while they move to this new interface. You're already signed in there."
        />
        <CardBody>
          <ul className="grid gap-2 sm:grid-cols-2">
            {CLASSIC_LINKS_BY_AUDIENCE[audience].map((label) => (
              <li key={label}>
                <a
                  href={CLASSIC_WORKSPACE_URL}
                  className="group flex items-center justify-between rounded-lg border border-border px-4 py-3 text-sm font-medium text-fg hover:border-primary hover:text-primary"
                >
                  <span className="flex items-center gap-2">
                    <Briefcase className="size-4 text-muted group-hover:text-primary" aria-hidden />
                    {label}
                  </span>
                  <ArrowUpRight className="size-4 text-muted group-hover:text-primary" aria-hidden />
                </a>
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>
    </div>
  );
}
