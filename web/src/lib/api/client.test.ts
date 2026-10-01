import { afterEach, describe, expect, it, vi } from "vitest";
import { makeSession, makeUser, mockApi, signIn } from "@/test/utils";
import { ApiError, api, errorMessage } from "./client";
import { SESSION_EXPIRED_EVENT, getAccessToken, getRefreshToken } from "./session";

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("sends the access token", async () => {
    signIn();
    const { fetchMock } = mockApi({ "GET /auth/me": () => ({ body: makeUser() }) });
    await api("/auth/me");
    const headers = fetchMock.mock.calls[0][1]?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer access-1");
  });

  it("refreshes once on 401 and retries the request", async () => {
    signIn();
    let meCalls = 0;
    const { calls } = mockApi({
      "GET /auth/me": () => (++meCalls === 1 ? { status: 401, body: { detail: "expired" } } : { body: makeUser() }),
      "POST /auth/refresh": () => ({ body: { ...makeSession(), access_token: "access-2", refresh_token: "refresh-2" } }),
    });

    const me = await api<{ email: string }>("/auth/me");

    expect(me.email).toBe("sarah@anthropic.com");
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual(["GET /auth/me", "POST /auth/refresh", "GET /auth/me"]);
    expect(calls[1].body).toEqual({ refresh_token: "refresh-1" });
    expect(getAccessToken()).toBe("access-2");
    expect(getRefreshToken()).toBe("refresh-2");
  });

  it("clears the session and announces expiry when refresh fails", async () => {
    signIn();
    mockApi({
      "GET /auth/me": () => ({ status: 401, body: { detail: "expired" } }),
      "POST /auth/refresh": () => ({ status: 401, body: { detail: "Refresh token is invalid or expired" } }),
    });
    const expired = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, expired);

    await expect(api("/auth/me")).rejects.toBeInstanceOf(ApiError);
    expect(getAccessToken()).toBeNull();
    expect(expired).toHaveBeenCalledOnce();
    window.removeEventListener(SESSION_EXPIRED_EVENT, expired);
  });

  it("shares one refresh between concurrent 401s", async () => {
    signIn();
    let refreshes = 0;
    let authorized = false;
    mockApi({
      "GET /jobs": () => (authorized ? { body: [] } : { status: 401 }),
      "GET /notifications": () => (authorized ? { body: [] } : { status: 401 }),
      "POST /auth/refresh": () => {
        refreshes++;
        authorized = true;
        return { body: makeSession() };
      },
    });
    await Promise.all([api("/jobs"), api("/notifications")]);
    expect(refreshes).toBe(1);
  });
});

describe("errorMessage", () => {
  it("uses FastAPI string details", () => {
    expect(errorMessage({ detail: "Job requisition not found" }, 404)).toBe("Job requisition not found");
  });

  it("flattens validation errors into one sentence", () => {
    const body = { detail: [{ loc: ["body", "email"], msg: "value is not a valid email address" }] };
    expect(errorMessage(body, 422)).toBe("email: value is not a valid email address");
  });

  it("has friendly fallbacks", () => {
    expect(errorMessage(null, 429)).toMatch(/too many requests/i);
    expect(errorMessage(null, 503)).toMatch(/something went wrong/i);
  });
});
