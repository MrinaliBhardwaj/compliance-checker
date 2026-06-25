# Regis — AI-Native Compliance Platform for Indian NBFCs (Phase 1)

A focused, AI-**assisted** compliance platform: an NBFC compliance officer answers a
short profile questionnaire and gets a complete, accurate compliance calendar —
obligations, due dates, owners, evidence repository, and a read-only Copilot —
replacing weeks of spreadsheet setup.

> **Design contract (honored throughout):** all AI is read-only/assistive and
> human-confirmed; the deterministic engines are the source of truth; every
> obligation ships `DRAFT_UNVERIFIED` until a content-team flag flips it; designed
> for AWS **ap-south-1**. See [`BUILD_PLAN.md`](../BUILD_PLAN.md) for the rationale.

## What's built (and proven)

The four verified reference engines are ported **verbatim** into `backend/app/engines/`
and locked behind regression tests reproducing every quoted figure:

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
| Auth | self-serve signup/login, JWT, RBAC, provider-agnostic (SSO-ready) |
| Onboarding | profile preview (provenance + gaps) → human-confirmed calendar generation |
| Obligations | tracker, dashboard, **Maker-Checker lifecycle** (assign/start/submit/approve/reject/mark-NA/reopen) |
| Evidence | upload → AI classify/extract (optional seam) → human-confirmed link → completeness gate |
| Notifications | risk-weighted reminders, overdue escalation ladder, assignment + review routing (email/Slack seam) |
| Reports | board-ready compliance status as JSON/HTML/**PDF** (pluggable engine + dependency-free fallback) |
| Legal updates | curated feed, optional AI summary, **deterministic applicability match reusing the obligation engine** |
| Copilot | read-only, structured-first, grounded-or-silent Q&A; escalates action/legal-opinion requests |

Background: an Arq worker runs the nightly overdue sweep + idempotent reminder
dispatch. Frontend: Next.js scaffold (login · onboarding · dashboard + Copilot ·
legal updates · PDF export).

```
Test status: 113 passed, 2 skipped (Postgres-only RLS/append-only tests).
```

## Repository layout

```
regis/
├─ backend/                 FastAPI modular monolith (Python 3.12)
│  ├─ app/engines/          ← ported verbatim from the verified references (pure, deterministic)
│  ├─ app/ai/               LLM / OCR / RAG seams (graceful offline fallback)
│  ├─ app/models/           SQLAlchemy models (1:1 with migrations)
│  ├─ app/modules/          auth · onboarding · obligations · documents · notify · reports · legal_updates · copilot
│  ├─ app/jobs/             Arq worker (nightly sweep, overdue, reminders)
│  ├─ app/seed/             obligation-library loader + CLI
│  ├─ alembic/              migrations (baseline + RLS/append-only hardening)
│  └─ tests/                golden (the contract) · unit · integration · api
├─ frontend/                Next.js 14 App Router (login · onboarding · dashboard + Copilot)
├─ infra/terraform/         AWS ap-south-1 topology (README; modules to author)
├─ shared/openapi.json      generated API contract
└─ docker-compose.yml       postgres · redis · minio(S3) · qdrant · api · worker
```

## Quick start

### Run the tests (no services needed)
```bash
cd backend
pip install -e ".[dev]"
python -m pytest -q            # 69 passed, 2 skipped
```

### Run the full stack (Docker)
```bash
docker compose up --build       # api on :8000 (migrates + seeds on boot), worker, db, redis, minio, qdrant
# API docs: http://localhost:8000/docs
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
REGIS_TEST_PG_URL=postgresql+psycopg://regis:regis@localhost:5432/regis_test \
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

## Stack decisions (made during the build)

- **Python/FastAPI backend** — keeps the verified engines bit-for-bit; regression tests pass day one.
- **Arq on Redis** — async-native job runner (vs BullMQ; follows from the Python choice).
- **Qdrant** — vector store, data-residency clean for ap-south-1.
- **FastAPI JWT auth, provider-agnostic** — self-contained for dev; SSO-ready.

## Out of scope (Phase 1, per PRD — deliberately not built)

Contract/litigation/audit/IFC/ERM modules · autonomous actions · AI legal drafting ·
government-portal integrations · native mobile · predictive ML scoring · public API ·
multi-jurisdiction. The V1 rule: if the AI would *act in the external world*, it's out.

## Content-team note

Engine correctness ≠ library legal correctness. The golden tests prove the engines
compute correctly; whether each obligation's rule / due date / required evidence is
*legally current* is a qualified CS/CA verification task against the `DRAFT_UNVERIFIED`
gate. That gate is wired through every engine for exactly this reason.
