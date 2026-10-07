import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { useToast } from "@/components/ui";
import { api } from "@/lib/api/client";
import type { MyOrganization } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/AuthProvider";
import { roleLabel } from "@/lib/auth/roles";

/** Shown to people who belong to more than one organization. */
export function OrgSwitcher() {
  const { user, switchOrg } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [switching, setSwitching] = useState(false);
  const enabled = !!user && (user.memberships_count ?? 0) > 1;
  const orgs = useQuery({
    queryKey: ["me", "organizations"],
    enabled,
    queryFn: () => api<MyOrganization[]>("/me/organizations"),
  });

  if (!enabled || !orgs.data) return null;
  const usable = orgs.data.filter((o) => o.status === "active" && o.organization_active);
  if (usable.length < 2) return null;

  async function onChange(organizationId: string) {
    if (organizationId === user?.organization_id) return;
    setSwitching(true);
    try {
      const next = await switchOrg(organizationId);
      const name = usable.find((o) => o.organization_id === organizationId)?.name ?? "the organization";
      navigate("/");
      toast.success(`Now working in ${name} as ${roleLabel(next.role)}`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSwitching(false);
    }
  }

  return (
    <div className="relative flex items-center">
      <Building2 className="pointer-events-none absolute left-2.5 size-4 text-muted" aria-hidden />
      <label htmlFor="org-switcher" className="sr-only">Organization</label>
      <select
        id="org-switcher"
        value={user?.organization_id ?? ""}
        disabled={switching}
        onChange={(e) => void onChange(e.target.value)}
        className="h-9 max-w-[12rem] truncate rounded-lg border border-border bg-surface-2 pl-8 pr-7 text-sm font-medium text-fg focus:border-primary focus:outline-none disabled:opacity-60 sm:max-w-[16rem]"
      >
        {usable.map((o) => (
          <option key={o.organization_id} value={o.organization_id}>
            {o.org_type === "client" ? `${o.name} (client)` : o.name} · {roleLabel(o.role)}
          </option>
        ))}
      </select>
    </div>
  );
}
