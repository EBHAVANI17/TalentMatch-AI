import { expect, test, type Page } from "@playwright/test";

async function signInAs(page: Page, persona: RegExp) {
  await page.goto("/app/login");
  await page.getByRole("button", { name: persona }).click();
  await expect(page).not.toHaveURL(/login/);
}

const RESUME = `Aarav Sharma
Staff AI Engineer
San Francisco, CA | aarav@stanford.edu | +1 (415) 555-0100
Skills
Python, PyTorch, k8s, PostgreSQL, FastAPI
Experience
Staff AI Engineer - Anthropic (Jan 2022 - Present)
Scaled inference to 50k QPS with custom CUDA kernels
ML Engineer at Amazon (Jun 2019 - Dec 2021)
Built model training pipelines on AWS
Education
M.S. in Computer Science - Stanford University, 2019
Languages
English, Hindi
`;

test.describe("Phase 4 AI drafting", () => {
  test("candidate imports a resume, reviews the draft and saves it", async ({ page }, info) => {
    await signInAs(page, /Candidate/);
    await page.goto("/app/profile");
    await page.getByRole("link", { name: "Import from resume" }).click();
    await page.getByLabel("Resume file").setInputFiles({ name: "aarav.txt", mimeType: "text/plain", buffer: Buffer.from(RESUME) });

    await expect(page.getByText(/Automatic draft|AI draft/)).toBeVisible();
    await expect(page.getByLabel("Headline")).toHaveValue("Staff AI Engineer");
    await expect(page.getByLabel("Company").first()).toHaveValue("Anthropic");
    await page.screenshot({ path: info.outputPath("01-resume-review.png"), fullPage: true });

    await page.getByLabel("Headline").fill(`Staff AI Engineer (${info.project.name})`);
    await page.getByRole("button", { name: "Save to my profile" }).click();
    await expect(page.getByText("Your profile was updated from your resume")).toBeVisible();
    await expect(page.getByLabel("Professional headline")).toHaveValue(`Staff AI Engineer (${info.project.name})`);
  });

  test("recruiter drafts a job from a brief and publishes it", async ({ page }, info) => {
    await signInAs(page, /Recruiter \(Stripe\)/);
    await page.goto("/app/jobs/new");
    const title = `Senior Backend Developer ${info.project.name} ${Date.now() % 10000}`;
    await page.getByLabel("Brief").fill(`${title}, 5+ years, Node.js, AWS, hybrid`);
    await page.getByRole("button", { name: "Generate draft" }).click();

    await expect(page.getByText(/Automatic draft|AI draft/)).toBeVisible();
    await expect(page.getByLabel("Job title")).toHaveValue(title);
    await expect(page.getByLabel("Minimum experience (years)")).toHaveValue("5");
    await expect(page.getByLabel("Screening questions")).not.toHaveValue("");
    await page.screenshot({ path: info.outputPath("02-job-draft.png"), fullPage: true });

    await page.getByRole("button", { name: "Publish job" }).click();
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(page.getByText("Node.js").first()).toBeVisible();
  });
});
