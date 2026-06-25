r"""
Obligation-instance lifecycle (Maker-Checker), pure rules.

Encodes the instance-generator spec §7 state machine + the PRD §10 role matrix as
data, so transitions are testable in isolation and the service layer only persists
+ audits the outcome. `overdue` is computed on read (not a stored transition) and
never blocks a legitimate transition.

    pending -> in_progress -> ready_for_review -> completed
                    |               |  ^             |
                    |          (reject)  \____________| (reopen, admin)
       any open ----+--------------------------------> not_applicable (admin)

Maker  = preparer submits (-> ready_for_review)
Checker = compliance_admin / head approves (-> completed) or rejects
"""
from __future__ import annotations

from dataclasses import dataclass

OPEN_STATES = ("pending", "in_progress", "ready_for_review", "overdue")
TERMINAL_STATES = ("completed", "not_applicable")


class LifecycleError(Exception):
    """Illegal state transition (HTTP 409)."""


class RolePermissionError(Exception):
    """Caller's role may not perform this action (HTTP 403)."""


@dataclass(frozen=True)
class Action:
    name: str
    allowed_from: frozenset[str] | None   # None = any non-terminal state
    to_status: str
    roles: frozenset[str]
    requires_evidence: bool = False        # approve gate: primary evidence present


# `overdue` is an effective (computed) status; the stored status under it is one of
# pending/in_progress/ready_for_review, so transitions accept those plus overdue.
ACTIONS: dict[str, Action] = {
    "start": Action("start", frozenset({"pending", "overdue"}), "in_progress",
                    frozenset({"preparer", "compliance_admin", "head"})),
    "submit": Action("submit", frozenset({"pending", "in_progress", "overdue"}),
                     "ready_for_review", frozenset({"preparer", "compliance_admin"})),
    "approve": Action("approve", frozenset({"ready_for_review"}), "completed",
                      frozenset({"compliance_admin", "head"}), requires_evidence=True),
    "reject": Action("reject", frozenset({"ready_for_review"}), "in_progress",
                     frozenset({"compliance_admin", "head"})),
    "mark_na": Action("mark_na", None, "not_applicable",
                      frozenset({"compliance_admin"})),
    "reopen": Action("reopen", frozenset({"completed", "not_applicable"}), "in_progress",
                     frozenset({"compliance_admin"})),
}


def plan_transition(action_name: str, current_status: str, role: str) -> str:
    """Validate role + state; return the target status. Raises on violation."""
    action = ACTIONS.get(action_name)
    if action is None:
        raise LifecycleError(f"unknown action '{action_name}'")
    if role not in action.roles:
        raise RolePermissionError(
            f"role '{role}' may not '{action_name}' (allowed: {sorted(action.roles)})")
    if action.allowed_from is None:
        if current_status in TERMINAL_STATES:
            raise LifecycleError(f"cannot '{action_name}' a {current_status} instance")
    elif current_status not in action.allowed_from:
        raise LifecycleError(
            f"cannot '{action_name}' from '{current_status}' "
            f"(allowed from: {sorted(action.allowed_from)})")
    return action.to_status
