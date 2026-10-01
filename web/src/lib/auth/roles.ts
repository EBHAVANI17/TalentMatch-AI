/**
 * Role helpers for showing/hiding UI. The API enforces the real rules
 * (backend/app/core/tenancy.py); these only decide what to display.
 */
import type { User } from "@/lib/api/types";

export const ORG_ROLES = ["ORG_ADMIN", "EMPLOYER_ADMIN", "RECRUITER", "HIRING_MANAGER", "INTERVIEWER", "ANALYST"] as const;
export const ORG_ADMIN_ROLES = ["ORG_ADMIN", "EMPLOYER_ADMIN"] as const;

export const isSuperAdmin = (u: User | null) => u?.role === "SUPER_ADMIN";
export const isCandidate = (u: User | null) => u?.role === "CANDIDATE";
export const isOrgMember = (u: User | null) =>
  !!u?.organization_id && (ORG_ROLES as readonly string[]).includes(u.role);
export const isOrgAdmin = (u: User | null) =>
  !!u?.organization_id && (ORG_ADMIN_ROLES as readonly string[]).includes(u.role);

const ROLE_LABELS: Record<string, string> = {
  SUPER_ADMIN: "Platform Admin",
  ORG_ADMIN: "Organization Admin",
  EMPLOYER_ADMIN: "Organization Admin",
  RECRUITER: "Recruiter",
  HIRING_MANAGER: "Hiring Manager",
  INTERVIEWER: "Interviewer",
  ANALYST: "Analyst",
  CANDIDATE: "Candidate",
};

export const roleLabel = (role: string) => ROLE_LABELS[role] ?? role;
