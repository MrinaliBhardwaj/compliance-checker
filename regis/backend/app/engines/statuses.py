"""
The obligation-instance status vocabulary, declared once.

Same doctrine as `thresholds.py`: one fact, one place. A status set spread
across call sites drifts the moment a status is added, and it drifts silently —
nothing fails, the numbers just stop agreeing with each other.

That is exactly what happened when `historical` was introduced for
pre-onboarding filings. The nightly sweep in `jobs/worker.py` was written as an
**allowlist** ("flip these open states") and kept working. The engines were
written as **denylists** ("anything that is not completed or not_applicable"),
so a new terminal state silently fell through as open: the copilot reported
every historical instance as overdue while the dashboard, computed elsewhere,
reported none. One org, two numbers, both shown to the same customer.

Prefer OPEN_STATUSES when you mean "still someone's work". An allowlist fails
closed when the vocabulary grows; a denylist fails open, and failing open here
means inventing overdue filings.
"""
from __future__ import annotations

# Every value obligation_instances.status may hold.
INSTANCE_STATUSES: tuple[str, ...] = (
    "pending", "in_progress", "ready_for_review",
    "completed", "overdue", "not_applicable", "historical",
)

# Closed: no further work is owed on these.
#   completed       — filed and approved
#   not_applicable  — ruled out for this entity
#   historical      — fell due before the customer onboarded; not their work
TERMINAL_STATUSES: tuple[str, ...] = ("completed", "not_applicable", "historical")

# Open: still owed by somebody. This is the set to test against.
OPEN_STATUSES: tuple[str, ...] = tuple(
    s for s in INSTANCE_STATUSES if s not in TERMINAL_STATUSES and s != "overdue"
)

# Open, including already-flagged-overdue rows — for "what is outstanding".
OUTSTANDING_STATUSES: tuple[str, ...] = tuple(
    s for s in INSTANCE_STATUSES if s not in TERMINAL_STATUSES
)
