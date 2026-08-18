# Security posture — Regis

For the security questionnaire that arrives with every NBFC deal.

**Every claim here is verifiable in this repository**, with the file named. Where
something is not yet true, it says so — an overstated control is worse than a
missing one, because procurement will check.

Last verified: 2026-08-18, commit on `claude/startup-guidance-nfpbqu`.

---

## 1. What is not true yet

Read this section first.

| Gap | Status |
|---|---|
| **Nothing is deployed.** `infra/terraform` is written and has never been applied. | Data residency is *intent*, not evidence. Do not claim India residency of a running system until it runs. |
| **No third-party penetration test.** Two internal security reviews only (`DECISIONS.md`, 2026-07-12 and 2026-07-24). | Budget one before a customer with a real security team. |
| **No SOC 2 / ISO 27001.** | Not started. Say so plainly if asked. |
| **The obligation library is unverified.** All 107 templates ship `DRAFT_UNVERIFIED`. | This is a *content* disclosure, not a security one, but it belongs in the same honest conversation. |
| **No formal incident response plan.** Logging and error tracking exist; the runbook does not. | Write it before the first pilot. |

---

## 2. Tenant isolation

The control most likely to be asked about, and the one most likely to be
silently broken elsewhere.

- **Postgres row-level security with `FORCE ROW LEVEL SECURITY`** on every tenant
  table (migration `0002_rls_and_append_only_audit.py`). A session with no
  `app.current_org` GUC is blocked on every tenant table — the default is denial,
  not exposure.
- **The GUC is set per request** from the caller's JWT, in `app/core/deps.py`.
- **One deliberate cross-tenant read exists**: login must resolve which org a
  user belongs to before any scope exists. It runs under a separate, read-only
  `app.bootstrap` GUC honoured **only** by the `memberships` USING clause — never
  WITH CHECK, so bootstrap cannot forge a membership — and the sole caller filters
  by user identity (migration `0003`, `app/core/db.set_bootstrap`).
- **Verified against live Postgres in CI**, under a **non-superuser role**.
  Superusers bypass RLS entirely, so testing as one would make every isolation
  test pass while the boundary was inert (`tests/integration/test_postgres_hardening.py`).
- **Evidence objects are keyed by org** (`<organization_id>/...` in
  `app/core/storage.py`), so a signed URL or a listing cannot cross tenants.

## 3. Authentication and session handling

- **Session JWT lives in an httpOnly cookie**, never in localStorage — an XSS
  cannot read it. `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` everywhere
  except local dev.
- **CSRF** is covered by `SameSite=Lax` plus every mutation being non-GET plus a
  same-origin proxy; the SPA never makes a cross-origin call.
- **Passwords** are bcrypt-hashed, minimum 8 characters.
- **RBAC** with three roles (admin / head / preparer), enforced server-side.
  Preparers are scoped to their own instances, not merely their org.
- **Removal is revocation**: login accepts only `status='active'` memberships,
  and invite acceptance is single-use, so a removed member's old link cannot
  reinstate them. Accepting also requires proving the password — possession of
  the link is not identity.

## 4. Rate limiting and abuse

- **Login and invite acceptance** are throttled per source IP *and* per targeted
  account, checked **before** the bcrypt verify so a flood cannot burn CPU.
- **A global per-IP ceiling** across the API (default 300/60s), and a tighter
  **per-organisation** limit on the expensive routes — calendar generation and
  evidence upload (default 10/60s).
- Redis-backed in production so the budget is shared across workers and
  replicas; an in-process counter would hand an attacker a fresh budget per
  worker. **Fails open** on backend errors: throttle attackers, don't lock real
  users out over a Redis hiccup.
- **Uploads are size-capped** (default 25 MB), read in bounded chunks.

## 5. Auditability

- **Append-only audit log**, enforced in the database — `UPDATE` and `DELETE` are
  rejected by trigger, not by convention (migration `0002`, verified in CI).
- Every state change is recorded: assignment, start, submit, approve, reject,
  reopen, evidence link, override.
- **Evidence overrides are audited**: linking a document that failed an
  entity-match check is possible and permanently recorded.
- The S3 bucket is **versioned** — a deleted or overwritten object would
  otherwise break the trail an inspection follows.

## 6. Data protection

- **Encryption in transit**: TLS everywhere; the evidence bucket policy denies
  non-TLS requests outright.
- **Encryption at rest**: KMS on RDS, ElastiCache, and S3, with key rotation
  enabled (one project key, `infra/terraform/main.tf`).
- **Field-level encryption on sensitive identifiers** — CIN and PAN are stored
  through a Fernet-backed `EncryptedStr` column type (`app/models/types.py`,
  applied in `app/models/tenancy.py`); `REGIS_FIELD_KEY` is required outside dev.
- **Credentials are not in source or images**: RDS generates its master password
  into Secrets Manager, so no literal enters Terraform state.

## 7. Operations

- **Structured JSON logging** on every request and background job, carrying
  organisation context; each request gets an id echoed as `x-request-id`
  (`app/core/logging.py`).
- **Error tracking** via Sentry when `REGIS_SENTRY_DSN` is set.
- **The nightly job isolates failures per organisation** — one tenant's bad data
  cannot stop another tenant's overdue flips or reminders, and the failure is
  logged with its org id rather than disappearing.
- **Notification delivery is recorded** (`sent` / `failed` plus the error), so
  "was the reminder actually delivered" is answerable.
- **API docs are disabled in production** (`/docs`, `/openapi.json` off when
  `REGIS_ENV=prod`).
- **CORS is off by default**; specific origins opt in, never `*`.

## 8. Testing

- **182 backend tests** (86% coverage) plus **6 end-to-end browser tests**
  covering signup → calendar, evidence upload → link → audit, and invite →
  accept.
- RLS and append-only enforcement run against **live Postgres** in CI, as a
  non-superuser.
- Regulatory constants carry provenance and a verification status; a value cannot
  be changed without changing its sign-off (`app/engines/thresholds.py`).

---

## The one thing that would void section 2

**The application must never connect to Postgres as a superuser.** Superusers
bypass row-level security, so every tenant boundary would be inert while every
test still passed. Create a dedicated non-superuser role and point the app at
that — never at the RDS master user.
