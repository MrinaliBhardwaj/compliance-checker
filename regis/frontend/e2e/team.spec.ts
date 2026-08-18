import { expect, test } from "@playwright/test";

import { PASSWORD, completeOnboarding, signUp, uniqueEmail } from "./helpers";

/**
 * Path 3 — team: invite a teammate, accept the invite as that person, and end
 * up with a second member on the org. Onboarding is single-player; this is the
 * step that makes it a team product, and the PRD's activation metric.
 */
test("invite a teammate and accept the invitation", async ({ page, browser }) => {
  await signUp(page, "Team NBFC");
  await completeOnboarding(page);

  await page.goto("/team");
  await expect(page.getByRole("heading", { name: "Team", exact: true })).toBeVisible();

  const inviteeEmail = uniqueEmail("invitee");
  await page.getByLabel(/email/i).first().fill(inviteeEmail);
  await page.getByRole("button", { name: /invite/i }).first().click();

  // The admin is shown a shareable invite link; that link is the handoff.
  const inviteLink = page.getByText(/\/accept\?token=/).first();
  await expect(inviteLink).toBeVisible({ timeout: 15_000 });
  // The banner reads "Invite link: <url>", so pull the URL out rather than
  // navigating to the label text.
  const banner = (await inviteLink.textContent())!;
  const href = banner.match(/https?:\/\/\S+\/accept\?token=\S+/)![0];
  expect(href).toContain("/accept?token=");

  // Accept in a clean context — the invitee is a different person, not the
  // admin with a cookie.
  const invitee = await browser.newContext();
  const inviteePage = await invitee.newPage();
  await inviteePage.goto(href);
  await inviteePage.getByLabel("Password").fill(PASSWORD);
  await inviteePage.getByRole("button", { name: /accept|join|continue/i }).first().click();
  await expect(inviteePage).toHaveURL(/\/(dashboard|obligations)/, { timeout: 20_000 });
  await invitee.close();

  // Back on the admin's side, the roster now has two people.
  await page.reload();
  const members = page.locator("table tbody tr");
  await expect(members.first()).toBeVisible({ timeout: 15_000 });
  expect(await members.count()).toBeGreaterThanOrEqual(2);
});
