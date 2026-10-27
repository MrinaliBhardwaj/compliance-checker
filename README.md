# Regis — Compliance Calendar Platform for Indian NBFCs

Regis turns a short company-profile questionnaire into a complete, dated compliance
calendar for a Non-Banking Financial Company (NBFC) in India — which obligations
apply, when each one is due, who owns it, what evidence proves it was done — and then
runs the day-to-day work on top of it: maker-checker approvals, evidence upload and
validation, reminders and escalations, an append-only audit trail, board reports and a
read-only compliance copilot.

It replaces the spreadsheet a compliance officer would otherwise build by hand from
RBI directions, the Companies Act, GST, income-tax, FEMA and labour law.

---

## Contents

1. [The problem it solves](#1-the-problem-it-solves)
2. [How it works, end to end](#2-how-it-works-end-to-end)
3. [Architecture](#3-architecture)
4. [The five deterministic engines](#4-the-five-deterministic-engines)
5. [Features, module by module](#5-features-module-by-module)
6. [Roles and the maker-checker lifecycle](#6-roles-and-the-maker-checker-lifecycle)
7. [Security and data integrity](#7-security-and-data-integrity)
8. [Getting started](#8-getting-started)
9. [Configuration](#9-configuration)
10. [Testing and quality](#10-testing-and-quality)
11. [Repository layout](#11-repository-layout)
12. [API overview](#12-api-overview)
13. [Design principles](#13-design-principles)
14. [Scope and known limitations](#14-scope-and-known-limitations)

---

## 1. The problem it solves

An NBFC's compliance team has to track filings and actions that come from many laws,
each with its own frequency, due-date rule and evidence. What applies depends on the
company: its RBI layer (base / middle / upper), whether it takes deposits, whether its
debt is listed, which states it operates in, its headcount, whether it has foreign
investment, and so on. Getting the list wrong means missed filings and penalties;
keeping it in a spreadsheet means no ownership, no evidence trail and no reminders.

Regis encodes that knowledge as an **obligation library** — **106 obligation
templates across 29 laws** — and a set of rule engines that decide applicability and
generate due dates. The officer answers questions about the company; Regis does the
rest and keeps doing it.

## 2. How it works, end to end

```mermaid
flowchart LR
    A[Sign up<br/>org + legal entity] --> B[Onboarding<br/>profile questionnaire]
    B --> C[Profile extraction<br/>normalise answers, derive<br/>layer / category, flag gaps]
    C --> D{Officer reviews<br/>and confirms}
    D --> E[Applicability engine<br/>which obligations apply, and why]
    E --> F[Instance generator<br/>dated instances for the FY,<br/>working-day adjusted]
    F --> G[Calendar & dashboard]
    G --> H[Maker-checker work<br/>assign → start → submit → approve]
    H --> I[Evidence upload<br/>classify → validate → link]
    G --> J[Reminders & escalations<br/>background worker]
    H --> K[(Append-only<br/>audit trail)]
    G --> L[Board report<br/>PDF / HTML / JSON]
```

1. **Sign up** creates an organisation, its first legal entity and a compliance-admin
   account, and lands on onboarding.
2. **Onboarding** asks for the company profile (asset size, turnover, listing, deposits,
   states, employees, foreign investment, …). A preview step shows what was derived
   from the answers, where each value came from, any contradictions, and the most
   useful questions still unanswered. Nothing is written until the officer confirms.
3. Optional **key dates** (AGM date, last TDS return, licence expiry) anchor filings that
   are due *after* those events. Without them those filings are parked as "awaiting a
   date" rather than given a guessed deadline.
4. **Generation** decides applicability and creates every dated obligation instance
   for the current financial year (April–March), starting from the onboarding date —
   periods that fell due before the company started using Regis are not reported as
   overdue. In the last 60 days of a financial year the next year is generated too,
   and a monthly job keeps rolling calendars forward.
5. The team then **works** the calendar: the dashboard ranks open items by risk and
   urgency; preparers do the work and submit it; a checker approves it once the
   required evidence is attached; reminders and escalations go out automatically.

## 3. Architecture

```mermaid
flowchart TB
    subgraph Browser
        UI[Next.js 14 app<br/>React Query, httpOnly session cookie]
    end
    subgraph Backend [FastAPI modular monolith]
        API[REST API<br/>10 modules]
        ENG[5 deterministic engines<br/>pure functions, golden-tested]
        AI[Optional AI seams<br/>Claude, OCR]
    end
    W[Arq worker<br/>overdue count · reminders · FY roll-over]
    PG[(PostgreSQL<br/>row-level security,<br/>append-only audit)]
    R[(Redis)]
    S3[(MinIO / AWS S3<br/>evidence files)]
    UI -->|/api| API
    API --> ENG
    API --> AI
    API --> PG
    API --> S3
    W --> PG
    W --> R
    API --> R
```

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (App Router), TypeScript, React Query |
| API | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 16 with row-level security (SQLite for fast tests) |
| Background jobs | Arq on Redis |
| File storage | S3-compatible: MinIO locally, AWS S3 (KMS-encrypted) in production |
| AI (optional) | Anthropic Claude for document classification and phrasing; Tesseract / pypdf / python-docx for text extraction |
| Deployment target | AWS `ap-south-1` (data residency in India) |

The backend is a **modular monolith**: one deployable FastAPI app split into modules
(`auth`, `team`, `onboarding`, `obligations`, `documents`, `notify`, `reports`,
`legal_updates`, `copilot`, `audit`). Business rules live in pure engine functions; the
modules persist results and write audit rows.

## 4. The five deterministic engines

The engines in `backend/app/engines/` are plain Python functions over dicts — no
database, no network — and are the source of truth for every compliance decision.
Their outputs on reference profiles are locked by **golden regression tests**; a change
that moves any of these numbers fails the suite.

| Engine | What it decides | Golden result |
|---|---|---|
| **Profile extraction** | Normalises raw questionnaire answers, derives fields (e.g. RBI layer from asset size), records provenance and confidence per field, finds contradictions and ranks gap questions | clean profile → **99** applicable obligations; messy → 61/33 with the FDI gap ranked first |
| **Applicability** | Evaluates each template's rule against the profile: applicable / not applicable / needs review, with a rationale | Profile A = 69/1/39 (22 laws), B = 100/1/13 (26 laws), C = 61/27/18 |
| **Instance generator** | Turns due rules (day-of-month, days after quarter-end, annual, anchored to an event, …) into dated instances inside a window, adjusting to working days | Profile B, FY2026-27 → **367** dated, 21 event-driven, 3 continuous, 92 working-day-adjusted |
| **Document intelligence** | Classifies uploaded evidence, extracts fields, validates it against the obligation (entity, period, form), de-duplicates, computes evidence completeness | 192 of 195 reference documents mapped (**98.4%**) |
| **Copilot** | Answers questions about the org's own obligations from structured data, with citations, confidence and role scoping; escalates requests to *act* | admin sees 18 vs preparer 13; structured answers 0.97 confidence; unverified content capped at 0.70 |

Every template ships as **`DRAFT_UNVERIFIED`**. Until a qualified CS/CA marks a
template `VERIFIED`, applicability confidence is capped at 0.70 and results are flagged
*provisional* — engine correctness is proven by tests, legal currency of the library is
a human verification task.

## 5. Features, module by module

**Auth & team** — sign-up, login and logout with an httpOnly session cookie; invite
members by email with single-use invite links; roles `compliance_admin`, `head` and
`preparer`; role changes and removal (with reassignment of the removed member's
obligations; the last admin can never be removed). Emails are matched
case-insensitively. Login is rate-limited per account and per IP, sign-up per IP.

**Onboarding** — the three-step wizard (profile → review derived values and
contradictions → optional key dates and generate). Re-running it after the business
changes reconciles the calendar: new obligations are added, ones that no longer apply
are deactivated (never deleted) and disappear from every view.

**Obligations** — the tracker (filter by status, category or text; group by urgency;
bulk start / submit / approve / assign / mark N/A with per-row results), the side sheet
for one obligation (rationale, penalty note, evidence completeness, linked documents,
activity) and the dashboard (overdue, due in 7 days, awaiting review, filed, health
score, risk-ranked priority queue). *Overdue* is computed from the due date when read,
never stored, so every screen agrees.

**Evidence** — upload (size-capped), automatic text extraction (PDF, Word, images via
OCR), AI classification when an API key is configured or manual classification
otherwise, validation against the target obligation, and a human-confirmed link.
Exact duplicates are blocked. Files are stored per organisation in S3/MinIO.

**Notifications** — a risk-weighted reminder schedule: **7 / 3 / 1** days before the due
date (high-risk obligations **15 / 7 / 3 / 1**), a due-day reminder, and an overdue
escalation ladder — **+1 day** owner, **+3 days** compliance admin, **+7 days** head.
Assignment, review-requested and rejection notifications are sent on lifecycle events.
Channels: email (SES) and Slack, recorded in-app even when no channel is configured.

**Background worker** (Arq, times in IST) — 00:30 daily overdue count, 06:00 daily
reminders and escalations, 01:00 on the 1st of each month calendar roll-over into the
next financial year.

**Reports** — a board-ready compliance status report (health score, overdue,
due-this-week, awaiting review, filed with evidence counts, by-category breakdown) as
JSON, HTML or PDF, marked *provisional* while the library is unverified.

**Legal updates** — a curated feed of regulatory changes. Each update carries an
applicability filter that is matched deterministically against each organisation's
profile, so every tenant sees whether it is affected and can mark it reviewed.
Publishing is limited to an allow-listed content team.

**Audit trail** — every state change (transitions with reasons, overrides,
self-approvals, uploads, links, team changes, calendar generation) is recorded in an
append-only log, filterable by action and viewable per obligation.

**Copilot** — ask "what's overdue?", "what's due this week?" or "what does DNBS-02
require?" and get an answer grounded in the organisation's own calendar, with
citations and confidence. It is read-only: requests to approve, file or change
anything are refused and escalated to a human.

## 6. Roles and the maker-checker lifecycle

| Capability | compliance_admin | head | preparer |
|---|:-:|:-:|:-:|
| Generate / re-generate the calendar | ✓ | | |
| Assign obligations | ✓ | | |
| Start work | ✓ | ✓ | ✓ (own) |
| Submit for review (maker) | ✓ | | ✓ (own) |
| Approve / reject (checker) | ✓ | ✓ | |
| Mark not applicable, reopen | ✓ | | |
| Upload evidence | ✓ | ✓ | ✓ (own) |
| Export reports, view audit trail | ✓ | ✓ | |

Preparers see and act only on obligations assigned to them.

```mermaid
stateDiagram-v2
    [*] --> pending
    pending --> in_progress: start
    pending --> ready_for_review: submit
    in_progress --> ready_for_review: submit (maker)
    ready_for_review --> completed: approve (checker, evidence gate)
    ready_for_review --> in_progress: reject (reason required)
    pending --> not_applicable: mark N/A (reason required)
    in_progress --> not_applicable: mark N/A
    ready_for_review --> not_applicable: mark N/A
    completed --> in_progress: reopen (reason required)
    not_applicable --> in_progress: reopen
```

- **Evidence gate** — approval requires the obligation's primary evidence to be linked.
  An admin or head can override the gate, but only with a written reason, and the
  override is flagged in the audit trail.
- **Maker ≠ checker** — the system records who submitted. If the same person approves,
  a reason is required and the approval is recorded as a *self-approval* (allowed so a
  single-admin organisation can still operate, but never silently).
- **Reasons are enforced by the API** (at least 8 characters) for reject, mark N/A,
  reopen, evidence override, override-linking a mismatched document and
  self-approval — not just by the user interface.
- *Overdue* is not a state: an item is shown as overdue while it is pending or in
  progress past its due date, and it can still be started and submitted.

## 7. Security and data integrity

- **Tenant isolation in the database.** Every tenant table uses PostgreSQL
  `FORCE ROW LEVEL SECURITY`; each request sets `app.current_org` for its transaction,
  so a query can only see its own organisation's rows even if application code has a
  bug. Tests for this run as a non-superuser role, because superusers bypass RLS.
- **Authorization is re-checked on every request** against the member's current
  membership — removing a member or changing a role takes effect immediately, not
  when their session expires.
- **Append-only audit log**, enforced by a database trigger that blocks `UPDATE` and
  `DELETE`.
- **Session handling** — an httpOnly cookie for the browser (the token is never read
  by JavaScript); a bearer token is also returned for API clients.
- **Brute-force protection** on login, sign-up and invite acceptance (per IP and per
  account; Redis-backed when available).
- **Evidence storage** — files are keyed by organisation; paths are resolved and
  checked against the caller's organisation, uploads are size-capped, and production
  storage is KMS-encrypted S3.
- **Field-level encryption** for identifiers such as PAN, CIN and NBFC registration
  number (Fernet, keyed by `REGIS_FIELD_KEY`, required outside development).
- **AI is read-only.** No AI path can move an obligation to a terminal state or link a
  document; every such action is human-confirmed.

## 8. Getting started

**Prerequisites:** Docker Desktop, Python 3.12, Node.js 20.

### Option A — full stack with Docker (recommended)

```bash
git clone https://github.com/MrinaliBhardwaj/compliance-checker.git
cd compliance-checker
docker compose up --build -d      # postgres, redis, minio, qdrant, api, worker

cd frontend
npm install
npm run dev                        # http://localhost:3000
```

On first boot the API applies all database migrations and loads the obligation
library (29 laws, 106 templates). Open http://localhost:3000, choose **Create
account**, and you are taken straight into onboarding.

| Service | URL |
|---|---|
| Web app | http://localhost:3000 |
| API + interactive docs | http://localhost:8000/docs |
| MinIO console (evidence files) | http://localhost:9001 — `regis` / `regis-secret` |

To use another port for the web app, run `npx next dev -p 3001`; the app proxies
`/api/*` to the API on port 8000. Stop everything with `docker compose down` (add `-v`
to also delete the data).

### Option B — backend only, no Docker (SQLite)

```bash
cd backend
pip install -e ".[dev,ocr]"
export REGIS_DATABASE_URL="sqlite+pysqlite:///dev.db" REGIS_JWT_SECRET=dev
alembic upgrade head               # create the schema
python -m app.seed.cli             # load the obligation library
uvicorn app.main:app --port 8000   # http://localhost:8000/docs
```

SQLite has no row-level security; use it for local exploration and tests, and
PostgreSQL for anything multi-tenant.

### Make shortcuts

| Command | What it does |
|---|---|
| `make install-dev` | install backend dependencies |
| `make up` | `docker compose up --build -d` |
| `make dev` | start services, apply migrations and run the tests |
| `make test` | run the backend test suite |
| `make lint` / `make format` | check / fix lint, formatting and imports (ruff, black, isort) |
| `make ci-check` | lint plus `mypy` type checks |
| `make build-frontend` | production build of the web app |

## 9. Configuration

Settings are read from environment variables with the prefix `REGIS_` (or from
`backend/.env`; see `backend/.env.example`). The most important ones:

| Variable | Default | Purpose |
|---|---|---|
| `REGIS_ENV` | `dev` | `dev` / `staging` / `prod`; production enforces secrets and S3 storage |
| `REGIS_DATABASE_URL` | local Postgres | SQLAlchemy URL |
| `REGIS_REDIS_URL` | `redis://localhost:6379/0` | worker queue and shared rate-limit counters |
| `REGIS_JWT_SECRET` | dev placeholder | session signing key — **must** be changed outside dev |
| `REGIS_ACCESS_TOKEN_TTL_MINUTES` | `720` | session length |
| `REGIS_FIELD_KEY` | — | Fernet key for PAN/CIN encryption (required in prod) |
| `REGIS_S3_BUCKET`, `REGIS_S3_ENDPOINT_URL`, `REGIS_S3_ACCESS_KEY`, `REGIS_S3_SECRET_KEY` | — | evidence storage; setting an endpoint selects S3/MinIO, otherwise local files in dev |
| `REGIS_ANTHROPIC_API_KEY`, `REGIS_ANTHROPIC_MODEL` | — / `claude-sonnet-5-5` | optional AI document classification; without a key uploads are classified manually |
| `REGIS_SLACK_WEBHOOK_URL`, `REGIS_EMAIL_FROM` | — | notification channels |
| `REGIS_CONTENT_ADMIN_EMAILS` | — | who may publish legal updates |
| `REGIS_MAX_UPLOAD_MB` | `25` | evidence upload limit |
| `REGIS_LOGIN_MAX_ATTEMPTS`, `REGIS_LOGIN_WINDOW_SECONDS` | `10`, `300` | rate limiting |
| `REGIS_CORS_ALLOW_ORIGINS` | — | only needed if a browser calls the API directly |

## 10. Testing and quality

```bash
cd backend
python -m pytest -q          # 177 passed, 6 skipped
```

**183 tests** in three tiers, about **85%** line coverage:

| Tier | Folder | What it proves |
|---|---|---|
| Golden | `tests/golden/` | the five engines reproduce their verified reference results exactly |
| Unit | `tests/unit/` | lifecycle rules, reminder schedule, storage adapters, OCR, LLM parsing, calendar windows |
| Integration | `tests/integration/` | the full chain through the database and the HTTP API: onboarding, maker-checker, evidence, notifications, reports, team, audit, migrations |

The 6 skipped tests need external pieces: 5 row-level-security and append-only tests
need a live PostgreSQL, and 1 OCR test needs the Tesseract binary. With the Docker
stack running:

```bash
REGIS_TEST_PG_URL=postgresql+psycopg://regis_app:regis_app_pw@localhost:5432/regis_test \
  python -m pytest -q        # 182 passed
```

`regis_app` is a non-superuser role created by the compose `postgres-init` service — do
not point these tests at the `regis` superuser, which bypasses RLS.

A migration test checks that the schema produced by running every migration is
identical to the SQLAlchemy models, so a model change without a migration fails.

Code style: `ruff`, `black` (≥ 26.1, < 27), `isort` and `mypy` for the backend
(`make ci-check` runs all four; `pre-commit install` runs them on every commit); the
frontend is type-checked by `npm run build`.

## 11. Repository layout

```
backend/
  app/
    engines/        the five deterministic engines
    modules/        API modules: auth, team, onboarding, obligations, documents,
                    notify, reports, legal_updates, copilot, audit
    models/         SQLAlchemy models (19 tables)
    core/           config, database + tenant scoping, security, rate limiting, storage, audit
    ai/             optional LLM, OCR and RAG seams
    jobs/worker.py  Arq background jobs
    seed/           obligation library (JSON) and loader
  alembic/          database migrations 0001–0010
  tests/            golden, unit and integration tests
frontend/
  app/              pages: dashboard, obligations, onboarding, evidence, legal-updates,
                    reports, audit, notifications, team, accept (invite)
  components/       app shell, obligation side sheet, command palette, copilot, UI kit
  lib/              API client, auth context, formatting, toasts, theme
scripts/            dev.sh (services + migrations + tests), demo.sh
docker-compose.yml  postgres · redis · minio · qdrant · api · worker
Makefile            developer shortcuts
```

## 12. API overview

**41 endpoints across 10 modules**, plus `/health`, `/ready` and `/metrics`. Full,
interactive documentation is served at `/docs` when the API is running (disabled in
production).

| Module | Endpoints |
|---|---|
| `/auth` | `signup`, `login`, `logout`, `me`, `accept-invite` |
| `/team` | invite, list members, list assignable, change role, remove (with reassignment) |
| `/onboarding` | `profile/preview` (no write), `calendar/generate` |
| `/obligations` | list instances (filters + paging), instance detail, completeness, dashboard; actions `assign`, `start`, `submit`, `approve`, `reject`, `mark_na`, `reopen` |
| `/documents` | upload, classify, link to an obligation, list |
| `/notifications` | inbox, mark read, run reminders |
| `/reports` | compliance report as JSON, HTML or PDF |
| `/legal-updates` | list (with per-tenant match), publish, review |
| `/copilot` | `ask` |
| `/audit` | feed, action list, per-record timeline |

## 13. Design principles

- **Deterministic engines are the source of truth; AI only assists.** Applicability,
  due dates and completion are computed by tested rules. AI may classify a document or
  phrase an answer, but a person confirms anything that changes compliance state.
- **Defensible by construction.** Every decision has a reason, every change is in an
  append-only trail, and unverified legal content is labelled provisional everywhere
  it appears.
- **Honest calendars.** No invented dates: obligations anchored to an unknown event wait
  for the date, and history from before onboarding is not counted as missed.
- **Isolation in the database, not just the code.** Tenant boundaries are enforced by
  PostgreSQL row-level security.
- **Golden tests are the contract.** Engine behaviour changes only deliberately, with
  the expected numbers updated in the same change.

## 14. Scope and known limitations

**Deliberately out of scope for Phase 1:** contract, litigation, internal-audit, IFC and
ERM modules; autonomous AI actions and AI legal drafting; government-portal
integrations; native mobile apps; predictive scoring; a public API; jurisdictions
outside India.

**Known limitations**

- The obligation library is `DRAFT_UNVERIFIED` until reviewed by a qualified CS/CA.
- The copilot answers from structured data only; retrieval over regulatory text
  (Qdrant is provisioned for it) is not wired yet.
- Single sign-on is planned; today there is email and password login.
- Each organisation has the legal entity created at sign-up; creating further
  entities is not yet exposed.
- Evidence entity matching uses PAN/CIN; GSTIN and TAN are not stored yet.
- The frontend has no automated tests; it is covered by type-checking, the production
  build and manual/browser testing.
