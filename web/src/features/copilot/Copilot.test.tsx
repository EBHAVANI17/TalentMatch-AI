import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CopilotMessage } from "@/lib/api/types";
import { makeUser, mockApi, renderApp, signIn } from "@/test/utils";
import { MessageContent } from "./MessageContent";

afterEach(() => vi.unstubAllGlobals());

const answer: CopilotMessage = {
  id: "cmsg_2",
  role: "assistant",
  content: "Best matches for [J1]:\n- [C1] 80% (Strong fit)\n- [C2] 54% (Partial fit)",
  citations: [
    { ref: "J1", kind: "job", id: "job_001", label: "Staff AI Engineer", url: "/jobs/job_001", available: true },
    { ref: "C1", kind: "candidate", id: "cand_001", label: "Aarav Sharma", url: "/candidates/cand_001", available: true },
    { ref: "C2", kind: "candidate", id: "", label: "Unavailable record", url: "", available: false },
  ],
  follow_ups: ["Tell me more about [C1]"],
  method: "rules",
  notice: "Answered with built-in rules (no AI provider was available), from your organization's records.",
  created_at: "2026-10-07T10:00:00",
};

function recruiterApi(extra = {}) {
  const recruiter = makeUser({ role: "RECRUITER" });
  signIn(recruiter);
  return mockApi({
    "GET /auth/me": () => ({ body: recruiter }),
    "GET /notifications": () => ({ body: [] }),
    "GET /copilot/conversations": () => ({ body: [] }),
    "POST /copilot/messages": () => ({ body: { conversation_id: "conv_1", message: answer } }),
    ...extra,
  });
}

describe("copilot message rendering", () => {
  it("turns references into links and never links records the user can't see", () => {
    render(
      <MemoryRouter>
        <MessageContent text={answer.content} citations={answer.citations} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Aarav Sharma" })).toHaveAttribute("href", "/candidates/cand_001");
    expect(screen.getByRole("link", { name: "Staff AI Engineer" })).toHaveAttribute("href", "/jobs/job_001");
    expect(screen.queryByRole("link", { name: "Unavailable record" })).not.toBeInTheDocument();
    expect(screen.getByText("Unavailable record")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByText(/\[C1\]/)).not.toBeInTheDocument();
  });
});

describe("copilot page", () => {
  it("asks a suggested question and shows the cited answer with how it was produced", async () => {
    const { calls } = recruiterApi();
    renderApp("/copilot");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "List my jobs" }));
    expect(await screen.findByRole("link", { name: "Aarav Sharma" })).toBeInTheDocument();
    expect(screen.getByText(/built-in rules/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tell me more about Aarav Sharma" })).toBeInTheDocument();
    const body = calls.find((c) => c.method === "POST")?.body as Record<string, unknown>;
    expect(body).toMatchObject({ message: "List my jobs", conversation_id: null });
  });
});

describe("copilot panel", () => {
  it("opens from the header, sends the question, and toggles with Ctrl+J", async () => {
    const { calls } = recruiterApi();
    renderApp("/nowhere");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Copilot" }));
    const panel = screen.getByRole("dialog", { name: "Copilot" });
    await user.type(within(panel).getByLabelText("Ask the copilot"), "Who should I interview?{Enter}");
    expect(await within(panel).findByRole("link", { name: "Aarav Sharma" })).toBeInTheDocument();
    expect(within(panel).getByText("Who should I interview?")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({ message: "Who should I interview?", context: {} });

    await user.keyboard("{Control>}j{/Control}");
    expect(screen.queryByRole("dialog", { name: "Copilot" })).not.toBeInTheDocument();
  });

  it("is not offered to candidates or interviewers", async () => {
    for (const role of ["CANDIDATE", "INTERVIEWER"]) {
      const person = makeUser({ role, organization_id: role === "CANDIDATE" ? null : "org_anthropic" });
      signIn(person);
      mockApi({ "GET /auth/me": () => ({ body: person }), "GET /notifications": () => ({ body: [] }) });
      const { unmount } = renderApp("/nowhere");
      await screen.findByText("Page not found");
      expect(screen.queryByRole("button", { name: "Copilot" })).not.toBeInTheDocument();
      unmount();
    }
  });
});
