# Regis — Final Year Project Presentation

## Slide 1 — Title
- **Regis — AI-Native Compliance Platform (Phase 1)**
- Author: Your Name
- Date: 2026-09-08

## Slide 2 — Problem
- Compliance for NBFCs is complex: many laws, dates, owners, evidence.
- Manual spreadsheets are error-prone, time-consuming, and non-reproducible.

## Slide 3 — Goal
- Deliver a reproducible engine that maps profile → obligations → calendar.
- Provide deterministic engines, a read-only Copilot, and an auditable DB.

## Slide 4 — Architecture (high-level)
- FastAPI backend (Python 3.11/3.12)
- Postgres with RLS + append-only `audit_log`
- Next.js frontend
- Arq worker + Redis (overdue count, reminders/escalations, FY roll-over)
- Copilot: deterministic and structured-first over the org's own data; RAG over
  regulatory text (Qdrant) is a stubbed seam, planned next
- Evidence in S3-compatible storage: MinIO locally, AWS S3 (KMS-encrypted) in prod

## Slide 5 — Key design choices
- DB-enforced tenant isolation (RLS) — security at the data layer.
- Append-only audit enforced by DB trigger — tamper-evident trail.
- Human-in-the-loop AI: Copilot is read-only and escalates actions.
- Verification via golden tests for deterministic engines.

## Slide 6 — Demo steps
1. Start the stack (from `regis/`): `docker compose up --build -d`. The API migrates
   and seeds on boot (29 laws, 106 obligation templates), and `postgres-init` creates
   the non-superuser `regis_app` role and `regis_test` DB.
2. Start the UI: `cd frontend && npm install && npm run dev`
3. Open `http://localhost:3000`, sign up, and run onboarding. The calendar is tracked
   from today, with nothing overdue on day one, and filings that need a date you
   haven't given (AGM, licence expiry) wait as "awaiting a date".
4. API docs: `http://localhost:8000/docs`

## Slide 7 — Tests & CI
- Local: `pytest` runs unit, golden, and integration tests (160 pass, plus 5 that
  need Postgres; all 165 pass with it). Coverage 85%.
- CI (GitHub Actions, on PRs and pushes to `main`): ruff, black, isort, mypy, then
  pytest including the live-Postgres RLS tests (run as a non-superuser), and the
  frontend build.

## Slide 8 — Evaluation criteria
- Correctness: golden tests reproduce verified outputs.
- Security: tenant isolation + audit trail.
- Reproducibility: docker-compose + CI ensure deterministic runs.

## Slide 9 — Next steps
- Add demo screencast + guided checklist.
- Harden production deployment, observability, and secrets.
- Expand templates, laws, and evidence mapping.

## Slide 10 — Contact
- Repo: (provide your GitHub link)
- Questions welcome
