import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeUser, mockApi, renderApp, signIn } from "@/test/utils";

afterEach(() => vi.unstubAllGlobals());

const pendingInvite = {
  id: "inv_1",
  organization_id: "org_anthropic",
  email: "pat@anthropic.com",
  role: "RECRUITER",
  status: "pending",
  expires_at: "2030-01-01T00:00:00",
  created_at: "2029-12-25T00:00:00",
};

function baseHandlers(invitations: unknown[] = []) {
  return {
    "GET /auth/me": () => ({ body: makeUser() }),
    "GET /notifications": () => ({ body: [] }),
    "GET /organizations/org_anthropic/users": () => ({
      body: [makeUser(), makeUser({ id: "usr_2", full_name: "Lee Park", email: "lee@anthropic.com", role: "RECRUITER" })],
    }),
    "GET /organizations/org_anthropic/invitations": () => ({ body: invitations }),
  };
}

describe("Team page", () => {
  it("lists members and pending invitations", async () => {
    signIn();
    mockApi(baseHandlers([pendingInvite, { ...pendingInvite, id: "inv_2", email: "old@anthropic.com", status: "revoked" }]));
    renderApp("/team");

    expect(await screen.findByText("Lee Park")).toBeInTheDocument();
    expect(await screen.findByText("pat@anthropic.com")).toBeInTheDocument();
    expect(screen.queryByText("old@anthropic.com")).not.toBeInTheDocument(); // revoked invites are hidden
  });

  it("sends an invitation", async () => {
    signIn();
    const { calls } = mockApi({
      ...baseHandlers(),
      "POST /organizations/org_anthropic/invitations": () => ({ status: 201, body: { ...pendingInvite, email: "new@anthropic.com", role: "HIRING_MANAGER" } }),
    });
    renderApp("/team");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Invite member" }));
    const dialog = await screen.findByRole("dialog", { name: "Invite a team member" });
    await user.type(within(dialog).getByLabelText("Work email"), "new@anthropic.com");
    await user.selectOptions(within(dialog).getByLabelText("Role"), "HIRING_MANAGER");
    await user.click(within(dialog).getByRole("button", { name: "Send invitation" }));

    expect(await screen.findByText("Invitation sent to new@anthropic.com")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ email: "new@anthropic.com", role: "HIRING_MANAGER" });
  });

  it("shows the API's reason when an invite is refused", async () => {
    signIn();
    mockApi({
      ...baseHandlers(),
      "POST /organizations/org_anthropic/invitations": () => ({ status: 402, body: { detail: "Seat limit reached (1). Upgrade the plan or remove a member." } }),
    });
    renderApp("/team");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Invite member" }));
    const dialog = await screen.findByRole("dialog", { name: "Invite a team member" });
    await user.type(within(dialog).getByLabelText("Work email"), "x@anthropic.com");
    await user.click(within(dialog).getByRole("button", { name: "Send invitation" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Seat limit reached");
  });

  it("is not available to recruiters", async () => {
    const recruiter = makeUser({ role: "RECRUITER" });
    signIn(recruiter);
    mockApi({
      ...baseHandlers(),
      "GET /auth/me": () => ({ body: recruiter }),
      "GET /organizations/org_anthropic": () => ({ body: { id: "org_anthropic", name: "Anthropic", domain: "anthropic.com" } }),
    });
    const { router } = renderApp("/team");
    await screen.findByRole("heading", { name: /Welcome/ });
    expect(router.state.location.pathname).toBe("/");
    expect(screen.queryByRole("link", { name: "Team" })).not.toBeInTheDocument();
  });
});
