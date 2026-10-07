import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeQueryClient } from "@/app/providers";
import { api, setActiveOrganization } from "@/lib/api/client";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import type { MyOrganization, User } from "@/lib/api/types";
import { makeSession, makeUser, mockApi, renderApp, signIn } from "@/test/utils";

afterEach(() => {
  vi.unstubAllGlobals();
  setActiveOrganization(null);
});

const orgs: MyOrganization[] = [
  { organization_id: "org_anthropic", name: "Anthropic AI", org_type: "standalone", parent_id: null, role: "RECRUITER", status: "active", organization_active: true, is_current: true },
  { organization_id: "org_client", name: "Client Co", org_type: "client", parent_id: "org_parent", role: "ORG_ADMIN", status: "active", organization_active: true, is_current: false },
];

function headerOf(call: unknown[], name: string): string | undefined {
  return ((call[1] as RequestInit | undefined)?.headers as Record<string, string> | undefined)?.[name];
}

describe("organization switcher", () => {
  it("switches organization, clears cached data and tags later writes with the new org", async () => {
    const recruiter = makeUser({ role: "RECRUITER", memberships_count: 2 });
    const switched: User = { ...recruiter, organization_id: "org_client", active_organization_id: "org_client", role: "ORG_ADMIN" };
    signIn(recruiter);
    const { calls, fetchMock } = mockApi({
      "GET /auth/me": () => ({ body: recruiter }),
      "GET /notifications": () => ({ body: [] }),
      "GET /me/organizations": () => ({ body: orgs }),
      "POST /auth/switch-org": () => ({ body: { ...makeSession(switched), access_token: "access-org-client" } }),
    });
    renderApp("/nowhere");
    const user = userEvent.setup();

    const select = await screen.findByLabelText("Organization");
    expect(screen.getByRole("option", { name: /Client Co \(client\) · Organization Admin/ })).toBeInTheDocument();
    const orgListFetchesBefore = calls.filter((c) => c.path === "/me/organizations").length;
    await user.selectOptions(select, "org_client");

    await screen.findByText(/Now working in Client Co as Organization Admin/);
    expect(calls.find((c) => c.path === "/auth/switch-org")?.body).toEqual({ organization_id: "org_client" });
    expect(localStorage.getItem("nexus-token")).toBe("access-org-client");
    // The query cache was cleared, so data is fetched again for the new organization
    await waitFor(() => expect(calls.filter((c) => c.path === "/me/organizations").length).toBeGreaterThan(orgListFetchesBefore));

    await act(() => api("/copilot/messages", { method: "POST", body: { message: "hi" } }).catch(() => undefined));
    const lastWrite = fetchMock.mock.calls.filter((c) => (c[1] as RequestInit)?.method === "POST").at(-1)!;
    expect(headerOf(lastWrite, "X-Org-Id")).toBe("org_client");
  });

  it("is hidden for people in one organization", async () => {
    const recruiter = makeUser({ role: "RECRUITER", memberships_count: 1 });
    signIn(recruiter);
    mockApi({ "GET /auth/me": () => ({ body: recruiter }), "GET /notifications": () => ({ body: [] }) });
    renderApp("/nowhere");
    await screen.findByText("Page not found");
    expect(screen.queryByLabelText("Organization")).not.toBeInTheDocument();
  });
});

describe("cross-tab organization changes", () => {
  it("reloads this tab when another tab switches to a different organization", async () => {
    const recruiter = makeUser({ role: "RECRUITER", memberships_count: 2 });
    signIn(recruiter);
    mockApi({ "GET /auth/me": () => ({ body: recruiter }) });
    const reload = vi.fn();
    render(
      <QueryClientProvider client={makeQueryClient()}>
        <AuthProvider onOrgSwitchedElsewhere={reload}>
          <span>app</span>
        </AuthProvider>
      </QueryClientProvider>,
    );
    await screen.findByText("app");
    const fire = (organizationId: string) =>
      window.dispatchEvent(new StorageEvent("storage", {
        key: "tm-org-switch",
        newValue: JSON.stringify({ type: "org-switched", organizationId, from: "other-tab", at: Date.now() }),
      }));

    act(() => fire("org_anthropic")); // same organization as this tab: nothing to do
    expect(reload).not.toHaveBeenCalled();
    act(() => fire("org_client"));
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
  });

  it("sends X-Org-Id only with a session", async () => {
    const { fetchMock } = mockApi({ "POST /thing": () => ({ body: {} }) });
    setActiveOrganization("org_anthropic");
    await api("/thing", { method: "POST", body: {} });
    expect(headerOf(fetchMock.mock.calls[0], "X-Org-Id")).toBeUndefined(); // no token stored
    signIn();
    await api("/thing", { method: "POST", body: {} });
    expect(headerOf(fetchMock.mock.calls[1], "X-Org-Id")).toBe("org_anthropic");
  });
});
