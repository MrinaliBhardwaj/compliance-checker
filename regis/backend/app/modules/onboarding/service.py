"""
Onboarding service (Milestone M4) — persists the deterministic chain.

    raw onboarding input
        -> extract_profile (provenance)               -> company_profiles
        -> generate_compliance_universe (applicability) -> company_obligations
        -> generate_instances (dates)                  -> obligation_instances
        -> register event-driven listeners            -> event_listeners

Everything the engines decide is persisted as-is; the service adds DB rows, the
audit trail, and idempotency. It does NOT re-decide anything — the engines are
the source of truth. Re-running is safe (upsert on natural keys) and powers the
"regenerate with diff" flow (removed obligations deactivate, never delete).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.engines.applicability import generate_compliance_universe
from app.engines.instance_generator import EVENT_DRIVEN, generate_instances
from app.engines.profile_extraction import extract_profile
from app.models.calendar import EventListener
from app.models.compliance import CompanyObligation, ObligationInstance
from app.models.content import ObligationTemplate
from app.models.profile import CompanyProfile
from app.modules.onboarding.calendar_chain import build_company_obligations
from app.seed.library_loader import load_library

LIBRARY_VERSION = "0.1-draft"


@dataclass
class GenerationResult:
    company_obligations: int
    instances: int
    event_listeners: int
    parked: int
    generation_run_id: str
    diff: dict


def _library_dict(session: Session) -> dict:
    """Read the library from the DB into the engine's expected dict shape.
    Falls back to the bundled seed if the DB is empty (e.g. fresh test)."""
    templates = session.execute(select(ObligationTemplate)).scalars().all()
    if not templates:
        return load_library()
    return {
        "obligation_templates": [
            {
                "template_id": t.template_id, "law_id": t.law_id, "category": t.category,
                "title": t.title, "description": t.description, "frequency": t.frequency,
                "due_rule": t.due_rule, "applicability_rule": t.applicability_rule,
                "required_evidence": t.required_evidence,
                "default_owner_role": t.default_owner_role, "risk_level": t.risk_level,
                "form_reference": t.form_reference, "dependencies": t.dependencies,
                "verification_status": t.verification_status,
            }
            for t in templates
        ]
    }


def save_profile(session: Session, *, organization_id, entity_id, raw_input: dict,
                 library: dict | None = None, confirmed_by=None) -> CompanyProfile:
    """Extract + persist the structured profile with provenance (human-confirmed upstream)."""
    library = library or _library_dict(session)
    extracted = extract_profile(raw_input, library)

    existing = session.execute(
        select(CompanyProfile).where(CompanyProfile.entity_id == entity_id)
    ).scalar_one_or_none()
    if existing is None:
        existing = CompanyProfile(organization_id=organization_id, entity_id=entity_id)
        session.add(existing)
    existing.raw_input = raw_input
    existing.profile = extracted["profile"]
    existing.provenance = extracted["provenance"]
    existing.issues = extracted["issues"]
    existing.confirmed_by = confirmed_by
    session.flush()

    audit.record(session, action="profile_extracted", organization_id=organization_id,
                 actor_user_id=confirmed_by, entity_type="company_profile",
                 entity_id=str(entity_id),
                 meta={"review_fields": extracted["review_fields"],
                       "issues": len(extracted["issues"]),
                       "completeness": extracted["completeness"]})
    return existing


def generate_calendar(session: Session, *, organization_id, entity_id, profile: dict,
                      ctx: dict | None = None, library: dict | None = None,
                      actor_user_id=None) -> GenerationResult:
    """
    Run applicability + instance generation and persist the result idempotently.

    Idempotent on:
      - company_obligations: (entity_id, applicability_id) unique
      - obligation_instances: (company_obligation_id, period_label) unique
    Re-running upserts; obligations no longer applicable are deactivated
    (is_active=False), never deleted.
    """
    library = library or _library_dict(session)
    run_id = str(uuid.uuid4())

    universe = generate_compliance_universe(library, profile)
    cobs_input = build_company_obligations(universe, library)
    new_appl_ids = {c["applicability_id"] if "applicability_id" in c
                    else c["template_id"] for c in cobs_input}

    # --- previously stored applicable set (for diff + deactivation) ---
    existing_cobs = {
        c.applicability_id: c
        for c in session.execute(
            select(CompanyObligation).where(CompanyObligation.entity_id == entity_id)
        ).scalars().all()
    }
    prior_active_ids = {aid for aid, c in existing_cobs.items() if c.is_active}

    # --- upsert company_obligations ---
    appl_by_id = {r["template_id"]: r for r in universe["applicable"]}
    co_rows: dict[str, CompanyObligation] = {}
    for c in cobs_input:
        appl_id = c["template_id"]
        result = appl_by_id[appl_id]
        co = existing_cobs.get(appl_id)
        if co is None:
            co = CompanyObligation(
                organization_id=organization_id, entity_id=entity_id,
                template_id=appl_id.split("__")[0], applicability_id=appl_id,
                state=c.get("state"),
            )
            session.add(co)
        co.is_active = True
        co.applicability_confidence = result["confidence"]
        co.rationale = result["rationale"]
        co_rows[appl_id] = co
    session.flush()

    # deactivate obligations that dropped out of applicability
    removed = prior_active_ids - new_appl_ids
    for appl_id in removed:
        existing_cobs[appl_id].is_active = False

    # --- instance generation per the due rules ---
    ctx = ctx or {
        "window_start": date(2026, 4, 1), "window_end": date(2027, 3, 31),
        "anchors": {"agm_date": date(2026, 9, 25), "tds_return_date": date(2026, 7, 31)},
        "license_expiry": date(2026, 11, 30),
    }
    gen = generate_instances(cobs_input, ctx)

    # map generator's company_obligation_id (co_<appl_id>) back to the DB row
    inst_count = 0
    for inst in gen["instances"]:
        appl_id = inst.company_obligation_id.removeprefix("co_")
        co = co_rows.get(appl_id)
        if co is None:
            continue
        exists = session.execute(
            select(ObligationInstance).where(
                ObligationInstance.company_obligation_id == co.id,
                ObligationInstance.period_label == inst.period_label,
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(ObligationInstance(
                company_obligation_id=co.id, organization_id=organization_id,
                period_label=inst.period_label, due_date=date.fromisoformat(inst.due_date),
                status=inst.status, working_day_adjusted=inst.working_day_adjusted,
                generation_source=inst.generation_source, owner_user_id=co.owner_user_id,
            ))
            inst_count += 1
        # existing instances are left untouched (status may have advanced)

    # --- register event-driven listeners (not pre-generated) ---
    listener_count = 0
    {t["template_id"]: t for t in library["obligation_templates"]}
    for c in cobs_input:
        if c["due_rule"].get("type") in EVENT_DRIVEN:
            co = co_rows[c["template_id"]]
            exists = session.execute(
                select(EventListener).where(EventListener.company_obligation_id == co.id)
            ).scalar_one_or_none()
            if exists is None:
                session.add(EventListener(
                    company_obligation_id=co.id, organization_id=organization_id,
                    due_rule_type=c["due_rule"]["type"],
                ))
                listener_count += 1

    diff = {
        "added": sorted(new_appl_ids - prior_active_ids),
        "removed": sorted(removed),
        "unchanged": sorted(new_appl_ids & prior_active_ids),
    }
    audit.record(session, action="calendar_generated", organization_id=organization_id,
                 actor_user_id=actor_user_id, entity_type="entity", entity_id=str(entity_id),
                 meta={"generation_run_id": run_id, "library_version": LIBRARY_VERSION,
                       "summary": universe["summary"],
                       "added": len(diff["added"]), "removed": len(diff["removed"])})
    session.flush()

    return GenerationResult(
        company_obligations=len(co_rows), instances=inst_count,
        event_listeners=listener_count, parked=len(gen["parked"]),
        generation_run_id=run_id, diff=diff,
    )
