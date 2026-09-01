"""
One status vocabulary, shared by every consumer.

`historical` was added for pre-onboarding filings and the codebase disagreed
with itself for a release: the nightly sweep (an allowlist) excluded it, the
engines (denylists) did not. The dashboard reported 0 overdue and the copilot
reported 77 for the same organisation, on the same data, in the same session.

These tests pin the shape that prevents it — not the specific statuses, which
are free to grow.
"""
from __future__ import annotations

import ast
from pathlib import Path

from app.engines import statuses as S
from app.engines.copilot import q_due_window
from app.models.compliance import INSTANCE_STATUSES
from app.modules.obligations.lifecycle import TERMINAL_STATES

_APP = Path(__file__).parents[2] / "app"


def test_every_consumer_shares_one_vocabulary():
    assert INSTANCE_STATUSES is S.INSTANCE_STATUSES
    assert TERMINAL_STATES is S.TERMINAL_STATUSES


def test_the_sets_partition_the_vocabulary():
    """Terminal and outstanding must together cover every status exactly once —
    a status in neither is invisible to every query that uses these sets."""
    assert set(S.TERMINAL_STATUSES) | set(S.OUTSTANDING_STATUSES) == set(S.INSTANCE_STATUSES)
    assert not set(S.TERMINAL_STATUSES) & set(S.OUTSTANDING_STATUSES)


def test_historical_is_terminal_everywhere():
    assert "historical" in S.TERMINAL_STATUSES
    assert "historical" not in S.OPEN_STATUSES
    assert "historical" not in S.OUTSTANDING_STATUSES


def test_open_excludes_already_flagged_overdue_but_outstanding_includes_it():
    """The sweep flips open -> overdue, so 'open' must not contain overdue or the
    sweep would re-flip forever; 'what is outstanding' must contain it or the
    copilot would under-report."""
    assert "overdue" not in S.OPEN_STATUSES
    assert "overdue" in S.OUTSTANDING_STATUSES


# ---------------------------------------------------------------------------
# The regression itself
# ---------------------------------------------------------------------------

def _inst(status, due):
    return {"id": status + due, "template_id": "t", "due_date": due,
            "status": status, "owner_user_id": None, "owner_role": "preparer",
            "period_label": "P"}


def test_copilot_does_not_count_historical_as_overdue():
    """The demo-breaking contradiction: a pre-onboarding filing is not overdue."""
    from datetime import date
    today = date(2026, 9, 1)
    rows = [
        _inst("historical", "2026-01-15"),   # before onboarding — not our work
        _inst("pending", "2026-08-01"),      # genuinely late
        _inst("overdue", "2026-07-01"),      # already flagged
        _inst("completed", "2026-02-01"),
        _inst("not_applicable", "2026-03-01"),
    ]
    sel, cites, facts = q_due_window(rows, today, "what is overdue?")
    assert facts["count"] == 2, [r["status"] for r in sel]
    assert {r["status"] for r in sel} == {"pending", "overdue"}
    assert len(cites) == 2


def test_no_consumer_reintroduces_a_hardcoded_terminal_pair():
    """The literal that caused this. A denylist fails open when the vocabulary
    grows — which here means inventing overdue filings out of closed ones."""
    offenders = []
    for path in sorted(_APP.rglob("*.py")):
        if path.name == "statuses.py":
            continue
        src = path.read_text()
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Tuple):
                continue
            vals = [e.value for e in node.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if {"completed", "not_applicable"} <= set(vals):
                offenders.append(f"{path.relative_to(_APP)}:{node.lineno}: {vals}")
    assert not offenders, (
        "status set hardcoded outside app/engines/statuses.py — import it "
        "instead so one vocabulary stays one vocabulary:\n" + "\n".join(offenders)
    )


def test_guard_is_not_vacuous():
    tree = ast.parse('X = ("completed", "not_applicable")\n')
    found = [n for n in ast.walk(tree) if isinstance(n, ast.Tuple)]
    vals = [e.value for e in found[0].elts]
    assert {"completed", "not_applicable"} <= set(vals)
