"""
Regis backend — FastAPI modular monolith entrypoint.

Wires the bounded-context module routers over the shared deterministic engines.
All AI is read-only/assistive; the deterministic cores are the source of truth.
"""
from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import engine
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.copilot.router import router as copilot_router
from app.modules.documents.router import router as documents_router
from app.modules.legal_updates.router import router as legal_updates_router
from app.modules.notify.router import router as notify_router
from app.modules.obligations.router import router as obligations_router
from app.modules.onboarding.router import router as onboarding_router
from app.modules.reports.router import router as reports_router
from app.modules.team.router import router as team_router

settings = get_settings()
settings.assert_production_ready()

# Interactive API docs are useful in dev but needlessly expose the surface map in
# prod — serve them everywhere except prod.
_docs_on = settings.env != "prod"

app = FastAPI(
    title="Regis — NBFC Compliance Platform (Phase 1)",
    version="0.1.0",
    description="AI-assisted, human-confirmed compliance calendar for Indian NBFCs. "
                "Deterministic cores; read-only AI; ap-south-1 data residency.",
    docs_url="/docs" if _docs_on else None,
    redoc_url="/redoc" if _docs_on else None,
    openapi_url="/openapi.json" if _docs_on else None,
)

# CORS is off by default (the SPA reaches the API through a same-origin Next.js
# proxy). Set REGIS_CORS_ALLOW_ORIGINS only if the browser calls the API directly;
# credentials are allowed but the origin list is explicit — never "*".
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "env": settings.env, "region": settings.aws_region}


# Start time for simple uptime metric
_START_TIME = time.time()


@app.get("/ready", tags=["system"])
def ready() -> dict:
    """Light readiness probe: ensures the database is reachable."""
    db_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "error", "db": db_ok}


@app.get("/metrics", tags=["system"])
def metrics() -> PlainTextResponse:
    """Minimal Prometheus-format metrics for local dev."""
    uptime = int(time.time() - _START_TIME)
    db_up = 0
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_up = 1
    except Exception:
        db_up = 0

    lines = [
        "# HELP regis_uptime_seconds Uptime of the application in seconds",
        "# TYPE regis_uptime_seconds gauge",
        f"regis_uptime_seconds {uptime}",
        "# HELP regis_db_up Whether the database is reachable (1 = up, 0 = down)",
        "# TYPE regis_db_up gauge",
        f"regis_db_up {db_up}",
    ]
    return PlainTextResponse("\n".join(lines), media_type="text/plain; charset=utf-8")


app.include_router(auth_router)
app.include_router(team_router)
app.include_router(onboarding_router)
app.include_router(obligations_router)
app.include_router(documents_router)
app.include_router(notify_router)
app.include_router(reports_router)
app.include_router(legal_updates_router)
app.include_router(copilot_router)
app.include_router(audit_router)
