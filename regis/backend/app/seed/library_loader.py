"""
Seed loader for `nbfc_obligation_library_seed.json` (Milestone M2).

Two layers, deliberately separated:

  1. `load_library()` / `validate_library()` — pure parse + structural validation,
     testable with no database. Returns the library dict the engines consume.
  2. `seed_database(session)` — idempotent DB write path (upsert on natural keys)
     into `law_library` + `obligation_templates`. Imported lazily so the pure
     layer has no SQLAlchemy dependency.

Hard invariant honoured here: every obligation_template is loaded with
`verification_status = DRAFT_UNVERIFIED` exactly as the seed ships it. Flipping a
template to VERIFIED is a content-team action elsewhere, never done by this loader.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

SEED_PATH = Path(__file__).with_name("nbfc_obligation_library_seed.json")

# Structural contract we assert on load (not legal correctness — that's content team).
REQUIRED_TEMPLATE_KEYS = {
    "template_id", "law_id", "category", "title", "description", "frequency",
    "due_rule", "applicability_rule", "required_evidence", "default_owner_role",
    "risk_level", "verification_status",
}
REQUIRED_LAW_KEYS = {"id", "name", "regulator", "category"}
VALID_VERIFICATION = {"DRAFT_UNVERIFIED", "VERIFIED"}


class SeedValidationError(ValueError):
    """Raised when the seed file violates its structural contract."""


def load_library(path: Path | str = SEED_PATH) -> dict[str, Any]:
    """Read and structurally validate the seed library. Pure; no DB."""
    with open(path, encoding="utf-8") as fh:
        library = json.load(fh)
    validate_library(library)
    return library


def validate_library(library: dict[str, Any]) -> None:
    """Assert the structural contract the engines rely on. Raises on violation."""
    if "obligation_templates" not in library or "law_library" not in library:
        raise SeedValidationError("seed missing 'obligation_templates' or 'law_library'")

    laws = library["law_library"]
    templates = library["obligation_templates"]
    law_ids = {law["id"] for law in laws}

    seen_law_ids: set[str] = set()
    for law in laws:
        missing = REQUIRED_LAW_KEYS - law.keys()
        if missing:
            raise SeedValidationError(f"law {law.get('id')!r} missing keys: {sorted(missing)}")
        if law["id"] in seen_law_ids:
            raise SeedValidationError(f"duplicate law id: {law['id']!r}")
        seen_law_ids.add(law["id"])

    seen_tpl_ids: set[str] = set()
    for tpl in templates:
        missing = REQUIRED_TEMPLATE_KEYS - tpl.keys()
        if missing:
            raise SeedValidationError(
                f"template {tpl.get('template_id')!r} missing keys: {sorted(missing)}")
        tid = tpl["template_id"]
        if tid in seen_tpl_ids:
            raise SeedValidationError(f"duplicate template id: {tid!r}")
        seen_tpl_ids.add(tid)
        if tpl["law_id"] not in law_ids:
            raise SeedValidationError(
                f"template {tid!r} references unknown law_id {tpl['law_id']!r}")
        if tpl["verification_status"] not in VALID_VERIFICATION:
            raise SeedValidationError(
                f"template {tid!r} has invalid verification_status {tpl['verification_status']!r}")
        if "type" not in (tpl["due_rule"] or {}):
            raise SeedValidationError(f"template {tid!r} due_rule has no 'type'")


def library_stats(library: dict[str, Any]) -> dict[str, Any]:
    """Quick counts for logging / the M2 acceptance test."""
    templates = library["obligation_templates"]
    return {
        "laws": len(library["law_library"]),
        "templates": len(templates),
        "by_verification": dict(Counter(t["verification_status"] for t in templates)),
        "by_category": dict(Counter(t["category"] for t in templates)),
        "by_frequency": dict(Counter(t["frequency"] for t in templates)),
        "due_rule_types": len({t["due_rule"]["type"] for t in templates}),
    }


def seed_database(session, path: Path | str = SEED_PATH) -> dict[str, int]:
    """
    Idempotent upsert of the library into Postgres (law_library + obligation_templates).

    Re-runnable: upserts on natural keys (law.id / template.template_id) so a second
    run is a no-op. Returns counts written. Imported lazily to keep the pure loader
    free of ORM dependencies.
    """
    from sqlalchemy import select

    from app.models.content import LawLibrary, ObligationTemplate

    library = load_library(path)

    law_count = 0
    for law in library["law_library"]:
        existing = session.get(LawLibrary, law["id"])
        if existing is None:
            session.add(LawLibrary(
                id=law["id"], name=law["name"], regulator=law["regulator"],
                category=law["category"], reference_url=law.get("reference_url"),
            ))
        else:
            existing.name = law["name"]
            existing.regulator = law["regulator"]
            existing.category = law["category"]
            existing.reference_url = law.get("reference_url")
        law_count += 1

    tpl_count = 0
    for tpl in library["obligation_templates"]:
        existing = session.get(ObligationTemplate, tpl["template_id"])
        payload = dict(
            law_id=tpl["law_id"], category=tpl["category"], title=tpl["title"],
            description=tpl["description"], frequency=tpl["frequency"],
            due_rule=tpl["due_rule"], applicability_rule=tpl["applicability_rule"],
            required_evidence=tpl["required_evidence"],
            default_owner_role=tpl["default_owner_role"], risk_level=tpl["risk_level"],
            penalty_note=tpl.get("penalty_note"), form_reference=tpl.get("form_reference"),
            dependencies=tpl.get("dependencies", []),
            # Invariant: seed always loads as shipped — DRAFT_UNVERIFIED. Never auto-promote.
            verification_status=tpl["verification_status"],
        )
        if existing is None:
            session.add(ObligationTemplate(template_id=tpl["template_id"], **payload))
        else:
            for k, v in payload.items():
                setattr(existing, k, v)
        tpl_count += 1

    session.flush()
    return {"laws": law_count, "templates": tpl_count}
