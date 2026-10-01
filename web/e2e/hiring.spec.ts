import { expect, test, type Page } from "@playwright/test";

async function signInAs(page: Page, persona: RegExp) {
  await page.goto("/app/login");
  await page.getByRole("button", { name: persona }).click();
  await expect(page).not.toHaveURL(/login/);
}

test.describe("Phase 2 hiring flows", () => {
  test("recruiter creates, publishes and manages a job", async ({ page }, info) => {
    await signInAs(page, /Recruiter \(Anthropic\)/);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByText("Active jobs")).toBeVisible();
    await page.screenshot({ path: info.outputPath("01-dashboard.png"), fullPage: true });

    const title = `E2E Platform Engineer ${info.project.name} ${Date.now() % 100000}`;
    await page.goto("/app/jobs/new");
    await page.getByLabel("Job title").fill(title);
    await page.getByLabel("Description").fill("Build and operate our inference platform.");
    await page.getByLabel("Required skills").fill("Kubernetes");
    await page.getByLabel("Required skills").press("Enter");
    await page.getByLabel("Location").fill("Bangalore, India");
    await page.getByRole("button", { name: "Save as draft" }).click();

    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(page.getByText("Draft", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Publish" }).click();
    await expect(page.getByText("Job published")).toBeVisible();
    // Published jobs offer Pause/Close instead of Publish
    await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Publish" })).toHaveCount(0);
    await page.screenshot({ path: info.outputPath("02-job-detail.png"), fullPage: true });

    await page.goto("/app/jobs");
    await expect(page.getByRole("link", { name: title })).toBeVisible();
    await page.screenshot({ path: info.outputPath("03-jobs.png"), fullPage: true });
  });

  test("recruiter reviews a candidate, adds a note and moves the application", async ({ page }, info) => {
    await signInAs(page, /Recruiter \(Anthropic\)/);
    await page.goto("/app/candidates");
    await expect(page.getByRole("heading", { name: "Candidates" })).toBeVisible();
    await page.screenshot({ path: info.outputPath("04-candidates.png"), fullPage: true });

    await page.goto("/app/candidates/cand_001");
    await expect(page.getByRole("heading", { name: "Aarav Sharma" })).toBeVisible();
    await expect(page.getByRole("link", { name: "aarav@stanford.edu" })).toBeVisible(); // applied to Anthropic
    const note = `Strong systems design (${info.project.name})`;
    await page.getByLabel("Add a note").fill(note);
    await page.getByRole("button", { name: "Save note" }).click();
    await expect(page.getByText(note)).toBeVisible();
    await page.screenshot({ path: info.outputPath("05-candidate.png"), fullPage: true });

    // Contacts are hidden for talent-pool candidates who haven't applied
    await page.goto("/app/candidates/cand_002");
    await expect(page.getByText("Contact details are shared once this person applies")).toBeVisible();

    await page.goto("/app/jobs/job_001");
    const stage = page.getByLabel("Stage for Aarav Sharma");
    await stage.selectOption("Shortlisted");
    await expect(page.getByText("Aarav Sharma moved to Shortlisted")).toBeVisible();
  });

  test("candidate edits their profile and sees their applications", async ({ page }, info) => {
    await signInAs(page, /Candidate/);
    await expect(page.getByRole("heading", { name: "My applications" })).toBeVisible();
    await page.screenshot({ path: info.outputPath("06-candidate-home.png"), fullPage: true });

    await page.goto("/app/profile");
    const headline = `Staff AI Engineer ${info.project.name}`;
    await page.getByLabel("Professional headline").fill(headline);
    await page.getByLabel("Notice period (days)").fill("45");
    await page.getByRole("button", { name: "Save profile" }).click();
    await expect(page.getByText("Profile saved")).toBeVisible();
    await page.reload();
    await expect(page.getByLabel("Professional headline")).toHaveValue(headline);
    await page.screenshot({ path: info.outputPath("07-profile.png"), fullPage: true });
  });
});
