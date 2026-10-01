import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MailPlus, UserPlus } from "lucide-react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Input,
  Modal,
  Skeleton,
  useToast,
} from "@/components/ui";
import { api } from "@/lib/api/client";
import type { Invitation, User } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/AuthProvider";
import { roleLabel } from "@/lib/auth/roles";
import { OrganizationCard } from "@/features/home/HomePage";

const INVITABLE_ROLES = ["RECRUITER", "HIRING_MANAGER", "INTERVIEWER", "ANALYST", "ORG_ADMIN"] as const;

const formatDate = (value?: string | null) => (value ? new Date(value).toLocaleDateString() : "");

function TableSkeleton() {
  return (
    <div className="flex flex-col gap-2">
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-10" />
      ))}
    </div>
  );
}

function InviteDialog({ orgId, open, onClose }: { orgId: string; open: boolean; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<string>("RECRUITER");
  const invite = useMutation({
    mutationFn: () => api<Invitation>(`/organizations/${orgId}/invitations`, { method: "POST", body: { email, role } }),
    onSuccess: (inv) => {
      toast.success(`Invitation sent to ${inv.email}`);
      void queryClient.invalidateQueries({ queryKey: ["invitations", orgId] });
      setEmail("");
      onClose();
    },
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    invite.mutate();
  }

  return (
    <Modal open={open} title="Invite a team member" onClose={onClose}>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        {invite.isError && <Alert>{invite.error.message}</Alert>}
        <Input label="Work email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <div className="flex flex-col gap-1.5">
          <label htmlFor="invite-role" className="text-sm font-medium text-fg">
            Role
          </label>
          <select
            id="invite-role"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-fg focus:border-primary focus:outline-none"
          >
            {INVITABLE_ROLES.map((r) => (
              <option key={r} value={r}>
                {roleLabel(r)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={invite.isPending} disabled={!email} icon={<MailPlus className="size-4" aria-hidden />}>
            Send invitation
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function TeamPage() {
  const { user } = useAuth();
  const orgId = user?.organization_id;
  const toast = useToast();
  const queryClient = useQueryClient();
  const [inviteOpen, setInviteOpen] = useState(false);
  const [toRevoke, setToRevoke] = useState<Invitation | null>(null);

  const members = useQuery({
    queryKey: ["members", orgId],
    queryFn: () => api<User[]>(`/organizations/${orgId}/users`),
    enabled: !!orgId,
  });
  const invitations = useQuery({
    queryKey: ["invitations", orgId],
    queryFn: () => api<Invitation[]>(`/organizations/${orgId}/invitations`),
    enabled: !!orgId,
  });
  const revoke = useMutation({
    mutationFn: (inv: Invitation) => api<Invitation>(`/organizations/${orgId}/invitations/${inv.id}`, { method: "DELETE" }),
    onSuccess: (inv) => {
      toast.success(`Invitation for ${inv.email} revoked`);
      void queryClient.invalidateQueries({ queryKey: ["invitations", orgId] });
      setToRevoke(null);
    },
    onError: (err) => toast.error(err.message),
  });

  if (!orgId) {
    return (
      <Card>
        <EmptyState title="No organization" description="Platform admins manage teams from the classic admin console for now." />
      </Card>
    );
  }

  const pending = invitations.data?.filter((i) => i.status === "pending") ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold text-fg">Team</h1>
          <p className="mt-1 text-sm text-muted">People who can work in your organization's hiring workspace.</p>
        </div>
        <Button icon={<UserPlus className="size-4" aria-hidden />} onClick={() => setInviteOpen(true)}>
          Invite member
        </Button>
      </div>

      <OrganizationCard orgId={orgId} />

      <Card>
        <CardHeader
          title="Members"
          description={members.data ? `${members.data.length} ${members.data.length === 1 ? "person" : "people"}` : undefined}
        />
        <CardBody>
          {members.isLoading ? (
            <TableSkeleton />
          ) : members.isError ? (
            <ErrorState message={members.error.message} onRetry={() => void members.refetch()} />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th className="py-2 pr-4 font-semibold">Name</th>
                    <th className="hidden py-2 pr-4 font-semibold sm:table-cell">Email</th>
                    <th className="hidden py-2 pr-4 font-semibold sm:table-cell">Role</th>
                    <th className="py-2 font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {members.data?.map((m) => (
                    <tr key={m.id} className="border-t border-border">
                      <td className="py-3 pr-4">
                        <span className="block font-medium text-fg">{m.full_name}</span>
                        {/* On small screens email and role sit under the name instead of their own columns */}
                        <span className="block text-xs text-muted sm:hidden">{m.email}</span>
                        <span className="block text-xs text-muted sm:hidden">{roleLabel(m.role)}</span>
                      </td>
                      <td className="hidden py-3 pr-4 text-muted sm:table-cell">{m.email}</td>
                      <td className="nowrap hidden py-3 pr-4 sm:table-cell">{roleLabel(m.role)}</td>
                      <td className="py-3">
                        <Badge tone={m.is_active ? "success" : "danger"}>{m.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Pending invitations" description="Invitations expire after 7 days." />
        <CardBody>
          {invitations.isLoading ? (
            <TableSkeleton />
          ) : invitations.isError ? (
            <ErrorState message={invitations.error.message} onRetry={() => void invitations.refetch()} />
          ) : pending.length === 0 ? (
            <EmptyState
              title="No pending invitations"
              description="Invite recruiters, hiring managers and interviewers to collaborate on hiring."
              action={
                <Button size="sm" variant="secondary" onClick={() => setInviteOpen(true)}>
                  Invite member
                </Button>
              }
            />
          ) : (
            <ul className="divide-y divide-border">
              {pending.map((inv) => (
                <li key={inv.id} className="flex items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-fg">{inv.email}</p>
                    <p className="text-xs text-muted">
                      {roleLabel(inv.role)} · expires {formatDate(inv.expires_at)}
                    </p>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => setToRevoke(inv)}>
                    Revoke
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <InviteDialog orgId={orgId} open={inviteOpen} onClose={() => setInviteOpen(false)} />
      <ConfirmDialog
        open={!!toRevoke}
        title="Revoke invitation?"
        message={`The link sent to ${toRevoke?.email ?? ""} will stop working. You can invite them again later.`}
        confirmLabel="Revoke"
        destructive
        loading={revoke.isPending}
        onConfirm={() => toRevoke && revoke.mutate(toRevoke)}
        onCancel={() => setToRevoke(null)}
      />
    </div>
  );
}
