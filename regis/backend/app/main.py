"""
Regis backend — FastAPI modular monolith entrypoint.

Wires the bounded-context module routers over the shared deterministic engines.
All AI is read-only/assistive; the deterministic cores are the source of truth.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.core.config import get_settings
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

app = FastAPI(
    title="Regis — NBFC Compliance Platform (Phase 1)",
    version="0.1.0",
    description="AI-assisted, human-confirmed compliance calendar for Indian NBFCs. "
                "Deterministic cores; read-only AI; ap-south-1 data residency.",
)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "env": settings.env, "region": settings.aws_region}


app.include_router(auth_router)
app.include_router(team_router)
app.include_router(onboarding_router)
app.include_router(obligations_router)
app.include_router(documents_router)
app.include_router(notify_router)
app.include_router(reports_router)
app.include_router(legal_updates_router)
app.include_router(copilot_router)
