"""
Copilot API (read-only). Loads the caller's instance rows, runs the deterministic
copilot turn (intent -> scope-before-retrieval -> grounded answer), persists the
turn to the append-only copilot_messages log, and returns the grounded result.

Permission scoping happens inside the engine at retrieval time (admin sees all,
preparer sees only their assigned rows) — never by filtering prose.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession
from app.core.security import CurrentPrincipal
from app.engines.copilot import answer
from app.models.compliance import ObligationInstance
from app.models.system import CopilotMessage

router = APIRouter(prefix="/copilot", tags=["copilot"])


class Ask(BaseModel):
    query: str


def _load_instance_rows(db, organization_id: str) -> list[dict]:
    rows = db.execute(
        select(ObligationInstance).where(
            ObligationInstance.organization_id == organization_id)
    ).scalars().all()
    return [
        {"id": str(i.id), "template_id": i.company_obligation.applicability_id,
         "due_date": i.due_date.isoformat() if i.due_date else "9999-12-31",
         "status": i.status, "owner_user_id": str(i.owner_user_id) if i.owner_user_id else None,
         "owner_role": "preparer", "period_label": i.period_label}
        for i in rows
    ]


@router.post("/ask")
def ask(body: Ask, db: DbSession, principal: CurrentPrincipal) -> dict:
    rows = _load_instance_rows(db, principal.organization_id)
    turn = answer(body.query, role=principal.role, user_id=principal.user_id,
                  instances=rows, today=date.today())

    # persist the turn (append-only; full traceability)
    db.add(CopilotMessage(
        organization_id=principal.organization_id, user_id=principal.user_id,
        role="user", content=body.query, intent=turn.intent,
        retrieved_context={"ids": turn.citations}, citations=turn.citations,
        confidence=turn.confidence, provisional=turn.provisional,
        escalation=turn.escalation_reason, grounding=turn.grounding,
        model_version="copilot-v1",
    ))
    return {
        "intent": turn.intent, "escalated": turn.escalated,
        "escalation_reason": turn.escalation_reason, "answer_facts": turn.answer_facts,
        "citations": turn.citations, "confidence": turn.confidence,
        "grounding": turn.grounding, "scope_note": turn.scope_note,
        "provisional": turn.provisional,
    }
