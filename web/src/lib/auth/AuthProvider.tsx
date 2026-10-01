import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import {
  SESSION_EXPIRED_EVENT,
  clearSession,
  getAccessToken,
  getStoredUser,
  saveSession,
  saveUser,
} from "@/lib/api/session";
import type { TokenResponse, User } from "@/lib/api/types";

type Status = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  user: User | null;
  status: Status;
  login: (email: string, password: string) => Promise<User>;
  /** For flows that already returned a session (sign-up, accept invitation). */
  startSession: (session: TokenResponse) => User;
  refreshUser: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(() => (getAccessToken() ? getStoredUser() : null));
  const [status, setStatus] = useState<Status>(() => (getAccessToken() ? "loading" : "anonymous"));

  const endSession = useCallback(() => {
    clearSession();
    queryClient.clear();
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

  const startSession = useCallback((session: TokenResponse) => {
    saveSession(session);
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

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {
      // Already signed out server-side; clear locally regardless.
    }
    endSession();
  }, [endSession]);

  const value = useMemo(
    () => ({ user, status, login, startSession, refreshUser, logout }),
    [user, status, login, startSession, refreshUser, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
