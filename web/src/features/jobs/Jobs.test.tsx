import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeUser, mockApi, renderApp, signIn } from "@/test/utils";

afterEach(() => vi.unstubAllGlobals());

const job = {
  id: "job_1", organization_id: "org_anthropic", company_name: "Anthropic", company_domain: "anthropic.com", company_logo: "briefcase",
  title: "Platform Engineer", department: "Infrastructure", description: "Run the platform.", key_responsibilities: ["Keep it up"],
  responsibilities: [], required_skills: ["Go"], preferred_skills: ["Terraform"], min_experience_years: 4, location: "Remote",
  workplace_type: "Remote", salary_min: 150000, salary_max: 190000, equity: "", required_education: "Bachelor's", urgency: "High",
  status: "Draft", benefits: [], applicants_count: 0, employment_type: "Full-time", openings: 1, max_experience_years: null,
  seniority: "", industry: "", application_deadline: null, published_at: null, closed_at: null, posted_date: "", created_at: null, updated_at: null,
};

const base = {
  "GET /auth/me": () => ({ body: makeUser() }),
  "GET /notifications": () => ({ body: [] }),
  "GET /pipeline/stages": () => ({ body: [{ name: "Applied", kind: "active" }, { name: "Shortlisted", kind: "active" }, { name: "Hired", kind: "hired" }, { name: "Rejected", kind: "rejected" }] }),
};

describe("job form", () => {
  it("validates ranges before calling the API", async () => {
    signIn();
    const { calls } = mockApi(base);
    renderApp("/jobs/new");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Job title"), "Platform Engineer");
    await user.type(screen.getByLabelText("Description"), "Run the platform.");
    await user.type(screen.getByLabelText("Salary from"), "200000");
    await user.type(screen.getByLabelText("Salary to"), "100000");
    await user.click(screen.getByRole("button", { name: "Publish job" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Minimum salary can't be higher");
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("saves a draft with skills and responsibilities", async () => {
    signIn();
    const { calls } = mockApi({ ...base, "POST /jobs": () => ({ body: job }), "GET /jobs/job_1": () => ({ body: job }), "GET /applications": () => ({ body: [] }) });
    const { router } = renderApp("/jobs/new");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Job title"), "Platform Engineer");
    await user.type(screen.getByLabelText("Description"), "Run the platform.");
    await user.type(screen.getByLabelText("Responsibilities"), "Keep it up{enter}Own on-call");
    await user.type(screen.getByLabelText("Required skills"), "Go{enter}");
    await user.click(screen.getByRole("button", { name: "Save as draft" }));

    await screen.findByRole("heading", { name: "Platform Engineer" });
    const body = calls.find((c) => c.method === "POST" && c.path === "/jobs")?.body as Record<string, unknown>;
    expect(body).toMatchObject({ status: "Draft", required_skills: ["Go"], key_responsibilities: ["Keep it up", "Own on-call"] });
    expect(router.state.location.pathname).toBe("/jobs/job_1");
  });
});

describe("job detail", () => {
  it("offers lifecycle actions that fit the status", async () => {
    signIn();
    let current: Record<string, unknown> = { ...job };
    const { calls } = mockApi({
      ...base,
      "GET /jobs/job_1": () => ({ body: current }),
      "GET /applications": () => ({ body: [] }),
      "POST /jobs/job_1/publish": () => {
        current = { ...job, status: "Active", published_at: "2026-10-01T00:00:00" };
        return { body: current };
      },
    });
    renderApp("/jobs/job_1");
    const user = userEvent.setup();
    expect(await screen.findByText("Draft")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Publish" }));
    expect(await screen.findByText("Job published")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/jobs/job_1/publish")).toBe(true);
    expect(await screen.findByRole("button", { name: "Close" })).toBeInTheDocument();
  });

  it("asks for confirmation before closing", async () => {
    signIn();
    const { calls } = mockApi({ ...base, "GET /jobs/job_1": () => ({ body: { ...job, status: "Active" } }), "GET /applications": () => ({ body: [] }) });
    renderApp("/jobs/job_1");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Close" }));
    const dialog = await screen.findByRole("dialog", { name: "Close this job?" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(calls.some((c) => c.path === "/jobs/job_1/close")).toBe(false);
  });
});

describe("candidates", () => {
  it("sends every required skill as its own filter", async () => {
    signIn();
    const { fetchMock } = mockApi({ ...base, "GET /candidates": () => ({ body: [] }) });
    renderApp("/candidates");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Must have skills"), "Go{enter}AWS{enter}");
    await screen.findByText("No candidates match these filters");
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes("skills=Go&skills=AWS"))).toBe(true);
  });
});
