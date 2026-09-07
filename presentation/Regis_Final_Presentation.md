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
- Arq worker + Redis
- Qdrant for vector search (Copilot RAG)
- MinIO for local S3-compatible storage

## Slide 5 — Key design choices
- DB-enforced tenant isolation (RLS) — security at the data layer.
- Append-only audit enforced by DB trigger — tamper-evident trail.
- Human-in-the-loop AI: Copilot is read-only and escalates actions.
- Verification via golden tests for deterministic engines.

## Slide 6 — Demo steps
1. Start local stack: `docker compose up -d postgres redis minio qdrant`
2. Create test DB + role (or use compose `db_init`):
   - `psql -U regis -c "CREATE ROLE regis_app WITH LOGIN PASSWORD 'regis_app_pw'"`
   - `psql -U regis -c "CREATE DATABASE regis_test OWNER regis_app"`
3. Apply migrations & seed: `cd backend && alembic upgrade head && python -m app.seed.cli`
4. Start API: `uvicorn app.main:app --reload`
5. Open `http://localhost:3000` (frontend) or `http://localhost:8000/docs` (API)

## Slide 7 — Tests & CI
- Local: `pytest` runs unit, golden, and integration tests.
- CI: GitHub Actions runs ruff/black/isort/mypy, alembic migrations, and pytest against Postgres.

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
