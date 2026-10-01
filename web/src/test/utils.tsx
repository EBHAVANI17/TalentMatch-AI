import { render } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AppProviders, makeQueryClient } from "@/app/providers";
import { routes } from "@/app/router";
import type { TokenResponse, User } from "@/lib/api/types";

type Handler = (init: RequestInit & { url: string }) => { status?: number; body?: unknown };

/**
 * Replace global fetch with a route table: { "GET /auth/me": () => ({ body: user }) }.
 * Paths are relative to /api/v1 and matched without the query string.
 */
export function mockApi(handlers: Record<string, Handler>) {
  const calls: Array<{ method: string; path: string; body?: unknown }> = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = (init.method ?? "GET").toUpperCase();
    const path = url.replace(/^.*\/api\/v1/, "").split("?")[0];
    const body = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({ method, path, body });
    const handler = handlers[`${method} ${path}`];
    if (!handler) return new Response(JSON.stringify({ detail: `No mock for ${method} ${path}` }), { status: 404 });
    const { status = 200, body: resBody } = handler({ ...init, url });
    return new Response(resBody === undefined ? "" : JSON.stringify(resBody), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export function renderApp(path = "/") {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const utils = render(
    <AppProviders queryClient={makeQueryClient()}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...utils, router };
}

export function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: "usr_1",
    email: "sarah@anthropic.com",
    full_name: "Sarah Jenkins",
    role: "EMPLOYER_ADMIN",
    organization_id: "org_anthropic",
    avatar_url: "",
    status: "Active",
    is_active: true,
    email_verified: true,
    created_at: null,
    ...overrides,
  };
}

export function makeSession(user: User = makeUser()): TokenResponse {
  return { access_token: "access-1", refresh_token: "refresh-1", token_type: "bearer", expires_in: 3600, user };
}

export function signIn(user: User = makeUser()) {
  localStorage.setItem("nexus-token", "access-1");
  localStorage.setItem("nexus-refresh", "refresh-1");
  localStorage.setItem("nexus-user", JSON.stringify(user));
}
