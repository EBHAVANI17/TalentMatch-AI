import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { FullPageSpinner } from "@/components/ui";
import type { User } from "@/lib/api/types";
import { useAuth } from "./AuthProvider";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <FullPageSpinner label="Checking your session" />;
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <>{children}</>;
}

/** Hides a route from users who don't pass `allow`; the API enforces the same rule. */
export function RequireRole({ allow, children }: { allow: (u: User | null) => boolean; children: ReactNode }) {
  const { user } = useAuth();
  if (!allow(user)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

/** Where to go after signing in: the page that sent the user to /login, else home. */
export function useReturnTo(): string {
  const location = useLocation();
  return (location.state as { from?: string } | null)?.from ?? "/";
}

export function RedirectIfAuthenticated({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const returnTo = useReturnTo();
  // This also handles the moment right after sign-in, so it must honour returnTo.
  if (status === "authenticated") return <Navigate to={returnTo} replace />;
  return <>{children}</>;
}
