import { Bot, Briefcase, Home, LayoutDashboard, Sparkles, UserRound, Users, UsersRound, type LucideIcon } from "lucide-react";
import type { User } from "@/lib/api/types";
import { canUseCopilot, isCandidate, isOrgAdmin, isOrgMember, isSuperAdmin } from "@/lib/auth/roles";

const hiringTeam = (u: User | null) => isOrgMember(u) || isSuperAdmin(u);

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
  { to: "/", label: "Dashboard", icon: LayoutDashboard, visible: hiringTeam },
  { to: "/", label: "Home", icon: Home, visible: isCandidate },
  { to: "/jobs", label: "Jobs", icon: Briefcase, visible: hiringTeam },
  { to: "/talent-match", label: "Talent Match", icon: Sparkles, visible: hiringTeam },
  { to: "/candidates", label: "Candidates", icon: UsersRound, visible: hiringTeam },
  { to: "/copilot", label: "Copilot", icon: Bot, visible: canUseCopilot },
  { to: "/jobs-for-you", label: "Jobs for you", icon: Sparkles, visible: isCandidate },
  { to: "/profile", label: "My profile", icon: UserRound, visible: isCandidate },
  { to: "/team", label: "Team", icon: Users, visible: (u) => isOrgAdmin(u) || isSuperAdmin(u) },
];

/** The classic (legacy) workspace, still served at the site root. */
export const CLASSIC_WORKSPACE_URL = "/";
