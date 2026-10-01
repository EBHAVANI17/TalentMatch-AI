import { expect, test } from "@playwright/test";

test.describe("new workspace smoke test", () => {
  test("recruiter signs in, manages the team, and stays signed in to the classic workspace", async ({ page }, info) => {
    // Signed-out visitors land on the sign-in page
    await page.goto("/app/team");
    await expect(page).toHaveURL(/\/app\/login$/);
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await expect(page.getByText("Demo accounts")).toBeVisible();
    await page.screenshot({ path: info.outputPath("01-login.png"), fullPage: true });

    // Email + password sign-in returns to the requested page
    await page.getByLabel("Email").fill("recruiter@anthropic.com");
    await page.getByLabel("Password").fill("anthropic123");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Team" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "recruiter@anthropic.com" })).toBeVisible();

    // Invite a teammate (real API call)
    const email = `e2e.${info.project.name}.${Date.now()}@anthropic.com`;
    await page.getByRole("button", { name: "Invite member" }).first().click();
    const dialog = page.getByRole("dialog", { name: "Invite a team member" });
    await dialog.getByLabel("Work email").fill(email);
    await dialog.getByLabel("Role").selectOption("HIRING_MANAGER");
    await dialog.getByRole("button", { name: "Send invitation" }).click();
    await expect(page.getByText(`Invitation sent to ${email}`)).toBeVisible();
    await expect(page.getByText(email, { exact: true })).toBeVisible();
    await page.screenshot({ path: info.outputPath("02-team.png"), fullPage: true });

    // The Team page shows the organization from the API; recruiters land on the dashboard
    await expect(page.getByRole("heading", { name: "Your organization" })).toBeVisible();
    await page.goto("/app/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await page.screenshot({ path: info.outputPath("03-home.png"), fullPage: true });

    // The classic workspace shares the session (same localStorage keys): its header shows the signed-in user
    await page.goto("/");
    await expect(page.getByRole("button", { name: "User Sarah" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible(); // landing CTA still present
    await page.screenshot({ path: info.outputPath("04-classic.png") });
  });

  test("candidate cannot open the Team page", async ({ page }) => {
    await page.goto("/app/login");
    await page.getByRole("button", { name: /Candidate/ }).click();
    await expect(page.getByRole("heading", { name: "Welcome, Aarav" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Team" })).toHaveCount(0);
    await page.goto("/app/team");
    await expect(page.getByRole("heading", { name: "Welcome, Aarav" })).toBeVisible();
  });

  test("dark theme toggle persists", async ({ page }) => {
    await page.goto("/app/login");
    await page.getByRole("button", { name: /Platform admin/ }).click();
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    const html = page.locator("html");
    const before = await html.getAttribute("data-theme");
    await page.getByRole("button", { name: /Switch to (dark|light) theme/ }).click();
    await expect(html).not.toHaveAttribute("data-theme", before ?? "");
    await page.reload();
    await expect(html).not.toHaveAttribute("data-theme", before ?? "");
  });
});
