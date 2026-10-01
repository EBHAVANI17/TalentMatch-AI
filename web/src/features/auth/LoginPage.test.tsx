import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeSession, makeUser, mockApi, renderApp } from "@/test/utils";

afterEach(() => vi.unstubAllGlobals());

const config = (demo_mode: boolean) => () => ({
  body: { app_name: "Talent Match", version: "2", environment: "test", demo_mode, require_email_verification: false, password_min_length: 8 },
});

const org = { id: "org_anthropic", name: "Anthropic", domain: "anthropic.com", plan_tier: "Enterprise", status: "Active", is_active: true,
  industry: "AI", max_recruiter_seats: 10, max_active_jobs: 50, monthly_ai_credits: 5000, monthly_ai_credits_used: 120 };

describe("sign in", () => {
  it("redirects signed-out visitors to the login page", async () => {
    mockApi({ "GET /config/public": config(false) });
    const { router } = renderApp("/team");
    await screen.findByRole("heading", { name: "Sign in" });
    expect(router.state.location.pathname).toBe("/login");
  });

  it("shows demo accounts only in demo mode", async () => {
    mockApi({ "GET /config/public": config(true) });
    renderApp("/login");
    expect(await screen.findByText("Demo accounts")).toBeInTheDocument();
  });

  it("hides demo accounts outside demo mode", async () => {
    mockApi({ "GET /config/public": config(false) });
    renderApp("/login");
    await screen.findByRole("heading", { name: "Sign in" });
    await waitFor(() => expect(screen.queryByText("Demo accounts")).not.toBeInTheDocument());
  });

  it("shows the server's error message on bad credentials", async () => {
    mockApi({
      "GET /config/public": config(false),
      "POST /auth/login": () => ({ status: 401, body: { detail: "Invalid email or password" } }),
    });
    renderApp("/login");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "sarah@anthropic.com");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
  });

  it("signs in, stores the session and returns to the page that was requested", async () => {
    const { calls } = mockApi({
      "GET /config/public": config(false),
      "POST /auth/login": () => ({ body: makeSession(makeUser()) }),
      "GET /organizations/org_anthropic/users": () => ({ body: [makeUser()] }),
      "GET /organizations/org_anthropic/invitations": () => ({ body: [] }),
      "GET /notifications": () => ({ body: [] }),
      "GET /organizations/org_anthropic": () => ({ body: org }),
    });
    const { router } = renderApp("/team");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "sarah@anthropic.com");
    await user.type(screen.getByLabelText("Password"), "anthropic123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Team" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/team");
    expect(localStorage.getItem("nexus-token")).toBe("access-1");
    expect(localStorage.getItem("nexus-refresh")).toBe("refresh-1");
    expect(calls.find((c) => c.path === "/auth/login")?.body).toEqual({ email: "sarah@anthropic.com", password: "anthropic123" });
  });
});
