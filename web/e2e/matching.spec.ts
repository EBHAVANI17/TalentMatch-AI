import { expect, test, type Page } from "@playwright/test";

async function signInAs(page: Page, persona: RegExp) {
  await page.goto("/app/login");
  await page.getByRole("button", { name: persona }).click();
  await expect(page).not.toHaveURL(/login/);
}

test.describe("Phase 3 matching and search", () => {
  test("recruiter reviews explained matches and shortlists", async ({ page }, info) => {
    await signInAs(page, /Recruiter \(Anthropic\)/);
    await page.goto("/app/talent-match?job=job_001");
    await expect(page.getByText(/potentially relevant candidates found/)).toBeVisible();
    await page.screenshot({ path: info.outputPath("01-talent-match.png"), fullPage: true });

    await page.getByRole("button", { name: /^Why .* matches$/ }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("How the score is made")).toBeVisible();
    await expect(dialog.getByText(/not a measure of a person's quality/)).toBeVisible();
    await page.screenshot({ path: info.outputPath("02-why-this-match.png") });
    await dialog.getByRole("button", { name: "Close dialog" }).click();

    // Shortlist someone who hasn't applied: they join the pipeline as Shortlisted
    const card = page.getByRole("listitem").filter({ hasText: "Sophia Vance" });
    const shortlist = card.getByRole("button", { name: /^Shortlist(ed)?$/ });
    if (await shortlist.isEnabled()) {
      await shortlist.click();
      await expect(page.getByText("Sophia Vance shortlisted and added to the pipeline")).toBeVisible();
    }
    await page.getByRole("tab", { name: "Shortlisted" }).click();
    await expect(page.getByRole("link", { name: "Sophia Vance" })).toBeVisible();
  });

  test("global search understands plain language", async ({ page }, info) => {
    await signInAs(page, /Recruiter \(Anthropic\)/);
    const search = page.getByRole("searchbox", { name: "Search" }).or(page.getByLabel("Search", { exact: true }));
    await search.first().fill("engineers who build LLM inference systems on GPUs");
    await search.first().press("Enter");
    await expect(page.getByRole("heading", { name: /Results for/ })).toBeVisible();
    await expect(page.getByRole("link", { name: "Aarav Sharma" })).toBeVisible();
    await page.screenshot({ path: info.outputPath("03-search.png"), fullPage: true });
  });

  test("candidate sees ranked jobs and applies", async ({ page }, info) => {
    await signInAs(page, /Candidate/);
    await page.goto("/app/jobs-for-you");
    await expect(page.getByRole("heading", { name: "Jobs for you" })).toBeVisible();
    await expect(page.getByRole("button", { name: /^Why .* matches you$/ }).first()).toBeVisible();
    await page.screenshot({ path: info.outputPath("04-jobs-for-you.png"), fullPage: true });
    const apply = page.getByRole("button", { name: "Apply" }).first();
    if (await apply.count()) {
      await apply.click();
      await expect(page.getByText(/^Applied to /)).toBeVisible();
    }
  });
});
