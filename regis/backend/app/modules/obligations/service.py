"""
Maker-Checker transitions over obligation_instances. Validates the move against
the lifecycle rules + role matrix, applies the evidence gate on approval, persists
completion metadata, and writes an immutable audit row for every change.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core import audit
from app.models.compliance import ObligationInstance
from app.modules.documents.service import completeness_for_instance
from app.modules.notify import service as notify
from app.modules.obligations.lifecycle import RolePermissionError, plan_transition


class InstanceNotFound(Exception):
    ...


class EvidenceGateError(Exception):
    """Approval blocked: primary evidence not present (HTTP 409)."""


def _get_instance(session: Session, organization_id, instance_id) -> ObligationInstance:
    inst = session.get(ObligationInstance, instance_id)
    if not inst or str(inst.organization_id) != str(organization_id):
        raise InstanceNotFound()
    return inst


def assign_owner(session: Session, *, organization_id, instance_id, owner_user_id,
                 principal) -> ObligationInstance:
    if principal.role not in ("compliance_admin",):
        raise RolePermissionError("only compliance_admin may assign owners")
    inst = _get_instance(session, organization_id, instance_id)
    prior = inst.owner_user_id
    inst.owner_user_id = owner_user_id
    audit.record(session, action="instance_assigned", organization_id=organization_id,
                 actor_user_id=principal.user_id, entity_type="obligation_instance",
                 entity_id=str(instance_id),
                 meta={"from": str(prior) if prior else None, "to": str(owner_user_id)})
    session.flush()
    notify.notify_assignment(session, organization_id=organization_id, instance=inst,
                             owner_user_id=owner_user_id)
    return inst


def transition(session: Session, *, organization_id, instance_id, action: str,
               principal, override_evidence: bool = False,
               reason: str | None = None) -> ObligationInstance:
    inst = _get_instance(session, organization_id, instance_id)

    # preparers act only on their own assigned instances
    if principal.role == "preparer" and str(inst.owner_user_id) != str(principal.user_id):
        raise RolePermissionError("preparers may only act on their assigned obligations")

    from_status = inst.status
    to_status = plan_transition(action, from_status, principal.role)  # raises on violation

    # evidence gate on approval (Maker-Checker completion). Override is audited.
    if action == "approve":
        comp = completeness_for_instance(session, inst)
        if not comp["eligible_for_completion"] and not override_evidence:
            raise EvidenceGateError(
                f"primary evidence required before completion "
                f"(missing: {[m[0] for m in comp['missing']]})")

    inst.status = to_status
    now = datetime.now(UTC)
    if action == "approve":
        inst.completed_at = now
        inst.completed_by = principal.user_id
        inst.approved_by = principal.user_id
    if action == "reopen":
        inst.completed_at = None
        inst.completed_by = None
        inst.approved_by = None

    audit.record(session, action="instance_status_change", organization_id=organization_id,
                 actor_user_id=principal.user_id, entity_type="obligation_instance",
                 entity_id=str(instance_id),
                 meta={"action": action, "from": from_status, "to": to_status,
                       "override_evidence": override_evidence, "reason": reason})
    session.flush()

    # Maker-Checker routing notifications (best-effort; recorded even if undelivered)
    if action == "submit":
        notify.notify_review_requested(session, organization_id=organization_id, instance=inst)
    elif action == "reject":
        notify.notify_rejected(session, organization_id=organization_id, instance=inst)
    return inst
