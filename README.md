# Regis — AI-Assisted Compliance Platform for Indian NBFCs

An NBFC compliance officer answers a short profile questionnaire and gets a complete,
accurate compliance calendar — obligations, due dates, owners, evidence repository,
an append-only audit trail, and a read-only copilot — replacing weeks of spreadsheet
setup.

> **Design contract:** all AI is read-only/assistive and human-confirmed; the
> deterministic engines are the source of truth; every obligation ships
> `DRAFT_UNVERIFIED` until a content-team flag flips it; designed for AWS **ap-south-1**.

## What's inside (verified by the test suite)

| | |
|---|---|
| Rule engines | **5** deterministic engines — applicability, instance generation, profile extraction, document intelligence, copilot — locked behind golden regression tests |
| Obligation library | **106** obligation templates spanning **29** Indian laws (RBI, Companies Act, GST, FEMA, labour, tax) |
| Calendar generation | the reference profile over a full FY → **367** dated obligation instances (golden-locked), working-day adjusted, in well under a second. A new company's calendar starts on its onboarding day |
| Document intelligence | **98.4%** evidence-to-obligation classification on the reference corpus (192/195) |
| API surface | **41** REST endpoints across 10 modules, plus `/health`, `/ready`, `/metrics` |
| Database | **19** PostgreSQL tables, row-level security (tenant isolation), append-only audit log, Alembic migrations |
| Tests | **183** tests, ~85% coverage — 177 run anywhere; 5 RLS/append-only tests need live Postgres, 1 OCR test needs the tesseract binary |

### Golden results (test-locked)

| Engine | Result |
|---|---|
| Applicability | A=69/1/39 (22 laws), B=100/1/13 (26 laws), C=61/27/18 |
| Instance generator | Profile B → **367** dated, 21 event-driven, 3 continuous, 92 working-day-adjusted |
| Profile extraction | clean → **99** applicable; messy → 61/33, FDI gap ranked above intl-txn |
| Document intelligence | 192 evidence mapped, 3 OTHER (98.4%); TDS-challan all-PASS; dedupe; completeness |
| Copilot | admin 18 vs preparer 13; structured 0.97; unverified 0.70 provisional; 3 escalations |

The engines are ported from the original reference implementations and adapted;
their behaviour is locked by these golden tests.

## Modules

| Module | What it does |
|---|---|
| Auth & Team | signup/login, httpOnly-cookie JWT, RBAC (admin / head / preparer) re-checked against the membership on every request, invites, role management; SSO planned |
| Onboarding | profile preview (provenance + gap questions) → human-confirmed calendar generation, with optional AGM / TDS-return / licence dates |
| Obligations | tracker, dashboard, **maker-checker lifecycle** (assign → start → submit → approve/reject → mark N/A → reopen); self-approval only with a recorded reason |
| Evidence | upload → AI classify/extract (optional) → human-confirmed link → completeness gate; exact-duplicate detection; stored in S3 / MinIO |
| Audit trail | every state change, append-only (DB trigger) — filterable trail for auditors and RBI inspection |
| Notifications | risk-weighted reminders, overdue escalation ladder, monthly calendar roll-over (Arq worker) |
| Reports | board-ready compliance status as JSON / HTML / PDF |
| Legal updates | curated feed with deterministic applicability matching |
| Copilot | read-only, deterministic, structured-first, grounded-or-silent Q&A with citations; escalates action requests. A RAG seam (`app/ai/rag.py`, Qdrant) is stubbed, not wired |

## Stack

FastAPI · SQLAlchemy 2 · PostgreSQL (RLS) / SQLite (tests) · Alembic · Arq + Redis ·
MinIO / S3 · Next.js 14 · TypeScript · React Query. AI seams target Anthropic Claude;
deterministic-only offline mode by default.

## Repository layout

```
backend/                 FastAPI modular monolith (Python 3.12)
├─ app/engines/          the 5 engines (pure, deterministic, golden-locked)
├─ app/ai/               LLM / OCR seams (graceful offline fallback); RAG stub
├─ app/models/           SQLAlchemy models
├─ app/modules/          auth · team · onboarding · obligations · documents · notify · reports · legal_updates · copilot · audit
├─ app/jobs/             Arq worker (overdue count, reminders/escalations, FY roll-over)
├─ app/seed/             obligation-library seed + loader CLI
├─ alembic/              migrations 0001–0010
└─ tests/                golden · unit · integration (incl. HTTP API smoke)
frontend/                Next.js 14 App Router (the full Phase-1 UI)
scripts/                 dev.sh (migrations + tests), demo.sh
docker-compose.yml       postgres · redis · minio · qdrant · api · worker (no frontend service)
Makefile                 developer shortcuts
```

## Run it

### Full stack (Docker) + UI
```bash
docker compose up --build -d     # api on :8000 (migrates + seeds on boot), worker, postgres, redis, minio, qdrant
cd frontend
npm install && npm run dev       # http://localhost:3000 (proxies /api -> :8000)
```
Sign up and you land on onboarding; answer the questionnaire and the dashboard fills
with your calendar, tracked from today. Filings that depend on a date you haven't
given (AGM, TDS return, licence expiry) wait as "awaiting a date" rather than being
guessed. API docs: http://localhost:8000/docs.

Evidence is stored in MinIO (S3-compatible; the bucket is created on first upload),
the same code path production uses against AWS S3. Qdrant starts but isn't used yet.

### Backend only (SQLite quickstart, no infra)
```bash
cd backend
pip install -e ".[dev,ocr]"
REGIS_DATABASE_URL="sqlite+pysqlite:///dev.db" REGIS_JWT_SECRET=dev alembic upgrade head
REGIS_DATABASE_URL="sqlite+pysqlite:///dev.db" REGIS_JWT_SECRET=dev python -m app.seed.cli
REGIS_DATABASE_URL="sqlite+pysqlite:///dev.db" REGIS_JWT_SECRET=dev uvicorn app.main:app --port 8000
```
For Postgres, copy `backend/.env.example` to `backend/.env` and set `REGIS_*`.

## Test and lint

```bash
cd backend
python -m pytest -q              # 177 passed, 6 skipped (Postgres-only + tesseract-only)

# Postgres-only guarantees (RLS + append-only audit). regis_app is the non-superuser
# that compose's postgres-init creates; never use the `regis` superuser here,
# superusers bypass RLS even with FORCE.
REGIS_TEST_PG_URL=postgresql+psycopg://regis_app:regis_app_pw@localhost:5432/regis_test \
  python -m pytest -q
```

`make lint` runs ruff, black (≥26.1, <27), isort and mypy; `make format` applies fixes;
`make build-frontend` runs the Next.js production build (which type-checks).
`backend/.pre-commit-config.yaml` runs the same checks on commit after `pre-commit install`.

## The two hard gates, in the data model (not just docs)

1. **`DRAFT_UNVERIFIED` content gate** — `obligation_templates.verification_status`
   is read at runtime: until a template is `VERIFIED`, applicability confidence is
   capped at 0.70 and output is flagged `library_provisional`; the Copilot caps
   unverified answers at 0.70 + provisional. The seed loader never auto-promotes.
2. **Read-only / human-confirmed AI** — no endpoint lets an AI path write a terminal
   compliance state. Status changes go through maker-checker; document links require
   human confirmation; the Copilot has no write path. `audit_log` is append-only
   (DB trigger, migration `0002`).

## Architecture notes

- **Tenant isolation** is enforced in Postgres with `FORCE ROW LEVEL SECURITY`; each
  request sets the `app.current_org` GUC, and `app.bootstrap` is used only on the
  login path.
- **Overdue is computed on read, never stored**, so the dashboard, reports and
  reminders always agree.
- **Audited decisions need a reason at the API** (8+ characters): reject, mark N/A,
  reopen, evidence override, override-link and self-approval.
- **Migrations:** `0001` is frozen DDL, so every model change needs its own migration;
  a test fails if the migrated schema and the models ever differ.

## Out of scope (Phase 1)

Contract/litigation/audit/IFC/ERM modules · autonomous actions · AI legal drafting ·
government-portal integrations · native mobile · predictive ML scoring · public API ·
multi-jurisdiction. The V1 rule: if the AI would *act in the external world*, it's out.

## Content-team note

Engine correctness ≠ library legal correctness. The golden tests prove the engines
compute correctly; whether each obligation's rule, due date and required evidence is
*legally current* is a qualified CS/CA verification task against the
`DRAFT_UNVERIFIED` gate.
