# Regis — AI-Native Compliance Platform for Indian NBFCs (Phase 1)

A focused, AI-**assisted** compliance platform: an NBFC compliance officer answers a
short profile questionnaire and gets a complete, accurate compliance calendar —
obligations, due dates, owners, evidence repository, and a read-only Copilot —
replacing weeks of spreadsheet setup.

<!-- CI badges -->
[![CI](https://github.com/MrinaliBhardwaj/compliance-checker/actions/workflows/ci.yml/badge.svg)](https://github.com/MrinaliBhardwaj/compliance-checker/actions/workflows/ci.yml)


> **Design contract (honored throughout):** all AI is read-only/assistive and
> human-confirmed; the deterministic engines are the source of truth; every
> obligation ships `DRAFT_UNVERIFIED` until a content-team flag flips it; designed
> for AWS **ap-south-1**.

## What's built (and proven)

The verified reference engines are ported and adapted into `backend/app/engines/`
(the code differs from the original reference implementations), and their behaviour is locked by golden
regression tests reproducing every quoted figure:

| Engine | Golden result (test-locked) |
|---|---|
| Applicability | A=69/1/39 (22 laws), B=100/1/13 (26 laws), C=61/27/18 |
| Instance generator | Profile B → **367** dated, 21 event-driven, 3 continuous, 92 working-day-adjusted |
| Profile extraction | clean → **99** applicable; messy → 61/33, FDI gap ranked above intl-txn |
| Document intelligence | 192 evidence mapped, 3 OTHER (98.4%); TDS-challan all-PASS; dedupe; completeness |
| Copilot | admin 18 vs preparer 13; structured 0.97; unverified 0.70 provisional; 3 escalations |

Around that core: Postgres schema + Alembic migrations (RLS + append-only audit),
an idempotent seed loader, the persisted **profile → applicability → instances**
chain, and a FastAPI modular monolith covering the full Phase-1 surface:

| Module | What it does |
|---|---|
| Auth | self-serve signup/login, httpOnly-cookie JWT, RBAC re-checked against the membership on every request; SSO planned |
| Onboarding | profile preview (provenance + gaps) → human-confirmed calendar generation |
| Obligations | tracker, dashboard, **Maker-Checker lifecycle** (assign/start/submit/approve/reject/mark-NA/reopen) |
| Evidence | upload → AI classify/extract (optional seam) → human-confirmed link → completeness gate |
| Notifications | risk-weighted reminders, overdue escalation ladder, assignment + review routing (email/Slack seam) |
| Reports | board-ready compliance status as JSON/HTML/**PDF** (pluggable engine + dependency-free fallback) |
| Legal updates | curated feed, optional AI summary, **deterministic applicability match reusing the obligation engine** |
| Copilot | read-only, deterministic, structured-first, grounded-or-silent Q&A; escalates action/legal-opinion requests. The RAG seam (`app/ai/rag.py`, Qdrant) is stubbed and not called yet |

Background: an Arq worker counts overdue items nightly (overdue is computed on read,
never stored), dispatches reminders and escalations idempotently, and rolls each
calendar into the next FY in its last 60 days. Frontend: Next.js 14 app — onboarding,
dashboard, obligations tracker with Maker-Checker sheet, evidence, team and invites,
notifications, legal updates, audit trail, reports, command palette and Copilot.

```
Test status: 160 passed, 5 skipped (Postgres-only RLS/append-only tests; 165 pass with Postgres).
```

## Repository layout

```
regis/
├─ backend/                 FastAPI modular monolith (Python 3.12)
│  ├─ app/engines/          ← ported from the verified references (pure, deterministic, golden-locked)
│  ├─ app/ai/               LLM / OCR seams (graceful offline fallback); RAG stub, not wired
│  ├─ app/models/           SQLAlchemy models (1:1 with migrations)
│  ├─ app/modules/          auth · team · onboarding · obligations · documents · notify · reports · legal_updates · copilot · audit
│  ├─ app/jobs/             Arq worker (overdue count, reminders/escalations, FY roll-over)
│  ├─ app/seed/             obligation-library loader + CLI
│  ├─ alembic/              migrations (baseline + RLS/append-only hardening)
│  └─ tests/                golden (the contract) · unit · integration (incl. HTTP API smoke)
├─ frontend/                Next.js 14 App Router (the full Phase-1 UI)
└─ docker-compose.yml       postgres · redis · minio · qdrant · api · worker (no frontend service)
```

## Quick start

### Run the tests (no services needed)
```bash
cd backend
pip install -e ".[dev]"
python -m pytest -q            # 160 passed, 5 skipped
```

### Run the full stack (Docker)
```bash
docker compose up --build       # api on :8000 (migrates + seeds on boot), worker, db, redis, minio, qdrant
# API docs: http://localhost:8000/docs   — then run the frontend (below) for the UI
```

Evidence is stored in MinIO (S3-compatible; the bucket is created on first upload), the
same `S3Storage` path prod uses against AWS S3. Qdrant starts but isn't used yet: the
Copilot is deterministic. Without `REGIS_S3_ENDPOINT_URL`, dev falls back to local files.

### Developer helpers

- Install `pre-commit` and enable hooks (runs `ruff`, `black`, `isort`, `mypy`):

```bash
cd backend
pip install -e ".[dev]"
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

- Reproduce the full dev environment, migrations and tests via `scripts/dev.sh`:

```bash
cd ..
./scripts/dev.sh
```

### Makefile

Common developer shortcuts are available via the `Makefile` at the repo root inside `regis`:

```bash
make install-dev        # install backend dev deps
make precommit-install  # install pre-commit and enable hooks
make up                 # docker compose up --build -d
make dev                # run scripts/dev.sh (migrations + tests)
make lint               # run lint checks
make format             # apply formatting fixes
make test               # run backend tests
make build-frontend     # build Next.js frontend
```

### Run the backend directly
```bash
cd backend
cp .env.example .env            # set REGIS_* (Postgres, JWT secret, optional Anthropic key)
alembic upgrade head
python -m app.seed.cli          # load 29 laws + 106 templates (idempotent, all DRAFT_UNVERIFIED)
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install && npm run dev      # http://localhost:3000  (proxies /api -> :8000)
```

### Verify the Postgres-only guarantees (RLS + append-only audit)
```bash
cd backend
# regis_app is the non-superuser that compose's postgres-init creates. Don't use
# `regis` (the compose superuser): superusers bypass RLS, even with FORCE.
REGIS_TEST_PG_URL=postgresql+psycopg://regis_app:regis_app_pw@localhost:5432/regis_test \
  python -m pytest tests/integration/test_postgres_hardening.py -q
```

## The two hard gates, in the data model (not just docs)

1. **`DRAFT_UNVERIFIED` content gate** — `obligation_templates.verification_status`
   is a column the engines read at runtime: until a template is `VERIFIED`,
   applicability confidence is capped at 0.70 and output is flagged
   `library_provisional`; the Copilot caps unverified answers at 0.70 + provisional.
   The seed loader always loads as shipped; nothing auto-promotes.
2. **Read-only / human-confirmed AI** — no endpoint or table lets an AI path write a
   terminal compliance state. Status changes go through Maker-Checker; document links
   require human confirmation; the Copilot has no write path and escalates action and
   legal-opinion requests. `audit_log` is append-only (DB trigger, migration `0002`).

## Architecture & design choices

- **Backend:** FastAPI with SQLAlchemy 2 and Alembic migrations; runtime on Python 3.11/3.12. The backend enforces tenant isolation at the DB layer using Postgres Row-Level Security (RLS).
- **Database hardening:** RLS for tenant isolation, `FORCE ROW LEVEL SECURITY` on production, and append-only `audit_log` enforced by a DB trigger (see `backend/alembic/versions/0002_rls_and_append_only_audit.py`). These are the key defensive guarantees: application code cannot bypass tenant boundaries even under bugs.
- **Authentication & session scope:** The app sets session GUCs `app.current_org` and `app.bootstrap` for tenant-aware queries; tests must run as a non-superuser role because Postgres superusers bypass RLS.
- **Testing strategy:** Three test tiers exist: unit, golden (regression-locked engine outputs), and integration (Postgres-backed). Integration tests that verify RLS/append-only behavior run against a real Postgres instance; CI creates a non-superuser role and a `regis_test` DB for them (locally, compose's `postgres-init` creates `regis_app`).
- **Formatting & quality:** Backend uses `ruff`, `black`, `isort` and `mypy`. The repo-root workflow (`.github/workflows/ci.yml`) enforces all four, runs pytest including the live-Postgres RLS tests, and builds the frontend (`next build`, which type-checks). It runs on pushes to `main` and on pull requests.


## Stack decisions (made during the build)

- **Python/FastAPI backend** — keeps the verified engines bit-for-bit; regression tests pass day one.
- **Arq on Redis** — async-native job runner (vs BullMQ; follows from the Python choice).
- **Qdrant** — chosen vector store (data-residency clean for ap-south-1); provisioned in compose, not yet wired to the Copilot.
- **FastAPI JWT auth** — self-contained; `users.auth_provider` leaves room for SSO, which is planned, not built.

## Out of scope (Phase 1, per PRD — deliberately not built)

Contract/litigation/audit/IFC/ERM modules · autonomous actions · AI legal drafting ·
government-portal integrations · native mobile · predictive ML scoring · public API ·
multi-jurisdiction. The V1 rule: if the AI would *act in the external world*, it's out.

## Content-team note

Engine correctness ≠ library legal correctness. The golden tests prove the engines
compute correctly; whether each obligation's rule / due date / required evidence is
*legally current* is a qualified CS/CA verification task against the `DRAFT_UNVERIFIED`
gate. That gate is wired through every engine for exactly this reason.
