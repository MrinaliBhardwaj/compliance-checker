"""
Copilot API (read-only). Loads the caller's instance rows, runs the deterministic
copilot turn (intent -> scope-before-retrieval -> grounded answer), persists the
turn to the append-only copilot_messages log, and returns the grounded result.

Permission scoping happens inside the engine at retrieval time (admin sees all,
preparer sees only their assigned rows) — never by filtering prose.
"""

from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession
from app.core.security import CurrentPrincipal
from app.engines.copilot import answer
from app.models.compliance import CompanyObligation, ObligationInstance
from app.models.content import ObligationTemplate
from app.models.system import CopilotMessage

router = APIRouter(prefix="/copilot", tags=["copilot"])


class Ask(BaseModel):
    query: str


def _load_instance_rows(db, organization_id: str) -> list[dict]:
    # One joined select: the applicability id and the template's owner role come with
    # each row instead of a lazy load per instance (was N+1).
    rows = db.execute(
        select(
            ObligationInstance,
            CompanyObligation.applicability_id,
            ObligationTemplate.default_owner_role,
        )
        .join(CompanyObligation, ObligationInstance.company_obligation_id == CompanyObligation.id)
        .join(ObligationTemplate, CompanyObligation.template_id == ObligationTemplate.template_id)
        .where(
            ObligationInstance.organization_id == organization_id,
            CompanyObligation.is_active.is_(True),
        )
    ).all()
    return [
        {
            "id": str(i.id),
            "template_id": applicability_id,
            "due_date": i.due_date.isoformat() if i.due_date else "9999-12-31",
            "status": i.status,
            "owner_user_id": str(i.owner_user_id) if i.owner_user_id else None,
            "owner_role": owner_role or "preparer",
            "period_label": i.period_label,
        }
        for i, applicability_id, owner_role in rows
    ]


@router.post("/ask")
def ask(body: Ask, db: DbSession, principal: CurrentPrincipal) -> dict:
    rows = _load_instance_rows(db, principal.organization_id)
    turn = answer(
        body.query,
        role=principal.role,
        user_id=principal.user_id,
        instances=rows,
        today=date.today(),
    )

    # Persist both sides of the turn (append-only, full traceability): the question,
    # then the answer with what it was grounded on.
    db.add(
        CopilotMessage(
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            role="user",
            content=body.query,
            model_version="copilot-v1",
        )
    )
    db.add(
        CopilotMessage(
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            role="assistant",
            content=json.dumps(turn.answer_facts, default=str),
            intent=turn.intent,
            retrieved_context={"ids": turn.citations},
            citations=turn.citations,
            confidence=turn.confidence,
            provisional=turn.provisional,
            escalation=turn.escalation_reason,
            grounding=turn.grounding,
            model_version="copilot-v1",
        )
    )
    return {
        "intent": turn.intent,
        "escalated": turn.escalated,
        "escalation_reason": turn.escalation_reason,
        "answer_facts": turn.answer_facts,
        "citations": turn.citations,
        "confidence": turn.confidence,
        "grounding": turn.grounding,
        "scope_note": turn.scope_note,
        "provisional": turn.provisional,
    }
