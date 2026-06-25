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


@router.post("/calendar/generate")
def calendar_generate(body: GenerateRequest, db: DbSession,
                      principal: Principal = Depends(_admin)) -> dict:
    """Commit the confirmed profile, then generate + persist the calendar."""
    prof = save_profile(db, organization_id=principal.organization_id,
                        entity_id=body.entity_id, raw_input=body.raw_input,
                        confirmed_by=principal.user_id)
    ctx = None
    if body.window_start and body.window_end:
        ctx = {"window_start": body.window_start, "window_end": body.window_end,
               "anchors": {}, "license_expiry": None}
    res = generate_calendar(db, organization_id=principal.organization_id,
                            entity_id=body.entity_id, profile=prof.profile, ctx=ctx,
                            actor_user_id=principal.user_id)
    return {
        "company_obligations": res.company_obligations,
        "instances": res.instances,
        "event_listeners": res.event_listeners,
        "diff": res.diff,
        "generation_run_id": res.generation_run_id,
    }
