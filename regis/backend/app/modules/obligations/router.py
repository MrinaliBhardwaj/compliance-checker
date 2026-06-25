"""
Obligations API: the daily tracker + dashboard rollup + Maker-Checker lifecycle.
Overdue is evaluated on read (PRD §8) so the dashboard is never stale between
nightly sweeps. Status changes go through the lifecycle service (validated +
audited); the AI never writes a terminal state.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, status as http_status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession
from app.core.security import CurrentPrincipal
from app.models.compliance import CompanyObligation, ObligationInstance
from app.models.content import ObligationTemplate
from app.models.evidence import Document, DocumentLink
from app.modules.documents.service import completeness_for_instance
from app.modules.obligations import service as svc
from app.modules.obligations.lifecycle import LifecycleError, RolePermissionError

router = APIRouter(prefix="/obligations", tags=["obligations"])

_OPEN = ("pending", "in_progress", "ready_for_review")


def _effective_status(i: ObligationInstance, today: date) -> str:
    if i.status in _OPEN and i.due_date and i.due_date < today:
        return "overdue"
    return i.status


def _instance_row(i: ObligationInstance, co: CompanyObligation,
                  tpl: ObligationTemplate, today: date) -> dict:
    """The tracker row the UI renders: enough to show name, law, risk, due, status."""
    return {
        "id": str(i.id), "period_label": i.period_label,
        "due_date": i.due_date.isoformat() if i.due_date else None,
        "status": _effective_status(i, today),
        "working_day_adjusted": i.working_day_adjusted,
        "owner_user_id": str(i.owner_user_id) if i.owner_user_id else None,
        "title": tpl.title, "category": tpl.category, "risk_level": tpl.risk_level,
        "form_reference": tpl.form_reference, "template_id": tpl.template_id,
        "state": co.state,
    }


@router.get("/instances")
def list_instances(db: DbSession, principal: CurrentPrincipal,
                   status: str | None = None, category: str | None = None,
                   q: str | None = None) -> list[dict]:
    query = (
        select(ObligationInstance, CompanyObligation, ObligationTemplate)
        .join(CompanyObligation, ObligationInstance.company_obligation_id == CompanyObligation.id)
        .join(ObligationTemplate, CompanyObligation.template_id == ObligationTemplate.template_id)
        .where(ObligationInstance.organization_id == principal.organization_id)
        .order_by(ObligationInstance.due_date)
    )
    triples = db.execute(query).all()
    today = date.today()
    out = []
    for i, co, tpl in triples:
        # preparers see only their assigned instances (PRD role matrix)
        if principal.role == "preparer" and str(i.owner_user_id) != principal.user_id:
            continue
        row = _instance_row(i, co, tpl, today)
        if status and row["status"] != status:
            continue
        if category and row["category"] != category:
            continue
        if q and q.lower() not in (row["title"] or "").lower():
            continue
        out.append(row)
    return out


@router.get("/instances/{instance_id}")
def instance_detail(instance_id: str, db: DbSession, principal: CurrentPrincipal) -> dict:
    triple = db.execute(
        select(ObligationInstance, CompanyObligation, ObligationTemplate)
        .join(CompanyObligation, ObligationInstance.company_obligation_id == CompanyObligation.id)
        .join(ObligationTemplate, CompanyObligation.template_id == ObligationTemplate.template_id)
        .where(ObligationInstance.id == instance_id,
               ObligationInstance.organization_id == principal.organization_id)
    ).first()
    if not triple:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Instance not found")
    i, co, tpl = triple
    if principal.role == "preparer" and str(i.owner_user_id) != principal.user_id:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Not your assigned obligation")

    today = date.today()
    docs = db.execute(
        select(Document)
        .join(DocumentLink, DocumentLink.document_id == Document.id)
        .where(DocumentLink.obligation_instance_id == i.id)
    ).scalars().all()
    return {
        **_instance_row(i, co, tpl, today),
        "description": tpl.description, "penalty_note": tpl.penalty_note,
        "frequency": tpl.frequency, "law_id": tpl.law_id,
        "verification_status": tpl.verification_status,
        "applicability_confidence": float(co.applicability_confidence)
        if co.applicability_confidence is not None else None,
        "rationale": co.rationale,
        "completeness": completeness_for_instance(db, i),
        "linked_documents": [
            {"id": str(d.id), "file_name": d.file_name, "ai_doc_type": d.ai_doc_type,
             "processing_status": d.processing_status} for d in docs],
    }


@router.get("/dashboard")
def dashboard(db: DbSession, principal: CurrentPrincipal) -> dict:
    """Risk-weighted counts for the action tiles + a simple health score."""
    rows = db.execute(
        select(ObligationInstance)
        .where(ObligationInstance.organization_id == principal.organization_id)
    ).scalars().all()
    if principal.role == "preparer":
        rows = [i for i in rows if str(i.owner_user_id) == principal.user_id]
    today = date.today()
    week = today + timedelta(days=7)
    counts = Counter(_effective_status(i, today) for i in rows)
    overdue = counts.get("overdue", 0)
    due_week = sum(1 for i in rows
                   if i.due_date and today <= i.due_date <= week
                   and _effective_status(i, today) in _OPEN)
    total = len(rows) or 1
    completed = counts.get("completed", 0)
    health = round(100 * (1 - overdue / total))
    return {
        "health_score": health,
        "tiles": {"overdue": overdue, "due_this_week": due_week,
                  "awaiting_review": counts.get("ready_for_review", 0),
                  "completed": completed},
        "by_status": dict(counts),
        "total_instances": len(rows),
    }


# ---------------------------------------------------------------------------
# Maker-Checker lifecycle
# ---------------------------------------------------------------------------
class TransitionBody(BaseModel):
    override_evidence: bool = False   # admin/head may override the evidence gate (audited)
    reason: str | None = None


class AssignBody(BaseModel):
    owner_user_id: str


def _map_errors(fn):
    try:
        return fn()
    except svc.InstanceNotFound:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Instance not found")
    except RolePermissionError as e:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, str(e))
    except (LifecycleError, svc.EvidenceGateError) as e:
        raise HTTPException(http_status.HTTP_409_CONFLICT, str(e))


@router.get("/instances/{instance_id}/completeness")
def instance_completeness(instance_id: str, db: DbSession, principal: CurrentPrincipal) -> dict:
    inst = db.get(ObligationInstance, instance_id)
    if not inst or str(inst.organization_id) != principal.organization_id:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Instance not found")
    return completeness_for_instance(db, inst)


@router.post("/instances/{instance_id}/assign")
def assign(instance_id: str, body: AssignBody, db: DbSession,
           principal: CurrentPrincipal) -> dict:
    inst = _map_errors(lambda: svc.assign_owner(
        db, organization_id=principal.organization_id, instance_id=instance_id,
        owner_user_id=body.owner_user_id, principal=principal))
    return {"id": str(inst.id), "owner_user_id": str(inst.owner_user_id)}


def _transition_route(action: str):
    def handler(instance_id: str, body: TransitionBody, db: DbSession,
                principal: CurrentPrincipal) -> dict:
        inst = _map_errors(lambda: svc.transition(
            db, organization_id=principal.organization_id, instance_id=instance_id,
            action=action, principal=principal,
            override_evidence=body.override_evidence, reason=body.reason))
        return {"id": str(inst.id), "status": inst.status,
                "completed_at": inst.completed_at.isoformat() if inst.completed_at else None}
    return handler


# Maker-Checker verbs (each validated + audited in the service layer)
for _action in ("start", "submit", "approve", "reject", "mark_na", "reopen"):
    router.add_api_route(f"/instances/{{instance_id}}/{_action}",
                         _transition_route(_action), methods=["POST"],
                         name=f"instance_{_action}")
