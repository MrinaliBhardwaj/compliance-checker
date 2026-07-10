"""
Legal updates API. Publishing is a content-team operation (admin-gated here; the
feed is global). Listing computes a deterministic match verdict per org; review is
admin/head only (PRD §10) — preparers do not review legal updates.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.deps import DbSession
from app.core.security import CurrentPrincipal, Principal, require_role
from app.modules.legal_updates import service as svc

router = APIRouter(prefix="/legal-updates", tags=["legal-updates"])

_reviewer = require_role("compliance_admin", "head")
_publisher = require_role("compliance_admin")  # content-team role; admin in V1


class PublishBody(BaseModel):
    title: str
    affects_filter: dict = {}
    law_id: str | None = None
    source_url: str | None = None
    published_date: date | None = None
    ai_summary: str | None = None
    ai_impact_note: str | None = None
    raw_text: str | None = None   # if provided + model configured, summarized via seam


@router.post("")
def publish(body: PublishBody, db: DbSession,
            principal: Principal = Depends(_publisher)) -> dict:
    u = svc.publish_update(
        db, title=body.title, affects_filter=body.affects_filter, law_id=body.law_id,
        source_url=body.source_url, published_date=body.published_date,
        ai_summary=body.ai_summary, ai_impact_note=body.ai_impact_note,
        raw_text=body.raw_text, actor_user_id=principal.user_id,
        organization_id=principal.organization_id)
    return {"id": str(u.id), "title": u.title}


@router.get("")
def list_updates(db: DbSession, principal: CurrentPrincipal) -> list[dict]:
    return svc.list_for_org(db, organization_id=principal.organization_id)


class ReviewBody(BaseModel):
    status: str  # applicable | not_applicable | reviewed
    reason: str | None = None


@router.post("/{update_id}/review")
def review(update_id: str, body: ReviewBody, db: DbSession,
           principal: Principal = Depends(_reviewer)) -> dict:
    try:
        row = svc.review_update(db, organization_id=principal.organization_id,
                                legal_update_id=update_id, status=body.status,
                                reviewed_by=principal.user_id, reason=body.reason)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return {"legal_update_id": str(row.legal_update_id), "status": row.status,
            "reviewed_at": row.reviewed_at.isoformat()}
