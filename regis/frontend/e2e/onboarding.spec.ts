import { expect, test } from "@playwright/test";

import { completeOnboarding, signUp } from "./helpers";

/**
 * Path 1 — the core promise: a compliance officer signs up and has a populated
 * calendar minutes later. If this breaks, there is no product to demo.
 */
test("sign up, onboard, and land on a populated calendar", async ({ page }) => {
  await signUp(page, "Onboarding NBFC");
  await completeOnboarding(page);

  await expect(page.getByRole("heading", { name: "Compliance" })).toBeVisible();

  // The dashboard is only meaningful if it has real obligations in it — an
  // empty dashboard would satisfy a URL assertion and still be a dead demo.
  const rows = page.locator("table tbody tr");
  await expect(rows.first()).toBeVisible({ timeout: 20_000 });
  expect(await rows.count()).toBeGreaterThan(0);
});

test("the provisional banner is visible while the library is unverified", async ({ page }) => {
  await signUp(page, "Provisional NBFC");
  await completeOnboarding(page);
  await page.goto("/reports");

  // Every template ships DRAFT_UNVERIFIED, so reports must say so. This is the
  // honesty gate that lets the product be sold before the library is signed
  // off; a silent removal of it is a commercial problem, not a UI nit.
  await expect(page.getByText(/provisional/i).first()).toBeVisible({ timeout: 20_000 });
});

test("a mid-size NBFC is tiered correctly from free-text asset size", async ({ page }) => {
  // Regression for the parse bug that returned 1.5 for "3 thousand crore" and
  // silently dropped the whole Middle-Layer obligation set.
  await signUp(page, "Freetext NBFC");
  await completeOnboarding(page, "around 3 thousand crore");

  await page.goto("/obligations");
  const rows = page.locator("table tbody tr");
  await expect(rows.first()).toBeVisible({ timeout: 20_000 });
  expect(await rows.count()).toBeGreaterThan(20);
});
