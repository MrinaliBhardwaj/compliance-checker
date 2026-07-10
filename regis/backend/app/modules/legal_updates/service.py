"""
Legal updates service.

- publish: create a master LegalUpdate (global feed). AI summarization is optional
  (content team reviews before publish — publishing is the human gate).
- list_for_org: every update with a deterministically computed match verdict for the
  caller's org (across its entity profiles) + the org's review status.
- review: upsert the per-org LegalUpdateStatus (applicable / not_applicable / reviewed),
  audited. Marking applicable is the trigger for a manual follow-up task (V1).

Matching never silently drops an update: no clean match -> "may affect, review".
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import audit
from app.models.compliance import CompanyObligation
from app.models.content import ObligationTemplate
from app.models.legal_updates import LegalUpdate, LegalUpdateStatus
from app.models.profile import CompanyProfile
from app.modules.legal_updates.matcher import match_org

REVIEW_STATUSES = {"new", "reviewed", "applicable", "not_applicable"}


def publish_update(session: Session, *, title: str, affects_filter: dict | None,
                   law_id: str | None = None, source_url: str | None = None,
                   published_date: date | None = None, ai_summary: str | None = None,
                   ai_impact_note: str | None = None, raw_text: str | None = None,
                   actor_user_id=None, organization_id=None) -> LegalUpdate:
    """Create a master legal update. If raw_text is given and a model is configured,
    summarize via the seam; otherwise the provided summary/impact is used as-is."""
    if raw_text and not ai_summary:
        from app.ai import legal
        if legal.available():
            try:
                out = legal.summarize(raw_text)
                ai_summary = out.get("summary")
                ai_impact_note = ai_impact_note or out.get("impact_note")
            except Exception:
                pass  # summarization is best-effort; never blocks publish

    update = LegalUpdate(
        law_id=law_id, title=title, source_url=source_url, published_date=published_date,
        ai_summary=ai_summary, ai_impact_note=ai_impact_note, affects_filter=affects_filter or {},
    )
    session.add(update)
    session.flush()
    audit.record(session, action="legal_update_published", organization_id=organization_id,
                 actor_user_id=actor_user_id, entity_type="legal_update", entity_id=str(update.id),
                 meta={"title": title, "affects_filter": affects_filter or {}})
    return update


def _org_profiles(session: Session, organization_id) -> list[dict]:
    rows = session.execute(
        select(CompanyProfile).where(CompanyProfile.organization_id == organization_id)
    ).scalars().all()
    return [r.profile for r in rows if r.profile]


def _affected_counts_by_law(session: Session, organization_id) -> dict[str, int]:
    """Active obligations the org holds under each law — the concrete 'affected
    obligations' signal for a legal update that names a law."""
    rows = session.execute(
        select(ObligationTemplate.law_id, func.count())
        .join(CompanyObligation, CompanyObligation.template_id == ObligationTemplate.template_id)
        .where(CompanyObligation.organization_id == organization_id,
               CompanyObligation.is_active.is_(True))
        .group_by(ObligationTemplate.law_id)
    ).all()
    return {law_id: n for law_id, n in rows}


def list_for_org(session: Session, *, organization_id) -> list[dict]:
    profiles = _org_profiles(session, organization_id)
    affected = _affected_counts_by_law(session, organization_id)
    updates = session.execute(
        select(LegalUpdate).order_by(LegalUpdate.created_at.desc())
    ).scalars().all()
    statuses = {
        s.legal_update_id: s
        for s in session.execute(
            select(LegalUpdateStatus).where(
                LegalUpdateStatus.organization_id == organization_id)
        ).scalars().all()
    }
    out = []
    for u in updates:
        m = match_org(u.affects_filter, profiles)
        st = statuses.get(u.id)
        out.append({
            "id": str(u.id), "title": u.title, "law_id": u.law_id,
            "source_url": u.source_url,
            "published_date": u.published_date.isoformat() if u.published_date else None,
            "ai_summary": u.ai_summary, "ai_impact_note": u.ai_impact_note,
            "match": m["decision"], "match_missing": m["missing_fields"],
            "review_status": st.status if st else "new",
            "affected_obligations": affected.get(u.law_id, 0) if u.law_id else 0,
        })
    return out


def review_update(session: Session, *, organization_id, legal_update_id, status: str,
                  reviewed_by, reason: str | None = None) -> LegalUpdateStatus:
    if status not in REVIEW_STATUSES:
        raise ValueError(f"invalid review status '{status}'")
    row = session.execute(
        select(LegalUpdateStatus).where(
            LegalUpdateStatus.organization_id == organization_id,
            LegalUpdateStatus.legal_update_id == legal_update_id)
    ).scalar_one_or_none()
    if row is None:
        row = LegalUpdateStatus(organization_id=organization_id,
                                legal_update_id=legal_update_id)
        session.add(row)
    row.status = status
    row.reviewed_by = reviewed_by
    row.reviewed_at = datetime.now(UTC)
    session.flush()
    audit.record(session, action="legal_update_reviewed", organization_id=organization_id,
                 actor_user_id=reviewed_by, entity_type="legal_update",
                 entity_id=str(legal_update_id), meta={"status": status, "reason": reason})
    return row
