"""
Regis backend — FastAPI modular monolith entrypoint.

Wires the bounded-context module routers over the shared deterministic engines.
All AI is read-only/assistive; the deterministic cores are the source of truth.
"""
from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import bind, configure_logging, get_logger, new_request_id
from app.core.ratelimit import client_ip, enforce
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

configure_logging()
log = get_logger(__name__)

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


@app.middleware("http")
async def request_context(request: Request, call_next):
    """One structured line per request, with a request id echoed to the caller.

    Nothing here may raise: an observability layer that can 500 a healthy
    request is worse than no observability. An unhandled error is logged with
    its request id and returned as a generic 500 — the detail goes to the log,
    not to the client.
    """
    request_id = request.headers.get("x-request-id") or new_request_id()
    started = time.perf_counter()

    with bind(request_id=request_id, method=request.method, path=request.url.path):
        try:
            response = await call_next(request)
        except Exception:
            ms = round((time.perf_counter() - started) * 1000, 1)
            log.exception("request failed", extra={"duration_ms": ms, "status": 500})
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "request_id": request_id},
                headers={"x-request-id": request_id},
            )

        ms = round((time.perf_counter() - started) * 1000, 1)
        # Health checks fire constantly and would drown the log.
        if request.url.path != "/health":
            log.log(40 if response.status_code >= 500 else 20, "request",
                    extra={"status": response.status_code, "duration_ms": ms})
        response.headers["x-request-id"] = request_id
        return response


# Paths that must never be throttled: health is polled by the load balancer and
# the container healthcheck, and throttling it would take a healthy task out of
# service under exactly the load the limit exists to survive.
_NO_LIMIT = frozenset({"/health", "/docs", "/redoc", "/openapi.json"})


@app.middleware("http")
async def global_rate_limit(request: Request, call_next):
    """Blunt per-IP ceiling across the whole API.

    Deliberately keyed on IP, not org: this runs before auth resolves, and its
    job is to bound an unauthenticated flood. Per-organisation limits on the
    genuinely expensive routes are enforced as route dependencies, where the
    principal already exists.
    """
    if request.url.path not in _NO_LIMIT:
        s = get_settings()
        try:
            enforce("api_ip", client_ip(request),
                    limit=s.api_max_requests, window=s.api_window_seconds)
        except HTTPException as exc:
            log.warning("rate limited", extra={"scope": "api_ip", "status": 429})
            return JSONResponse(status_code=exc.status_code,
                                content={"detail": exc.detail},
                                headers=exc.headers)
    return await call_next(request)


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
app.include_router(audit_router)
