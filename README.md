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
| Calendar generation | one profile → **367+** dated obligation instances, working-day adjusted, in **< 2s** end-to-end over HTTP |
| Document intelligence | **98.4%** evidence-to-obligation classification on the reference corpus (192/195) |
| API surface | **34** REST endpoints across 9 modules |
| Database | **27** PostgreSQL tables, row-level security (tenant isolation), append-only audit log, Alembic migrations |
| Tests | **137** tests at **84%** coverage — 133 run everywhere; 4 RLS/append-only hardening tests run against live Postgres in CI |

## Modules

| Module | What it does |
|---|---|
| Auth & Team | JWT + RBAC (admin / head / preparer), invites, role management |
| Onboarding | AI-extracted profile preview with provenance + gap questions → human-confirmed calendar generation |
| Obligations | tracker, dashboard, **maker-checker lifecycle** (assign → start → submit → approve/reject → reopen) |
| Evidence | upload → AI classify/extract → human-confirmed link → completeness gate; exact-duplicate detection |
| Audit trail | every state change, append-only and immutable — filterable evidence trail for auditors and RBI inspection |
| Notifications | risk-weighted reminders, overdue escalation ladder (Arq background worker) |
| Reports | board-ready compliance status as JSON / HTML / PDF |
| Legal updates | curated feed with deterministic applicability matching |
| Copilot | read-only, structured-first, grounded-or-silent Q&A with citations; escalates action requests |

## Stack

FastAPI · SQLAlchemy 2 · PostgreSQL (RLS) / SQLite (tests) · Alembic · Arq + Redis ·
Next.js 14 · TypeScript · React Query · Tailwind — AI seams target Anthropic Claude,
deterministic-only offline mode by default.

## Run it

```bash
# backend (SQLite quickstart — no infra needed)
cd regis/backend
pip install -e ".[dev]"
pytest                                   # 133 passed, 4 skipped

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

Sign up, run onboarding, and the dashboard fills with your generated calendar.
For production-shaped dev (Postgres + RLS), point `REGIS_DATABASE_URL` at Postgres
and run `alembic upgrade head`.

## Deeper docs

- [`regis/README.md`](regis/README.md) — engine reference results and module detail
- [`BUILD_PLAN.md`](BUILD_PLAN.md) — architecture rationale and phase plan
- [`Compliance docs/`](Compliance%20docs) — engine specs and the obligation library source
