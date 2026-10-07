import { expect, test } from "@playwright/test";

const ANTHROPIC_JOB = "Staff AI Infrastructure & Inference Engineer";
const STRIPE_JOB = "Lead Distributed Ledger & Systems Engineer";

test.describe("Step 1 organization switching", () => {
  test("switching organization changes the jobs list and reloads other tabs", async ({ page, context }) => {
    await page.goto("/app/login");
    await page.getByRole("button", { name: /Two organizations/ }).click();
    await expect(page).not.toHaveURL(/login/);

    await page.goto("/app/jobs");
    await expect(page.getByText(ANTHROPIC_JOB).first()).toBeVisible();
    await expect(page.getByText(STRIPE_JOB)).toHaveCount(0);

    // A second tab on the same session, still showing Anthropic
    const other = await context.newPage();
    await other.goto("/app/jobs");
    await expect(other.getByText(ANTHROPIC_JOB).first()).toBeVisible();
    const otherReloaded = other.waitForEvent("load");

    await page.getByLabel("Organization").selectOption("org_stripe");
    await expect(page.getByText(/Now working in Stripe as Hiring Manager/)).toBeVisible();

    await page.goto("/app/jobs");
    await expect(page.getByText(STRIPE_JOB).first()).toBeVisible();
    await expect(page.getByText(ANTHROPIC_JOB)).toHaveCount(0);

    // The broadcast made the other tab reload, and it now shows Stripe too
    await otherReloaded;
    await expect(other.getByText(STRIPE_JOB).first()).toBeVisible();
    await expect(other.getByText(ANTHROPIC_JOB)).toHaveCount(0);
  });
});
