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
