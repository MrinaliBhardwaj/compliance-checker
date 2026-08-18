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

## 2026-08-18 — Phase 1: made the backend operable

Written against the technical review. The theme: the codebase was built to be
*correct* and never built to be *operated*.

- **Structured logging (`app/core/logging.py`), stdlib only — no new hard dep.**
  JSON on stdout, `REGIS_LOG_FORMAT=text` for local. `bind()` attaches tenant
  context to every line in a block; a log line without an `organization_id` is
  nearly useless in a multi-tenant worker. **Logging never raises** — a
  formatting failure must not take down the sweep it exists to make observable.
  Sentry initialises lazily only when `REGIS_SENTRY_DSN` is set, and a failed
  init warns rather than exits.
- **Per-organisation failure isolation in the worker.** Both jobs previously
  walked every org with *no exception handling at all*: one bad row or one SES
  failure aborted the loop and every later org silently got no overdue flips and
  no reminders. The earlier DECISIONS claim that "per-org commit makes one bad
  org non-fatal for the rest of the sweep" was **wrong in the half that
  mattered** — the commit made completed orgs durable, nothing kept the loop
  alive. `_for_each_org` now rolls back, logs with the org id, counts, and
  continues, returning a per-org tally. It takes an injectable session factory
  so the isolation is testable (`test_worker_isolation.py`).
- **`cron_jobs` was an empty list** — the sweep would never have fired even once
  deployed. Now 00:30 and 09:00 IST (19:00 / 03:30 UTC; arq cron is UTC).
- **Notification delivery is a recorded outcome** (migration `0004`):
  `delivery_status` (pending|sent|failed) + `delivery_error`. `sent_at IS NULL`
  could not distinguish never-attempted from attempted-and-failed. `emit()`
  catches channel exceptions rather than letting SES/Slack failures escape into
  the worker loop.
- **`parse_amount_cr` no longer mis-tiers an NBFC.** `"around 3 thousand crore"`
  returned **1.5** (the `thousand`→`000` substitution made `"3 000"`, read as
  the band [3.0, 0.0] and averaged), so a customer entering asset size that way
  was classified Base Layer and silently lost the whole ML/UL set. Multipliers
  now fold into their number *before* band detection, and a band needs an
  explicit separator — adjacency is not a range, so `"3 000"` is **refused as
  ambiguous** rather than guessed. Messy extraction golden 62 → 73.
- **Request logging middleware** with an `x-request-id` echoed to the caller.
  It cannot raise: an unhandled error is logged with its id and returned as a
  generic 500, detail to the log rather than the client.
- **Deployment exists now, on paper.** `docker-compose.yml` (Postgres/Redis/api/
  worker/web — api and worker are the *same image*, different command, so the
  engines can never drift), Dockerfiles for both apps (non-root, healthchecked,
  Next.js `output: "standalone"`), and `infra/terraform` for ap-south-1 (RDS,
  ElastiCache, S3+KMS; `var.region` validation rejects anything outside
  `ap-south-*`).
  **Never applied, and no Docker daemon was available to build the images** —
  syntax-checked only. The config docstring previously pointed at an
  `infra/terraform` that did not exist; it now points at one that does and says
  plainly that residency is intent, not yet evidence. **Do not repeat the data
  residency claim to a customer until someone applies it.**
- **The threshold guard caught `1_000` in the new multiplier map** — a genuine
  false positive. Added an explicit `# not-a-threshold` opt-out rather than
  weakening the guard, so skipping is visible in review.
- 170 → 173 tests passing; 85% coverage.

## 2026-08-08 — Base Layer concentration policy template added (107th)

- **`sbr_concentration_policy_bl`** — Board-approved internal policy on
  credit/investment concentration limits for single borrower/party and single group.
  Base Layer has **no RBI-prescribed numerical ceilings**, but exposure computation
  must follow NBFC-ML requirements. Source: **RBI/2023-24/112, 15 January 2024**
  (Credit/Investment Concentration Norms – Credit Risk Transfer), which harmonised
  computation across BL and ML. `law_rbi_sbr`, annual, `annual_board_review`,
  `rbi_layer: ["base"]`, medium risk, ships DRAFT_UNVERIFIED like everything else.
- **It pairs with `rbi_concentration`** (the ML/UL numerical ceilings) and the two
  are mutually exclusive on layer — pinned by
  `test_base_layer_concentration_policy_pairs_with_the_ml_norms`.
- **Goldens moved as expected:** profile A 69 -> 70 applicable (Base Layer, gains
  it); B and C gain one not-applicable each (13 -> 14, 14 -> 15); seed counts
  106 -> 107.
- **The evidence corpus grew 192 -> 195 and all three new strings type cleanly**
  (POLICY_DOC / BOARD_SECRETARIAL / COMPUTATION_RECON), so OTHER stays at 3 and the
  classification rate goes 189/192 = 98.4% -> 192/195 = 98.5%. Note the README
  previously read "98.4% ... (192/195)", which mixed the old percentage with the
  new fraction — it was never internally consistent. Now corrected.

### Found while doing this — NOT fixed, pinned instead

- **`parse_amount_cr("around 3 thousand crore")` returns 1.5, not 3000.** The
  "thousand" -> "000" substitution yields "3 000", which the band branch reads as
  the band [3.0, 0.0] and averages. A real customer entering their asset size as
  free text in that shape is classified **Base Layer instead of Middle Layer and
  silently loses the entire Middle/Upper Layer obligation set** — a missed-obligation
  bug, the dangerous direction. It is also why RAW_MESSY picked up the new Base
  Layer template (61 -> 62): that golden has been measuring a Rs.1.5cr entity, not
  the Rs.3000cr one its fixture comment describes.
  `test_messy_asset_size_misparses_thousand` pins it; delete that test in the same
  change that fixes `parse_amount_cr`, and expect the messy golden to move well
  above 62.

## 2026-08-08 — Category/asset consistency check (closes the open item below)

- **`consistency_checks` now compares `nbfc_category` against asset size and the
  deposit-taking flag**, so the Profile C class of contradiction is caught at
  runtime on a real customer profile, not only in fixtures.
- **Asymmetric, mirroring the layer checks — the asymmetry is the design:**
  - *understating* (`icc` at/above Rs.500cr, non-deposit) → **contradiction**. This
    is the direction that silently drops CRILC scope, i.e. a missed obligation.
  - *overstating* (`nd_si` below Rs.500cr) → **warning only**. Legitimate causes
    exist: an NBFC-Factor is notified regardless of size, and group-asset
    aggregation pulls in individually smaller NBFCs. A contradiction here would be
    a false positive.
  - category disagreeing with `deposit_taking` in either direction →
    **contradiction** (direct field conflict, no legitimate reading).
- **An unasserted category is never flagged** — a derived-only profile must not
  contradict itself.
- **`asserted` now carries `nbfc_category`** alongside `rbi_layer` in
  `extract_profile`. Neither golden raw payload asserts a category, so the
  extraction goldens are unmoved.
- Also formats asset figures with `:g` in all three contradiction/warning messages
  — they rendered as "Rs.520.0cr" to a compliance officer.

## 2026-08-08 — Profile C fixture corrected to `nd_si` (closes the item below)

- **`profile_c` now declares `nbfc_category: "nd_si"`**, which is what
  `derive_regulatory_category` actually returns at Rs.520cr (>= the Rs.500cr CRILC
  threshold). The old `"icc"` was a fixture bug that silently held CRILC out of
  scope, so the previous golden of 63 was measuring the bug, not the rule.
  **Golden: profile C 63 -> 65 / 27 / 14.** A and B unmoved.
- **`rbi_layer` stays `"middle"` at Rs.520cr.** That is legitimate, not a second
  bug — RBI may place an NBFC in a higher layer than asset size implies, which is
  why `consistency_checks` flags only the Base-with-large-assets direction.
- **The pin became a real invariant.** `test_profile_c_fixture_is_internally_inconsistent`
  is replaced by `test_fixture_categories_agree_with_the_engine`, parametrized over
  all three profiles: a fixture declaring a category the engine would not derive
  makes every golden resting on it meaningless.
- **Added `test_crilc_covers_base_layer_above_the_notified_threshold`** — a Base
  Layer NBFC at Rs.700cr must get CRILC and must NOT get the ML/UL prudential
  norms. That is precisely the case the layer keying got wrong, and nothing
  covered it before.
- **Still open:** `consistency_checks` compares layer against asset size but never
  category against asset size, so this class of contradiction is caught only in
  tests, not at runtime for a real customer profile.

## 2026-08-08 — CRILC reverted to the Rs.500cr keying (corrects the entry above/below)

- **The four templates were never a homogeneous group.** They were lumped under one
  rule because they share one pre-SBR `law_id` ("NBFC-ND-SI / NBFC-D Prudential
  Norms"), not because they share a scope. Re-keying all four as a batch was wrong.
- **`rbi_crilc` and `rbi_crilc_sma_weekly` are back on
  `nbfc_category: ["nd_si","deposit_taking"]`.** CRILC reporting and weekly
  SMA/default reporting apply to deposit-taking NBFCs and non-deposit-taking NBFCs
  at **Rs.500cr and above, independent of layer** — a Base Layer NBFC between
  Rs.500cr and Rs.1000cr is in scope. Keying them on `rbi_layer` made the product
  **miss** an obligation for exactly that band, which is the dangerous direction of
  error, unlike the over-compliance the original keying caused for CRAR.
- **`sbr_crar` and `rbi_concentration` stay on `rbi_layer: ["middle","upper"]`.**
  The 15% CRAR is a Middle/Upper Layer requirement, and the numerical concentration
  ceilings (25% single / 40% group) are ML/UL. Base Layer has only a board-approved
  internal concentration policy and no prescribed numerical limits — **which is a
  missing Base Layer template**, not something these two should cover.
- **`nbfc_category` is NOT vestigial.** It is the only way this rule DSL can express
  `(non-deposit AND >= Rs.500cr) OR deposit-taking` — keys within a rule are ANDed,
  so the derived-field-with-list-membership trick is doing real work. The original
  author was right. Consider renaming the emitted value `nd_si` -> `crilc_notified`
  so it stops reading as a live SBR classification.
- **Golden: profile C 61 -> 63** (gains CRAR + concentration; does not gain CRILC).
  A and B unmoved throughout.
- **Fixture bug found, deliberately NOT fixed:** profile C declares
  `nbfc_category: "icc"` at Rs.520cr, but `derive_regulatory_category` returns
  `"nd_si"` at >= Rs.500cr. `consistency_checks` only compares layer against asset
  size, never category, so nothing flags it. The 63 therefore rests on a wrong
  fixture — correcting it to `nd_si` would give 65 and put CRILC in scope.
  `test_profile_c_fixture_is_internally_inconsistent` pins this; delete that test in
  the same change that fixes the fixture.
- Sourcing unchanged: secondary analysis only, `rbi.org.in` unreachable.

## 2026-08-08 — Four ML/UL obligations re-keyed from `nbfc_category` to `rbi_layer`

- **`rbi_crilc`, `rbi_crilc_sma_weekly`, `sbr_crar`, `rbi_concentration` now key on
  `rbi_layer: ["middle","upper"]`**, replacing `nbfc_category: ["nd_si","deposit_taking"]`.
  SBR para 2.7 reads references to NBFC-ND-SI as NBFC-ML/UL and to NBFC-D as ML/UL,
  so the two rules denote the same set — but via a classification that SBR retired.
- **Why it mattered in practice:** the ND-SI line is Rs.500cr; the Middle-Layer line
  is Rs.1000cr. A non-deposit-taking NBFC between them is Base Layer under SBR but
  was being served four Middle-Layer obligations. Over-compliance, and the exact
  "marked N/A" churn signal the PRD treats as the content-accuracy proxy.
- **Golden movement is exactly profile C: 61 -> 65 applicable, 18 -> 14 not applicable.**
  Profiles A (Base) and B (Middle) are unmoved — B matched under both keys, A under
  neither. Profile C declares `rbi_layer: middle` with `nbfc_category: icc` at
  Rs.520cr, so it was previously excluded despite being Middle Layer.
  `test_middle_layer_obligations_key_off_layer_not_category` guards the re-key.
  The 367-instance goldens are unaffected (they run profile B).
- **`nbfc_category` now has ZERO consumers** in applicability rules (`rbi_layer` has
  10). `derive_regulatory_category` still populates it and `NDSI_ASSET_CR` still
  feeds that, but nothing downstream reads either. Both **kept, not deleted** —
  Rs.500cr appears to survive as a live threshold in the Prudential Framework for
  Resolution of Stressed Assets and in a group-asset aggregation rule, so CRILC in
  particular may need re-keying BACK onto an explicit Rs.500cr rule citing the
  instrument that retains it. If no obligation needs it, retire `nbfc_category` and
  `NDSI_ASSET_CR` together.
- **Sourcing caveat:** para 2.7 is from secondary analysis (Vinod Kothari, Lexology).
  `rbi.org.in`, `vinodkothari.com`, `lexology.com` and the FIDC mirror of the Master
  Direction are all unreachable through the sandbox egress proxy. **Confirm against
  primary text before this reaches a customer.**
- **Known asymmetry, deliberately left:** `consistency_checks` flags "answered Base
  but asset >= Rs.1000cr" and NOT the reverse. That is correct — RBI may place an
  NBFC in a higher layer than asset size implies (`derive_rbi_layer` says as much),
  so declaring Middle at Rs.520cr is legitimate, not a contradiction.

## 2026-08-08 — Regulatory thresholds carry provenance (`app/engines/thresholds.py`)

- **A legal threshold is declared exactly once, with its source.** The SBR
  Middle-Layer figure previously existed as a bare `1000` in THREE places:
  `derive_rbi_layer`, the `consistency_checks` contradiction test, and the
  near-boundary warning band (`900 <= asset <= 1100`, plus `Rs.1000cr` hardcoded
  in the message). One legal fact, four literals — updating one would have left
  the consistency engine silently disagreeing with the derivation.
- **`Threshold` carries `value / unit / source / lookup / status / verified_by /
  verified_on`**, reusing the library's `DRAFT_UNVERIFIED | VERIFIED` vocabulary.
  `VERIFIED` without both `verified_by` and `verified_on` raises — that invariant
  is what makes the status mean something.
- **Never edit `value` without editing `status`, `verified_by`, `verified_on` and
  `source` in the same change.** `python -m app.engines.thresholds` prints the
  reviewer worklist (what to look up, and where).
- **The near-boundary band is derived** (`near_band(pct=0.10)`), not hand-written,
  so it moves when the threshold moves.
- **Guard tests use the AST, not text scanning.** A line-based regex flagged regex
  quantifiers (`\d{5}`) and the `10` inside `0.10`. Integer *constants* via
  `ast.walk` are exact; a separate narrow check catches `Rs.<n>cr` baked into
  user-facing message strings.
- **All 5 thresholds ship DRAFT_UNVERIFIED and no value was changed.** Primary
  text (`rbi.org.in`, `rbidocs.rbi.org.in`) is unreachable from the sandboxed
  session — 502 through the egress proxy — and secondary summaries have already
  been observed conflating the 29 Apr 2026 Amendment Directions (Type I
  registration exemption, CoR surrender window to 30 Sep 2026) with an SBR
  Base/Middle/Upper layer revision, which they are **not**. Re-derive from the
  primary instrument only.
- **Pre-existing CI breakage fixed in the same pass:** `ruff check .` had 2 errors
  since `375c5a6` (unsorted imports in `test_api_smoke.py`; `B017` blind
  `pytest.raises(Exception)` in `test_postgres_hardening.py:162`, narrowed to
  `DBAPIError` to match lines 82/127 in that file). CI was red; the README badge
  is load-bearing.
- **README metrics re-verified** (they were stale by the rate-limiting commit):
  now **158 tests / 85% coverage**, 153 everywhere + 5 live-Postgres.

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
