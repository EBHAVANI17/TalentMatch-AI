import { expect, test, type Page } from "@playwright/test";

async function signInAs(page: Page, persona: RegExp) {
  await page.goto("/app/login");
  await page.getByRole("button", { name: persona }).click();
  await expect(page).not.toHaveURL(/login/);
}

// The E2E server runs without AI keys, so these exercise the rule-based copilot end to end.
test.describe("Phase 5 recruiter copilot", () => {
  test("recruiter asks about the open job and follows a cited candidate", async ({ page }, info) => {
    await signInAs(page, /Recruiter \(Anthropic\)/);
    await page.goto("/app/jobs/job_001");
    await page.getByRole("button", { name: "Copilot" }).click();
    const panel = page.getByRole("dialog", { name: "Copilot" });
    await panel.getByRole("button", { name: "Who are the best candidates for this job?" }).click();

    await expect(panel.getByText(/Best matches for/)).toBeVisible();
    await expect(panel.getByRole("link", { name: "Staff AI Infrastructure & Inference Engineer" })).toBeVisible();
    await expect(panel.getByText(/built-in rules/)).toBeVisible();
    await page.screenshot({ path: info.outputPath("01-copilot-panel.png"), fullPage: true });

    await panel.getByRole("link", { name: "Aarav Sharma" }).first().click();
    await expect(page).toHaveURL(/\/app\/candidates\/cand_001$/);
  });

  test("conversations are kept in history on the copilot page", async ({ page }) => {
    await signInAs(page, /Recruiter \(Anthropic\)/);
    await page.goto("/app/copilot");
    const question = `Show my hiring pipeline`;
    await page.getByRole("button", { name: question, exact: true }).click();
    await expect(page.getByText(/Pipeline for your organization/)).toBeVisible();
    await expect(page).toHaveURL(/\?c=conv_/);

    await page.reload();
    await expect(page.getByText(/Pipeline for your organization/)).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Conversations" }).getByText(question).first()).toBeVisible();
  });
});
