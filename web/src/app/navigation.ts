import { Home, Users, type LucideIcon } from "lucide-react";
import type { User } from "@/lib/api/types";
import { isOrgAdmin, isSuperAdmin } from "@/lib/auth/roles";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  visible: (user: User | null) => boolean;
}

/**
 * Screens available in the new app. Modules join this list as they are migrated
 * from the classic workspace (frontend/index.html); see docs/DEVELOPMENT.md.
 */
export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Home", icon: Home, visible: () => true },
  { to: "/team", label: "Team", icon: Users, visible: (u) => isOrgAdmin(u) || isSuperAdmin(u) },
];

/** The classic (legacy) workspace, still served at the site root. */
export const CLASSIC_WORKSPACE_URL = "/";
