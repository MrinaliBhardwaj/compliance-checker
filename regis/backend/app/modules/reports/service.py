"""
Compliance status report builder — deterministic, grounded in the org's actual
instances. No AI in the data path (legal defensibility): every number is computed
from rows, and the `provisional` banner reflects the DRAFT_UNVERIFIED content gate.

The same effective-status logic as the dashboard (overdue evaluated on read) so the
report and the live view never disagree.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.compliance import CompanyObligation, ObligationInstance
from app.models.content import ObligationTemplate
from app.models.evidence import DocumentLink
from app.models.tenancy import Entity, Organization

LIBRARY_VERSION = "0.1-draft"
_OPEN = ("pending", "in_progress", "ready_for_review")


def _effective_status(status: str, due: date | None, today: date) -> str:
    if status in _OPEN and due and due < today:
        return "overdue"
    return status


def build_compliance_report(session: Session, *, organization_id, today: date,
                            entity_id=None) -> dict:
    org = session.get(Organization, organization_id)
    entity = session.get(Entity, entity_id) if entity_id else None

    q = (select(ObligationInstance, CompanyObligation, ObligationTemplate)
         .join(CompanyObligation, ObligationInstance.company_obligation_id == CompanyObligation.id)
         .join(ObligationTemplate, CompanyObligation.template_id == ObligationTemplate.template_id)
         .where(ObligationInstance.organization_id == organization_id))
    if entity_id:
        q = q.where(CompanyObligation.entity_id == entity_id)
    triples = session.execute(q).all()

    week = today + timedelta(days=7)
    by_status: Counter = Counter()
    by_category: dict[str, Counter] = defaultdict(Counter)
    overdue, due_week, awaiting, completed = [], [], [], []
    provisional = False

    # evidence counts for completed instances (small N) — keyed by instance id
    completed_ids = [i.id for (i, _co, _t) in triples if i.status == "completed"]
    ev_counts: dict = {}
    if completed_ids:
        rows = session.execute(
            select(DocumentLink.obligation_instance_id, func.count())
            .where(DocumentLink.obligation_instance_id.in_(completed_ids))
            .group_by(DocumentLink.obligation_instance_id)
        ).all()
        ev_counts = {iid: n for iid, n in rows}

    for inst, _co, tpl in triples:
        eff = _effective_status(inst.status, inst.due_date, today)
        by_status[eff] += 1
        by_category[tpl.category][eff] += 1
        if tpl.verification_status != "VERIFIED":
            provisional = True
        item = {"period_label": inst.period_label, "title": tpl.title,
                "category": tpl.category, "form_reference": tpl.form_reference,
                "due_date": inst.due_date.isoformat() if inst.due_date else None,
                "status": eff, "risk_level": tpl.risk_level}
        if eff == "overdue":
            overdue.append(item)
        elif eff in _OPEN and inst.due_date and today <= inst.due_date <= week:
            due_week.append(item)
        if eff == "ready_for_review":
            awaiting.append(item)
        if eff == "completed":
            completed.append({**item, "evidence_count": ev_counts.get(inst.id, 0)})

    total = len(triples) or 1
    n_overdue = by_status.get("overdue", 0)
    health = round(100 * (1 - n_overdue / total))
    overdue.sort(key=lambda x: x["due_date"] or "")
    due_week.sort(key=lambda x: x["due_date"] or "")

    narrative = _narrative(by_status, len(overdue), len(due_week), len(awaiting))

    return {
        "organization": org.name if org else str(organization_id),
        "entity": entity.legal_name if entity else "All entities",
        "generated_at": datetime.now(UTC).isoformat(),
        "as_of": today.isoformat(),
        "library_version": LIBRARY_VERSION,
        "provisional": provisional,  # DRAFT_UNVERIFIED content gate -> shown as provisional
        "health_score": health,
        "totals": {"instances": len(triples), "by_status": dict(by_status)},
        "tiles": {"overdue": n_overdue, "due_this_week": len(due_week),
                  "awaiting_review": len(awaiting), "completed": by_status.get("completed", 0)},
        "narrative": narrative,
        "by_category": {k: dict(v) for k, v in by_category.items()},
        "sections": {
            "overdue": overdue,
            "due_this_week": due_week,
            "awaiting_review": awaiting,
            "completed": completed,
        },
    }


def _narrative(by_status: Counter, n_overdue: int, n_due_week: int, n_awaiting: int) -> str:
    """Deterministic, grounded narrative (no LLM in the legal-evidence path)."""
    parts = []
    if n_overdue:
        parts.append(f"{n_overdue} obligation(s) are overdue and need immediate attention")
    if n_due_week:
        parts.append(f"{n_due_week} are due within 7 days")
    if n_awaiting:
        parts.append(f"{n_awaiting} are awaiting review")
    if not parts:
        return "No overdue or imminent obligations. The compliance calendar is on track."
    return ". ".join([p.capitalize() if i == 0 else p for i, p in enumerate(parts)]) + "."
