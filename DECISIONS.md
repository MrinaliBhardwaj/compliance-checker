# Decisions

Append-only log of direction decisions, so future sessions inherit them.

## 2026-07-11 — Repo completion pass (resume-ready)

- **This folder (`Downloads/compliance`) is the project home.** The GitHub repo is
  `MrinaliBhardwaj/compliance-checker`; work here, don't re-clone elsewhere.
- **The audit-trail module is part of Phase 1.** Formerly uncommitted WIP; now merged,
  tested (`test_audit_trail.py`), and live in the UI at `/audit`.
- **CI (GitHub Actions) is the proof for resume claims.** Backend job runs ruff +
  pytest with coverage against a `postgres:16` service; the 4 RLS/append-only
  hardening tests run there under a **non-superuser role** (superusers bypass RLS —
  never point the tests at a superuser). Frontend job typechecks and builds.
- **Alembic URL precedence:** a programmatically-set `sqlalchemy.url` (test fixtures)
  wins over app settings in `alembic/env.py`. Don't revert to the unconditional
  settings override.
- **Verified metrics as of this date** (re-verify before quoting newer ones):
  137 tests / 84% coverage / 34 endpoints / 27 tables / 106 obligation templates
  across 29 laws / 367+ instances per calendar / 98.4% doc classification.
- **SQLite is the demo/test path; Postgres+RLS is production-shaped.** The root
  README quickstart uses SQLite so the app runs with zero infra.

## 2026-07-12 — Security review fixes (auth boundary)

- **Auth endpoints set the RLS GUC explicitly; they are the one place that crosses
  tenant scope.** Under production Postgres (`FORCE ROW LEVEL SECURITY`), a session
  with no `app.current_org` is blocked on every tenant table. So: **signup** scopes
  to the newly-created org before inserting membership/entity; **accept-invite**
  scopes to the org in the signed invite token; **/me** scopes to the JWT's org.
- **Login uses a narrow, read-only `app.bootstrap` GUC** (migration `0003`) to resolve
  which org a user belongs to — the one unavoidable cross-tenant read. It is honored
  ONLY by the `memberships` USING clause (not WITH CHECK: bootstrap can't forge a
  membership), and the sole caller filters by user identity. Set via
  `app.core.db.set_bootstrap`. Don't broaden this to other tables.
- **Removal is revocation:** login accepts only `status='active'` memberships, and
  invite acceptance is single-use (`invited`-only) — a removed member's old invite
  link can't reinstate them, and an existing account must prove its own password to
  accept (possession of the link ≠ identity).
- **The legal-updates feed is cross-tenant, so publishing is allowlist-gated**
  (`REGIS_CONTENT_ADMIN_EMAILS`), NOT just `compliance_admin` — every self-serve
  signup is an admin of their own org. Empty allowlist = API publishing disabled.

## 2026-07-24 — Security review: medium+ findings

- **Background worker commits per-org, inside each org's tenant scope.** With
  `autoflush=False`, deferring all writes to one final commit flushed them under the
  *last* org's `app.current_org`, so Postgres RLS silently dropped every other org's
  overdue-flips and reminders. `nightly_sweep` and `enqueue_due_reminders` now
  `commit()` inside the per-org loop. (Enumerating `organizations` is fine — it has
  no RLS policy.)
- **Uploads are size-capped** (`REGIS_MAX_UPLOAD_MB`, default 25) — read in bounded
  chunks, 413 over the cap — so a large upload can't exhaust memory.
- **Passwords require ≥ 8 chars** (signup via Pydantic; new invited users in the
  team service).
- **`instance_completeness` scopes preparers to their own instances** (mirrors
  list/detail) — was an org-only check.
- **CORS is off by default** (SPA reaches the API via a same-origin Next.js proxy);
  `REGIS_CORS_ALLOW_ORIGINS` opts specific origins in — never `*`. **API docs
  (`/docs`, `/openapi.json`) are disabled when `REGIS_ENV=prod`.**
- **Deliberately deferred (own change, not this batch):** (1) move the JWT from
  localStorage to an httpOnly cookie — a full auth refactor (CSRF handling, every
  call) that shouldn't be rushed into a hardening batch, and there's no known XSS
  vector today (React escaping, no dangerouslySetInnerHTML). (2) Login rate-limiting
  belongs at the edge/gateway (Cloudflare/ALB or slowapi+Redis at deploy), not in
  app code.

## 2026-07-24 — Session auth moved to httpOnly cookie

- **The JWT lives in an httpOnly `regis_session` cookie, not localStorage** — so an
  XSS can't read the token. Set by signup/login/accept-invite; cleared by the new
  `POST /auth/logout` (httpOnly means JS can't clear it client-side).
- **Cookie flags:** `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age`=token TTL, and
  `Secure` on everywhere except `REGIS_ENV=dev` (plain-http localhost). CSRF is
  covered by SameSite=Lax + all mutations being non-GET + the same-origin proxy.
- **`get_current_principal` reads `Authorization: Bearer` first, else the cookie** —
  explicit header wins so API clients/tests stay stateless; the browser (no header)
  uses the cookie. The Bearer path is retained for programmatic clients.
- **Frontend never touches the token:** `lib/api.ts` sends `credentials:"include"`
  (fetch) / `withCredentials` (XHR upload); `setToken/getToken/clearToken` are gone.
  `auth.tsx` `refresh()` just calls `/auth/me` (401 ⇒ signed out); `logout()` calls
  the API. `regis_entity` (non-sensitive UI state) stays in localStorage.
- Tests: `_auth` clears the shared TestClient's cookie jar so Bearer-based smoke
  tests stay stateless; `test_httponly_cookie_session` covers the cookie path.

## 2026-07-24 — Login rate limiting (brute-force guard)

- **`app/core/ratelimit.py`** — fixed-window limiter on the auth endpoints. Keys:
  login is throttled per source IP AND per targeted account (`REGIS_LOGIN_MAX_ATTEMPTS`
  in `REGIS_LOGIN_WINDOW_SECONDS`, default 10 / 300s); invite acceptance per IP.
  Checked BEFORE the bcrypt verify, so a flood can't burn CPU. A successful login
  resets the counters (honest users aren't punished for a few typos).
- **Backend: Redis when reachable, in-process fallback otherwise.** Redis is the
  only correct choice in prod (shared across uvicorn workers/replicas — an in-process
  counter hands an attacker a fresh budget per worker). The app already runs Redis
  for Arq, so no new infra. **Fails OPEN** on backend errors — throttle attackers,
  don't lock real users out over a Redis hiccup; the per-account limit still holds
  if a spoofed X-Forwarded-For defeats the per-IP layer.
- **Client IP** comes from X-Forwarded-For (first hop) else `request.client.host`;
  in prod this must sit behind a proxy/LB that sets a trustworthy XFF (Vercel/
  Railway/ALB do).
- Tests clear the process-global counter between cases (autouse fixture in
  `tests/integration/conftest.py`); `test_login_is_rate_limited` covers the 429 path.

## 2026-09-01 — Frontend UX + visual system rework ("Ledger")

- **The design language is "Ledger": light-first, editorial, structured by hairline
  rules rather than cards and shadows.** The old navy `#0b1020` + `#4f86f7` + 10px-radius
  + drop-shadow theme was the generic dark-SaaS template look. Light is the default
  because compliance officers work in bright offices and screenshot into board packs;
  dark is a real second theme (neutral near-black, never navy). Tokens live in
  `app/globals.css` under `:root` / `[data-theme="dark"]`, stamped pre-paint by
  `THEME_BOOT_SCRIPT` in `lib/theme.tsx` so there is no flash.
- **Colour is reserved for meaning.** Status and risk carry colour; chrome does not.
  Primary buttons are ink-black, not accent-blue. The accent (`--accent`) is only for
  focus, selection and links. Risk is a 3-bar ramp *plus* a word, so it survives
  colour-blindness and printing.
- **No `window.prompt` / `window.confirm` anywhere.** Reject reasons, N/A reasons,
  evidence overrides and member removals all write permanent audit records, so each
  gets a labelled, validated dialog (`ConfirmDialog` in `components/ui.tsx`, min. 8
  chars on required reasons). Native dialogs cannot be validated or styled and were
  unacceptable for audited input.
- **Every overlay traps focus, closes on Escape and restores focus** (`useOverlay`).
  The old drawer *told* users to press Esc without implementing it.
- **Tracker filter/sort/selection state lives in the URL.** Views are shareable and
  survive the back button. Saved views (All / My work / Overdue / In review / Next 7
  days) replaced the wrapping chip wall — the views encode the questions people ask,
  the chips encoded the data model.
- **Bulk actions fan out over the existing per-instance lifecycle verbs**
  (`bulkTransition` / `bulkAssign` in `lib/api.ts`, concurrency 4). No new backend
  endpoints. Bulk runs are *pre-flighted* — ineligible rows are identified and excluded
  before the user confirms — and report per-item outcomes, so a partial failure (e.g.
  the evidence gate blocking an approval) is visible and re-runnable.
- **`/evidence` is a new route filling an IA hole.** `GET /documents` existed with no
  UI; the only path to a document was through the obligation it was linked to. It also
  surfaces unclassified and expired documents, which nothing else did.
- **Deadlines are stated relatively, not just absolutely** (`relativeDue` in
  `lib/format.ts`). Absolute-only dates made the user do arithmetic 346 times to answer
  "is this urgent?".
- **The health score is defined in the product.** The tooltip states the backend's exact
  formula — `100 × (1 − overdue ÷ total)` — plus today's inputs. A number a board can
  challenge but nobody can define is a number nobody should trust. If the backend
  formula changes, update the `Definition` tooltips in `app/dashboard/page.tsx` and
  `app/reports/page.tsx`.
- **Permission denial is a state, not a redirect.** Reports/Audit/Team/Onboarding render
  `PermissionDenied` naming who *can* do it. Silently bouncing to the dashboard reads
  as a bug.
- **Errors never auto-dismiss** and keep the raw server message behind "Show detail";
  success toasts still expire. Toasts are `aria-live`.
- **Below 900px the sidebar becomes a horizontal scrolling nav strip.** Note the grid
  track must be `minmax(0, 1fr)`, not `1fr` — `1fr` defaults to `min-width: auto` and
  the strip would widen the whole page. The responsive block must also sit *after* the
  base sidebar rules in `globals.css`, or equal-specificity base rules win.
- **`components/ObligationDrawer.tsx` was replaced by `components/ObligationSheet.tsx`**
  (tabs: Overview / Evidence / Activity, single "next action" footer). Don't reintroduce
  the flat all-expanded drawer.
- Verified against the live stack on this date: `tsc --noEmit` clean, `next build` clean
  (14 routes), and the flows exercised in-browser against the seeded SQLite dev DB
  (`backend/_live.db`) with a 346-obligation demo org.

## 2026-09-01 — Second UX pass: hierarchy and the core workflow

Audit focused on product hierarchy, not styling. The Ledger visual direction is
unchanged; everything here is about decision-making, trust and error prevention.

- **Triage priority is an explicit, explainable score** (`priorityOf` in
  `lib/format.ts`), and it is the default sort on the tracker and the dashboard
  queue. Sorting overdue work by date alone inverted real exposure: a 153-day-late
  board minute outranked a 3-day-late RBI return. Score = risk weight (high 3 /
  medium 2 / low 1) × time pressure. **It uses only fields the list endpoint
  returns** — penalty text lives on the detail record and is deliberately not part
  of the score, and the UI does not claim otherwise. The formula is published in a
  `Definition` tooltip (`PRIORITY_EXPLAINER`), same honesty rule as the health score.
- **Lateness uses a log curve, not a cap.** The first implementation capped
  lateness at 60 days; on the real portfolio (109 overdue, most 120+ days old,
  most high risk) *every* row scored exactly 15.0 and the column discriminated
  nothing. `3 + log10(1 + late/7) × 1.5` compresses the tail without ever
  flattening it — verified at 57 distinct scores across 346 rows. **If you retune
  this, re-check it against a lapsed portfolio, not a healthy one.**
- **On a badly lapsed portfolio most open items legitimately band as "critical".**
  That is the honest reading. The *score* does the ordering; the band is context.
  Don't "fix" this by inflating thresholds.
- **The detail sheet navigates prev/next through the list you came from**
  (`siblingIds` / `onNavigate`, plus ↑/↓ and J/K). Triaging 109 items was 109
  open/close cycles. Terminal actions (approve / mark-N/A / reject) auto-advance.
- **Bulk approve pre-checks the evidence gate, not just status.** The previous
  dialog promised "5 obligations will be changed" and then all five failed,
  because the server enforces a gate the list endpoint knows nothing about. It now
  calls `/obligations/instances/{id}/completeness` per selected row
  (`checkEvidenceGates`, concurrency 5, capped at `GATE_CHECK_LIMIT` = 60) and
  splits the batch into *will file* / *needs a recorded override* / *couldn't
  check*. Those are different decisions, so they get different paths. Rows that
  couldn't be checked are excluded rather than attempted blindly.
- **Evidence could not be linked from an existing document — a hard dead end.**
  Uploads de-duplicate on content hash, so the second upload of a document
  satisfying several obligations was rejected, and nothing in the UI reached
  `linkDocument()` for an existing file. `ExistingDocumentPicker` in the sheet's
  Evidence tab closes it, ranking documents whose type matches an outstanding
  requirement first. Unclassified documents are offered but disabled — they can't
  satisfy a requirement until they have a type.
- **Approve and mark-N/A offer Undo** (they are reversible through `reopen`, which
  is admin-only, so the affordance only appears for someone who can use it). The
  undo writes its own reason into the audit trail rather than silently reverting.
- **The active legal entity is in the top bar on every screen**, not the sidebar
  footer. Filing under the wrong entity is the most expensive mistake available in
  this product and was previously resolvable only by scrolling to the bottom of
  the nav.
- **The audit trail can isolate exceptions** — evidence overrides, blocked
  actions, rejections, member removals. That is an inspection's first question and
  tinting rows red doesn't help when they're on page 7. The API has no such
  parameter, so it filters the fetched page client-side; the count is therefore
  labelled "in events 51–100", never presented as a total.
- **Error boundaries exist** (`app/error.tsx`, `app/global-error.tsx`,
  `app/not-found.tsx`). A render error used to white-screen the app, which in a
  compliance product reads as data loss — the copy explicitly says nothing was
  changed. `ErrorState` now renders `PermissionDenied` for a 403 instead of a red
  alarm with a pointless retry button.
- **Table rows are activated by a real `<button>`** (`.row-open`), so assistive
  tech announces something operable rather than a cell. J/K move, X selects,
  Enter opens; selection changes are announced via `useAnnounce`.
- **Below 700px tracker rows stack into two lines** instead of scrolling
  sideways — due date and status, the two columns a decision needs, were off the
  right edge. Risk is hidden there because priority already encodes it. Verified
  the document cannot pan horizontally.
