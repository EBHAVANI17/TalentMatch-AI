import { SESSION_EXPIRED_EVENT, clearSession, getAccessToken, getRefreshToken, saveSession } from "./session";
import type { TokenResponse } from "./types";

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Query;
  signal?: AbortSignal;
  /** Send the access token and refresh it on 401 (default true). */
  auth?: boolean;
}

function buildUrl(path: string, query?: Query): string {
  const url = `${API_BASE}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

/** Turns FastAPI error bodies ({detail: string | [{msg}]}) into one readable sentence. */
export function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const field = Array.isArray(d.loc) ? d.loc.filter((p) => p !== "body").join(".") : "";
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  if (status === 429) return "Too many requests. Please wait a moment and try again.";
  if (status >= 500) return "Something went wrong on our side. Please try again.";
  return `Request failed (${status})`;
}

// Only one refresh call at a time; concurrent 401s wait for the same result.
let refreshInFlight: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  refreshInFlight ??= (async () => {
    try {
      const res = await fetch(buildUrl("/auth/refresh"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return false;
      saveSession((await res.json()) as TokenResponse);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const isForm = options.body instanceof FormData;
  if (options.body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  const token = options.auth === false ? null : getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  return fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : isForm ? (options.body as FormData) : JSON.stringify(options.body),
    signal: options.signal,
  });
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let res = await send(path, options);

  if (res.status === 401 && options.auth !== false && getAccessToken()) {
    if (await refreshSession()) {
      res = await send(path, options);
    } else {
      clearSession();
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
  }

  const text = await res.text();
  const body = text ? safeJson(text) : null;
  if (!res.ok) throw new ApiError(res.status, errorMessage(body, res.status), body);
  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
