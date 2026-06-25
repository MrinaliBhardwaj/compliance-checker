"""Unit tests — Maker-Checker lifecycle rules (state machine + role matrix)."""
import pytest

from app.modules.obligations.lifecycle import (
    LifecycleError,
    RolePermissionError,
    plan_transition,
)


def test_happy_path_maker_checker():
    assert plan_transition("start", "pending", "preparer") == "in_progress"
    assert plan_transition("submit", "in_progress", "preparer") == "ready_for_review"
    assert plan_transition("approve", "ready_for_review", "compliance_admin") == "completed"


def test_overdue_can_still_be_worked():
    # overdue is an effective status; the underlying instance can still progress
    assert plan_transition("start", "overdue", "preparer") == "in_progress"
    assert plan_transition("submit", "overdue", "preparer") == "ready_for_review"


def test_preparer_cannot_approve():
    with pytest.raises(RolePermissionError):
        plan_transition("approve", "ready_for_review", "preparer")


def test_head_cannot_be_maker():
    with pytest.raises(RolePermissionError):
        plan_transition("submit", "in_progress", "head")


def test_only_admin_marks_na_and_reopens():
    assert plan_transition("mark_na", "pending", "compliance_admin") == "not_applicable"
    with pytest.raises(RolePermissionError):
        plan_transition("mark_na", "pending", "head")
    assert plan_transition("reopen", "completed", "compliance_admin") == "in_progress"


def test_illegal_state_transition():
    with pytest.raises(LifecycleError):
        plan_transition("approve", "pending", "compliance_admin")  # not submitted yet
    with pytest.raises(LifecycleError):
        plan_transition("reopen", "pending", "compliance_admin")   # only completed/na reopen


def test_cannot_act_on_terminal_with_open_action():
    with pytest.raises(LifecycleError):
        plan_transition("start", "completed", "compliance_admin")


def test_unknown_action():
    with pytest.raises(LifecycleError):
        plan_transition("teleport", "pending", "compliance_admin")
