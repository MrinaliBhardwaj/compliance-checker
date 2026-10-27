# Regis — AI-Assisted Compliance Platform for Indian NBFCs

[![CI](https://github.com/MrinaliBhardwaj/compliance-checker/actions/workflows/ci.yml/badge.svg)](https://github.com/MrinaliBhardwaj/compliance-checker/actions/workflows/ci.yml)

An NBFC compliance officer answers a short profile questionnaire and gets a complete,
accurate compliance calendar — obligations, due dates, owners, evidence repository,
an append-only audit trail, and a read-only AI copilot — replacing weeks of
spreadsheet setup.

**Design contract:** all AI is read-only/assistive and human-confirmed. Deterministic
rule engines are the source of truth; every obligation ships `DRAFT_UNVERIFIED` until
a content-team flag flips it.

## What's inside (verified by the test suite)

| | |
|---|---|
| Rule engines | **5** deterministic engines — applicability, instance generation, profile extraction, document intelligence, copilot — locked behind golden regression tests |
| Obligation library | **106** obligation templates spanning **29** Indian laws (RBI, Companies Act, GST, FEMA, labour, tax) |
| Calendar generation | the reference profile over a full FY → **367** dated obligation instances (golden-locked), working-day adjusted; generation runs in well under a second. A new company's calendar starts on its onboarding day |
| Document intelligence | **98.4%** evidence-to-obligation classification on the reference corpus (192/195) |
| API surface | **41** REST endpoints across 10 modules, plus `/health`, `/ready`, `/metrics` |
| Database | **19** PostgreSQL tables, row-level security (tenant isolation), append-only audit log, Alembic migrations |
| Tests | **165** tests at **85%** coverage — 160 run everywhere; 5 RLS/append-only hardening tests need live Postgres (CI runs them) |

## Modules

| Module | What it does |
|---|---|
| Auth & Team | JWT + RBAC (admin / head / preparer), invites, role management |
| Onboarding | AI-extracted profile preview with provenance + gap questions → human-confirmed calendar generation |
| Obligations | tracker, dashboard, **maker-checker lifecycle** (assign → start → submit → approve/reject → reopen) |
| Evidence | upload → AI classify/extract → human-confirmed link → completeness gate; exact-duplicate detection |
| Audit trail | every state change, append-only and immutable — filterable evidence trail for auditors and RBI inspection |
| Notifications | risk-weighted reminders, overdue escalation ladder, monthly calendar roll-over (Arq background worker) |
| Reports | board-ready compliance status as JSON / HTML / PDF |
| Legal updates | curated feed with deterministic applicability matching |
| Copilot | read-only, deterministic and structured-first: grounded-or-silent Q&A over your own obligations, with citations; escalates action requests. A RAG seam over regulatory text is stubbed, not wired |

## Stack

FastAPI · SQLAlchemy 2 · PostgreSQL (RLS) / SQLite (tests) · Alembic · Arq + Redis ·
Next.js 14 · TypeScript · React Query · Tailwind — AI seams target Anthropic Claude,
deterministic-only offline mode by default.

## Run it

```bash
# backend (SQLite quickstart — no infra needed)
cd regis/backend
pip install -e ".[dev]"
pytest                                   # 160 passed, 5 skipped (Postgres-only)

REGIS_DATABASE_URL="sqlite+pysqlite:///dev.db" REGIS_JWT_SECRET=dev python -c \
  "from app.core.db import engine, SessionLocal; from app.models import Base; \
   from app.seed.library_loader import seed_database; \
   Base.metadata.create_all(engine); s=SessionLocal(); seed_database(s); s.commit()"
REGIS_DATABASE_URL="sqlite+pysqlite:///dev.db" REGIS_JWT_SECRET=dev \
  uvicorn app.main:app --port 8000

# frontend
cd regis/frontend
npm install && npm run dev               # http://localhost:3000 (proxies /api -> :8000)
```

Sign up, run onboarding, and the dashboard fills with your calendar, tracked from
today. Filings that depend on a date you haven't given (AGM, TDS return, licence
expiry) wait as "awaiting a date" rather than being guessed.
For production-shaped dev (Postgres + RLS), use `docker compose up --build` in
`regis/` (see [`regis/README.md`](regis/README.md)).

## Deeper docs

- [`regis/README.md`](regis/README.md) — engine reference results and module detail
- [`BUILD_PLAN.md`](BUILD_PLAN.md) — architecture rationale and phase plan
- [`Compliance docs/`](Compliance%20docs) — engine specs and the obligation library source
