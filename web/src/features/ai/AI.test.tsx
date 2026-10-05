import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeUser, mockApi, renderApp, signIn } from "@/test/utils";

afterEach(() => vi.unstubAllGlobals());

const parsed = {
  method: "rules", provider: "rules", model: "", request_id: "air_1",
  notice: "Created with built-in rules because no AI provider is configured. Review and edit before saving.",
  document_id: "doc_1", resume_id: "res_1", candidate_id: "cand_9",
  contact: { name: "Riya Menon", email: "riya@example.com", phone: "+91 98765 43210", location: "Pune, India", linkedin_url: "", github_url: "", portfolio_url: "" },
  draft: {
    headline: "Senior Backend Engineer", summary: "Payments infrastructure.", total_experience_years: 6,
    skills: ["Python", "Go"], industries: [], projects: [],
    work_experience: [{ job_title: "Backend Engineer", company_name: "Razorpay", location: "", start_date: "2021-04", end_date: "", is_current: true, description: "", achievements: ["Cut latency 40%"] }],
    education: [{ institution: "NIT Trichy", degree: "B.Tech", field_of_study: "CS", graduation_year: 2018 }],
    certifications: [], languages: [{ language: "English", proficiency: "professional" }],
  },
};

describe("resume import", () => {
  it("shows the draft for review and saves only what the user confirms", async () => {
    const candidate = makeUser({ role: "CANDIDATE", organization_id: null, full_name: "Riya Menon" });
    signIn(candidate);
    const { calls } = mockApi({
      "GET /auth/me": () => ({ body: candidate }),
      "GET /notifications": () => ({ body: [] }),
      "POST /ai/resume/parse": () => ({ body: parsed }),
      "PATCH /candidates/me": () => ({ body: { id: "cand_9", name: "Riya Menon" } }),
      "GET /candidates/me": () => ({ body: { id: "cand_9", name: "Riya Menon", skills: [], profile_strength: 50 } }),
    });
    renderApp("/profile/import");
    const user = userEvent.setup();

    await user.upload(await screen.findByLabelText("Resume file"), new File(["resume text"], "cv.txt", { type: "text/plain" }));
    expect(await screen.findByText(/no AI provider is configured/)).toBeInTheDocument();
    const headline = screen.getByLabelText("Headline");
    expect(headline).toHaveValue("Senior Backend Engineer");
    await user.clear(headline);
    await user.type(headline, "Staff Backend Engineer");
    await user.click(screen.getByRole("button", { name: "Save to my profile" }));

    await screen.findByText("Your profile was updated from your resume");
    const body = calls.find((c) => c.method === "PATCH")?.body as Record<string, unknown>;
    expect(body.title).toBe("Staff Backend Engineer");
    expect(body.skills).toEqual(["Python", "Go"]);
    expect((body.work_experience as Array<{ company_name: string }>)[0].company_name).toBe("Razorpay");
  });
});

describe("job draft assistant", () => {
  it("fills the job form from a brief", async () => {
    signIn();
    mockApi({
      "GET /auth/me": () => ({ body: makeUser() }),
      "GET /notifications": () => ({ body: [] }),
      "POST /ai/jobs/generate": () => ({ body: {
        method: "ai", provider: "groq", model: "llama", request_id: "air_2", notice: "Drafted with AI (groq). Review and edit before saving.",
        draft: { title: "Senior Backend Developer", department: "Engineering", seniority: "Senior", employment_type: "Full-time", workplace_type: "Hybrid",
          location: "Bangalore", description: "Build APIs.", responsibilities: ["Design services"], required_skills: ["Node.js", "AWS"],
          preferred_skills: ["Express"], min_experience_years: 5, max_experience_years: null, required_education: "Bachelor's degree",
          salary_min: null, salary_max: null, interview_criteria: ["Depth in Node.js"], screening_questions: ["Tell us about a Node.js project."] },
      } }),
    });
    renderApp("/jobs/new");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Brief"), "Senior Backend Developer, 5+ years, Node.js, AWS");
    await user.click(screen.getByRole("button", { name: "Generate draft" }));

    expect(await screen.findByText(/Drafted with AI \(groq\)/)).toBeInTheDocument();
    expect(screen.getByLabelText("Job title")).toHaveValue("Senior Backend Developer");
    expect(screen.getByLabelText("Minimum experience (years)")).toHaveValue(5);
    expect(screen.getByLabelText("Work mode")).toHaveValue("Hybrid");
    expect(screen.getByLabelText("Education")).toHaveValue("Bachelor's");
    expect(screen.getByLabelText("Screening questions")).toHaveValue("Tell us about a Node.js project.");
  });
});
