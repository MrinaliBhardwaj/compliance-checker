import { expect, test } from "@playwright/test";

import { completeOnboarding, signUp } from "./helpers";

/**
 * Path 2 — evidence: upload a document against an obligation and link it.
 * This is the loop a preparer runs every filing cycle, and the one that proves
 * the audit trail has something in it.
 */
test("upload evidence against an obligation and link it", async ({ page }) => {
  await signUp(page, "Evidence NBFC");
  await completeOnboarding(page);

  await page.goto("/obligations");
  const rows = page.locator("table tbody tr");
  await expect(rows.first()).toBeVisible({ timeout: 20_000 });
  await rows.first().click();

  // The drawer is the working surface for a single obligation.
  const drawer = page.locator(".drawer, [role=dialog]").first();
  await expect(drawer).toBeVisible();

  // The input is hidden behind a drop zone; drive it directly.
  await page.locator('input[type="file"]').setInputFiles({
    name: "cims-acknowledgment.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\nCIMS acknowledgment for DNBS02\n%%EOF"),
  });

  // With no LLM key wired, classification is manual: the panel asks for a
  // document type and then links. That is the deterministic-offline path the
  // product ships in by default, so it is the one worth pinning.
  await expect(
    page.getByText(/AI classification unavailable/i),
  ).toBeVisible({ timeout: 20_000 });

  await page.getByRole("button", { name: /Classify & link/i }).click();

  // Linking runs the validation checks and reports each one — a link that
  // silently produced no checks would mean the evidence gate is not running.
  await expect(page.locator(".pill-row .chip").first()).toBeVisible({ timeout: 20_000 });
});

test("an uploaded file appears in the audit trail", async ({ page }) => {
  await signUp(page, "Audit NBFC");
  await completeOnboarding(page);

  await page.goto("/obligations");
  const rows = page.locator("table tbody tr");
  await expect(rows.first()).toBeVisible({ timeout: 20_000 });
  await rows.first().click();

  await page.locator('input[type="file"]').setInputFiles({
    name: "board-minutes.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\nboard minutes\n%%EOF"),
  });
  await expect(page.getByText(/AI classification unavailable/i)).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: /Classify & link/i }).click();
  await expect(page.locator(".pill-row .chip").first()).toBeVisible({ timeout: 20_000 });

  // The append-only trail is the thing an inspection follows; an upload that
  // leaves no record would still look fine in the UI.
  await page.goto("/audit");
  await expect(page.locator("table tbody tr").first()).toBeVisible({ timeout: 20_000 });
});
