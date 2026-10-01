/**
 * Session storage. The keys are shared with the legacy UI (frontend/index.html),
 * so signing in to either app signs you in to both.
 */
import type { TokenResponse, User } from "./types";

const TOKEN_KEY = "nexus-token";
const USER_KEY = "nexus-user";
const REFRESH_KEY = "nexus-refresh";

export const SESSION_EXPIRED_EVENT = "tm:session-expired";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function getAccessToken(): string | null {
  return read(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return read(REFRESH_KEY);
}

export function getStoredUser(): User | null {
  const raw = read(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function saveSession(session: TokenResponse): void {
  localStorage.setItem(TOKEN_KEY, session.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(session.user));
  if (session.refresh_token) localStorage.setItem(REFRESH_KEY, session.refresh_token);
}

export function saveUser(user: User): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession(): void {
  [TOKEN_KEY, USER_KEY, REFRESH_KEY].forEach((key) => localStorage.removeItem(key));
}
