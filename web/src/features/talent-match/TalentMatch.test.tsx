import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeUser, mockApi, renderApp, signIn } from "@/test/utils";

afterEach(() => vi.unstubAllGlobals());

const job = { id: "job_1", title: "Platform Engineer", status: "Active", company_name: "Anthropic", location: "Remote", workplace_type: "Remote",
  required_skills: ["Kubernetes"], preferred_skills: [], key_responsibilities: [], benefits: [], organization_id: "org_anthropic" };

const match = {
  score: 86, fit_level: "Strong fit", engine_version: "2.0", computed_at: "2026-10-01T00:00:00",
  explanation: "86% match (strong fit) based on 6 factors. Strongest: skills, experience.",
  strengths: ["Skills: Has 1 of 1 required skills"], gaps: ["Salary: Expectation is 10% above the top of the range"],
  factors: [
    { key: "skills", label: "Skills", score: 1, weight: 0.5, detail: "Has 1 of 1 required skills" },
    { key: "experience", label: "Experience", score: 0.8, weight: 0.5, detail: "4 years vs 5+ required" },
    { key: "salary", label: "Salary", score: null, weight: 0, detail: "Salary expectation or budget not provided" },
  ],
  matching_skills: [{ skill: "Kubernetes", importance: "required", score: 1, kind: "synonym", via: "k8s" }],
  missing_skills: [{ skill: "Terraform", importance: "preferred" }],
};

const item = {
  candidate: { id: "cand_9", name: "Riya Menon", title: "SRE", skills: ["k8s", "Go"], experience_years: 4, location: "Pune", remote_preference: "Remote",
    avatar_url: "", availability: "open", preferred_locations: [], source: "self_registered", contact_visible: false, email: "" },
  match, status: "new", application: null, resume_document_id: null,
};

const list = { job, summary: { considered: 12, strong: 3, potential: 7 }, total: 1, items: [item], disclaimer: "Scores are not a measure of quality." };

const base = {
  "GET /auth/me": () => ({ body: makeUser() }),
  "GET /notifications": () => ({ body: [] }),
  "GET /jobs": () => ({ body: [job] }),
};

describe("Talent Match", () => {
  it("shows discovery summary, skill evidence and the factor breakdown", async () => {
    signIn();
    mockApi({ ...base, "GET /matching/jobs/job_1/candidates": () => ({ body: list }) });
    renderApp("/talent-match?job=job_1");
    const user = userEvent.setup();

    expect(await screen.findByText(/potentially relevant candidates found/)).toHaveTextContent("7 potentially relevant candidates found");
    expect(screen.getByLabelText("Matching skills")).toHaveTextContent("Kubernetes");
    expect(screen.getByLabelText("Matching skills")).toHaveTextContent("via k8s");
    expect(screen.getByLabelText("Missing skills")).toHaveTextContent("Terraform");

    await user.click(screen.getByRole("button", { name: "Why Riya Menon matches" }));
    const dialog = await screen.findByRole("dialog", { name: /Why Riya Menon matches Platform Engineer/ });
    expect(within(dialog).getByText("86%")).toBeInTheDocument();
    expect(within(dialog).getByText("4 years vs 5+ required")).toBeInTheDocument();
    expect(within(dialog).getByText(/Not used \(no data\): Salary/)).toBeInTheDocument();
    expect(within(dialog).getByText("Scores are not a measure of quality.")).toBeInTheDocument();
  });

  it("shortlisting is an explicit action", async () => {
    signIn();
    const { calls } = mockApi({
      ...base,
      "GET /matching/jobs/job_1/candidates": () => ({ body: list }),
      "POST /matching/jobs/job_1/candidates/cand_9/shortlist": () => ({ body: { ...item, status: "shortlisted", application: { id: "app_9", stage: "Shortlisted" } } }),
    });
    renderApp("/talent-match?job=job_1");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Shortlist" }));
    expect(await screen.findByText("Riya Menon shortlisted and added to the pipeline")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/matching/jobs/job_1/candidates/cand_9/shortlist")).toBe(true);
  });
});

describe("search", () => {
  it("shows how the query was understood", async () => {
    signIn();
    mockApi({
      ...base,
      "GET /search": () => ({ body: {
        query: "senior k8s engineers in Pune", interpreted: { skills: ["Kubernetes"], min_experience: 5, location: "Pune" },
        candidates: [{ candidate: item.candidate, relevance: 1, reasons: ["Skills: Kubernetes"] }], jobs: [], skills: [], organizations: [],
      } }),
    });
    renderApp("/search?q=senior%20k8s%20engineers%20in%20Pune");
    expect(await screen.findByText("Skills: Kubernetes", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("5+ years")).toBeInTheDocument();
    expect(screen.getByText("Location: Pune")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Riya Menon" })).toBeInTheDocument();
  });
});

describe("jobs for you", () => {
  it("lets a candidate apply", async () => {
    const candidate = makeUser({ role: "CANDIDATE", organization_id: null, full_name: "Riya Menon" });
    signIn(candidate);
    let applied = false;
    const { calls } = mockApi({
      "GET /auth/me": () => ({ body: candidate }),
      "GET /notifications": () => ({ body: [] }),
      "GET /matching/me/jobs": () => ({ body: [{ job, match, applied, application_stage: applied ? "Applied" : null }] }),
      "POST /applications": () => {
        applied = true;
        return { body: { id: "app_1", job_id: "job_1", stage: "Applied" } };
      },
    });
    renderApp("/jobs-for-you");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Apply" }));
    expect(await screen.findByText("Applied to Platform Engineer")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ job_id: "job_1" });
  });
});
