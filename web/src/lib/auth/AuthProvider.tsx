import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, setActiveOrganization } from "@/lib/api/client";
import {
  SESSION_EXPIRED_EVENT,
  clearSession,
  getAccessToken,
  getStoredUser,
  saveSession,
  saveUser,
} from "@/lib/api/session";
import type { TokenResponse, User } from "@/lib/api/types";
import { announceOrgSwitch, onOrgSwitchElsewhere } from "./orgSync";

type Status = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  user: User | null;
  status: Status;
  login: (email: string, password: string) => Promise<User>;
  /** For flows that already returned a session (sign-up, accept invitation). */
  startSession: (session: TokenResponse) => User;
  refreshUser: () => Promise<void>;
  /** Work in another organization the user belongs to. Clears cached data and tells other tabs. */
  switchOrg: (organizationId: string) => Promise<User>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Reloading is the reliable way to drop another organization's data from a tab. */
function reloadPage() {
  window.location.reload();
}

export function AuthProvider({ children, onOrgSwitchedElsewhere = reloadPage }: { children: ReactNode; onOrgSwitchedElsewhere?: () => void }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(() => (getAccessToken() ? getStoredUser() : null));
  const [status, setStatus] = useState<Status>(() => (getAccessToken() ? "loading" : "anonymous"));

  // Every request from this tab says which organization the tab is showing.
  useEffect(() => setActiveOrganization(user?.organization_id), [user?.organization_id]);

  const endSession = useCallback(() => {
    clearSession();
    queryClient.clear();
    setActiveOrganization(null);
    setUser(null);
    setStatus("anonymous");
  }, [queryClient]);

  // Confirm a stored token is still valid (and pick up role/org changes).
  useEffect(() => {
    if (!getAccessToken()) return;
    api<User>("/auth/me")
      .then((me) => {
        saveUser(me);
        setUser(me);
        setStatus("authenticated");
      })
      .catch(endSession);
  }, [endSession]);

  useEffect(() => {
    window.addEventListener(SESSION_EXPIRED_EVENT, endSession);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, endSession);
  }, [endSession]);

  // Another tab switched the shared session to a different organization.
  useEffect(
    () =>
      onOrgSwitchElsewhere((organizationId) => {
        if (organizationId !== user?.organization_id) onOrgSwitchedElsewhere();
      }),
    [user?.organization_id, onOrgSwitchedElsewhere],
  );

  const startSession = useCallback((session: TokenResponse) => {
    saveSession(session);
    setActiveOrganization(session.user.organization_id);
    setUser(session.user);
    setStatus("authenticated");
    return session.user;
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const session = await api<TokenResponse>("/auth/login", {
        method: "POST",
        body: { email, password },
        auth: false,
      });
      return startSession(session);
    },
    [startSession],
  );

  const refreshUser = useCallback(async () => {
    const me = await api<User>("/auth/me");
    saveUser(me);
    setUser(me);
  }, []);

  const switchOrg = useCallback(
    async (organizationId: string) => {
      const session = await api<TokenResponse>("/auth/switch-org", {
        method: "POST",
        body: { organization_id: organizationId },
      });
      queryClient.clear(); // nothing cached from the previous organization survives
      const next = startSession(session);
      announceOrgSwitch(organizationId);
      return next;
    },
    [queryClient, startSession],
  );

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {
      // Already signed out server-side; clear locally regardless.
    }
    endSession();
  }, [endSession]);

  const value = useMemo(
    () => ({ user, status, login, startSession, refreshUser, switchOrg, logout }),
    [user, status, login, startSession, refreshUser, switchOrg, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
