"""Onboarding API: profile preview (no commit) + calendar generation (human-confirmed)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.deps import DbSession
from app.core.security import Principal, require_role
from app.engines.profile_extraction import extract_profile
from app.modules.onboarding.service import generate_calendar, save_profile
from app.seed.library_loader import load_library

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

_admin = require_role("compliance_admin")


class ProfilePreview(BaseModel):
    raw_input: dict


@router.post("/profile/preview")
def profile_preview(body: ProfilePreview, principal: Principal = Depends(_admin)) -> dict:
    """
    Run extraction WITHOUT committing — feeds the review screen (PRD Step 4):
    derived/extracted fields flagged, contradictions surfaced, gap questions ranked.
    The human confirms before anything persists.
    """
    return extract_profile(body.raw_input, load_library())


class GenerateRequest(BaseModel):
    entity_id: str
    raw_input: dict
    window_start: date | None = None
    window_end: date | None = None
    # The company's real dates, when known. Obligations that depend on a missing
    # one are parked (reported as `parked`) instead of dated from a guess.
    agm_date: date | None = None
    tds_return_date: date | None = None
    license_expiry: date | None = None


@router.post("/calendar/generate")
def calendar_generate(
    body: GenerateRequest, db: DbSession, principal: Principal = Depends(_admin)
) -> dict:
    """Commit the confirmed profile, then generate + persist the calendar."""
    from fastapi import HTTPException, status
    from sqlalchemy import select

    from app.models.tenancy import Entity

    entity = db.execute(
        select(Entity).where(
            Entity.id == body.entity_id, Entity.organization_id == principal.organization_id
        )
    ).scalar_one_or_none()
    if not entity:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found in organization")

    prof = save_profile(
        db,
        organization_id=principal.organization_id,
        entity_id=body.entity_id,
        raw_input=body.raw_input,
        confirmed_by=principal.user_id,
    )
    anchors = {
        k: v
        for k, v in (("agm_date", body.agm_date), ("tds_return_date", body.tds_return_date))
        if v
    }
    ctx = None
    if body.window_start and body.window_end:
        ctx = {
            "window_start": body.window_start,
            "window_end": body.window_end,
            "anchors": anchors,
            "license_expiry": body.license_expiry,
        }
    res = generate_calendar(
        db,
        organization_id=principal.organization_id,
        entity_id=body.entity_id,
        profile=prof.profile,
        ctx=ctx,
        actor_user_id=principal.user_id,
        anchors=anchors,
        license_expiry=body.license_expiry,
    )
    return {
        "company_obligations": res.company_obligations,
        "instances": res.instances,
        "parked": res.parked,
        "not_tracked": res.not_tracked,
        "event_listeners": res.event_listeners,
        "diff": res.diff,
        "generation_run_id": res.generation_run_id,
    }
