import { expect, type Page } from "@playwright/test";

/** Unique per run: every path signs up a real organisation. */
export function uniqueEmail(prefix = "e2e"): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e4)}@acme.example`;
}

export const PASSWORD = "goodpassword1";

/** Sign up a fresh org and land on onboarding. Returns the account's email. */
export async function signUp(page: Page, orgName = "E2E NBFC"): Promise<string> {
  const email = uniqueEmail();
  await page.goto("/");
  await page.getByLabel("Organization name").fill(orgName);
  await page.getByLabel("Entity legal name").fill(`${orgName} Ltd`);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  return email;
}

/** Fill the profile, preview, and confirm — leaving a generated calendar. */
export async function completeOnboarding(page: Page, assetCr = "3000"): Promise<void> {
  await page.getByLabel("Asset size (₹ cr)").fill(assetCr);
  await page.getByLabel("Turnover (₹ cr)").fill("450");
  await page.getByLabel("Employees").fill("260");
  await page.getByLabel("Branches").fill("12");

  await page.getByRole("button", { name: "Analyze profile" }).click();
  await page.getByRole("button", { name: /Confirm & generate/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 30_000 });
}
