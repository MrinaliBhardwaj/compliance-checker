"""
Reports API: compliance status report as JSON / HTML / PDF.

RBAC (PRD §10): only compliance_admin and head may export reports — preparers
cannot. Data is org-scoped (RLS) and entity-filterable for the multi-entity rollup.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Response
from fastapi.responses import HTMLResponse

from app.core.deps import DbSession
from app.core.security import Principal, require_role
from app.modules.reports.render import render_html, render_pdf
from app.modules.reports.service import build_compliance_report

router = APIRouter(prefix="/reports", tags=["reports"])

_viewer = require_role("compliance_admin", "head")


def _report(db, principal: Principal, entity_id: str | None) -> dict:
    return build_compliance_report(db, organization_id=principal.organization_id,
                                   today=date.today(), entity_id=entity_id)


@router.get("/compliance")
def compliance_json(db: DbSession, entity_id: str | None = None,
                    principal: Principal = Depends(_viewer)) -> dict:
    return _report(db, principal, entity_id)


@router.get("/compliance.html", response_class=HTMLResponse)
def compliance_html(db: DbSession, entity_id: str | None = None,
                    principal: Principal = Depends(_viewer)) -> HTMLResponse:
    return HTMLResponse(render_html(_report(db, principal, entity_id)))


@router.get("/compliance.pdf")
def compliance_pdf(db: DbSession, entity_id: str | None = None,
                   principal: Principal = Depends(_viewer)) -> Response:
    pdf = render_pdf(_report(db, principal, entity_id))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="compliance-status.pdf"'})
