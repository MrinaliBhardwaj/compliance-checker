# Instance-Generator Engine — Specification (Phase 1)
## NBFC Compliance Platform

> **Component:** Instance Generator
> **Role:** Converts applicable `company_obligations` into dated, recurring `obligation_instances` using each template's `due_rule`
> **Status:** Build-ready. A working reference implementation (`instance_generator.py`) accompanies this spec and runs against the live library + the applicability engine.
> **Scope:** Phase 1 only.

---

## 1. PURPOSE & POSITION IN THE SYSTEM

The applicability engine decides *which* obligations apply. The instance generator decides *when each one is due*, repeatedly, over time. It is the component that turns a static obligation list into the living compliance calendar the tracker, dashboard, and reminders all run on.

```
company_obligations  (one row per applicable obligation, from applicability engine)
        │
        ▼
┌──────────────────────────────┐
│  INSTANCE GENERATOR           │  ← this spec
│  due_rule → dated occurrences │
└──────────────────────────────┘
        │   obligation_instances (period_label, due_date, status, owner)
        ▼
Tracker · Dashboard · Reminders · Audit
```

**Core data-model relationship (from the PRD):**
> `obligation_template` (master) → `company_obligation` (per org, applicable) → `obligation_instance` (per occurrence, dated)

A monthly obligation like *TDS deposit* exists as one `company_obligation` and generates twelve `obligation_instances` per year, each with its own due date, owner, status, and evidence. **This is what makes recurring compliance trackable rather than a flat checklist.**

**Verified scale:** for the golden middle-layer profile (100 applicable obligations across 4 states), the generator produced **367 dated instances** over a single FY window — the real working volume a compliance team faces, now structured.

---

## 2. INPUTS

| Input | Source | Notes |
|---|---|---|
| `company_obligations` | Applicability engine output (persisted) | carries `template_id`, `due_rule`, `owner_role`, `risk_level`, and `state` (for state-expanded rows) |
| **Calendar context** | System config | FY start month (April for India), quarter-ends, holiday calendar |
| **Anchors** | Other instances' actual dates | e.g., AGM completion date → anchors AOC-4/MGT-7 (see §5) |
| **Data anchors** | Documents / profile | e.g., licence expiry (AI-extracted) → anchors renewal; customer risk tier → re-KYC |
| **Generation window** | Job config | rolling horizon `[window_start, window_end]`, default 12 months |

---

## 3. THE `due_rule` TAXONOMY

The live library uses **30 `due_rule.type` values**, which the generator resolves into **five families**. Every type is accounted for.

### Family 1 — Scheduled recurring (produces dated instances on the horizon)

| `due_rule.type` | Cadence | Date logic | Example obligation |
|---|---|---|---|
| `day_of_month` | monthly | Nth of (period + `offset_month`); `march_special` & `qrmp_alt` overrides | TDS deposit, GSTR-3B |
| `days_after_month_end` | monthly | month-end + `days` | ALM statements |
| `days_after_quarter_end` | quarterly | quarter-end + `days`; `annual_days` for year-end quarter | DNBS02/03, SEBI Reg 52 |
| `days_after_fortnight_end` | fortnightly | 15th/month-end + `days` | CIC reporting |
| `weekly` | weekly | next `day_of_week` each week | CRILC-SMA |
| `fixed_date` | annual | fixed `month`/`day` | DPT-3 (30 Jun), FLA (15 Jul) |
| `days_after_fy_end` | annual | 31 Mar + `days` | SAC, auditor report |
| `tds_return_dates` / `advance_tax_dates` / `esi_return_dates` / `msme_dates` | quarterly/HY | explicit `dates` list (MM-DD) | TDS returns, advance tax |
| `state_specific` | monthly/HY | `default_day` (monthly) or `common_dates` (HY), per state | Professional Tax, LWF |
| `max_gap_days` | quarterly | placeholders honoring max gap | Board meetings (≤120 days) |
| `license_renewal` | annual | expiry − `lead_days` (data-anchored) | Shops & Establishment renewal |

### Family 2 — Governance cadence (FY-anchored review instances)

| `due_rule.type` | Cadence | Example |
|---|---|---|
| `annual_board_review`, `annual_review`, `before_board_report` | annual (FY) | KYC policy review, FPC review, secretarial audit |
| `first_board_meeting_of_fy` | annual | MBP-1 / DIR-8 collection |
| `audit_committee_cycle` | quarterly | RBIA, loans-to-directors review |

These generate scheduled internal-review instances anchored to the financial year, not a statutory filing date.

### Family 3 — Dependency-anchored (due relative to another obligation's *actual* date)

| `due_rule.type` | Anchored to | Example |
|---|---|---|
| `days_after_agm` | AGM instance completion date | AOC-4 (+30d), MGT-7 (+60d) |
| `days_after_tds_return` | TDS return instance date | Form 16A issue (+15d) |

See §5 for handling.

### Family 4 — Event-driven (NOT generated on a schedule; created on a trigger)

| `due_rule.type` | Trigger | Example |
|---|---|---|
| `days_after_event` | a business event occurs | FC-GPR (allotment+30d), DIR-12, CHG-1, STR |
| `before_event` | an event is planned | 15CA/CB (before remittance), SEBI board-meeting intimation |
| `hours_after_event` | incident detected | cyber-incident report (+6h) |
| `around_due_date` | debt servicing date | SEBI Reg 57 payment intimation |
| `days_after_account_open` | account opened | CKYCR upload (+10d) |
| `per_loan_disbursal`, `per_rate_reset` | per transaction | KFS issuance, EMI reset comms |
| `risk_based_periodic` | customer risk tier | re-KYC (2/8/10 yrs) |

The generator does **not** pre-create these. It registers an **event listener**; an instance is created when the event fires (see §6).

### Family 5 — Continuous controls (no dated instance)

`continuous` — perpetual obligations (statutory registers, insider-trading SDD). Represented as a standing control with periodic review, not dated occurrences.

---

## 4. SCHEDULED GENERATION ALGORITHM

```
generate(company_obligations, ctx):
  for each company_obligation co:
    family = classify(co.due_rule.type)
    if family == EVENT_DRIVEN:   register_event_listener(co); continue
    if family == CONTINUOUS:     ensure_standing_control(co); continue
    rows = strategy[co.due_rule.type](co.due_rule, ctx)   # → [(period_label, due_date, adjusted)]
    for (label, due, adjusted) in rows:
        if due is None:  park(co, label); continue        # awaiting an anchor (§5)
        upsert_instance(co.id, label, due, adjusted)      # idempotent on (co.id, label)
```

**Rolling horizon:** the job generates only instances whose due date falls within `[window_start, window_end]` (default today → +12 months). A nightly run extends the window forward, so the calendar is always populated ~12 months ahead without unbounded growth.

**Idempotency (critical):** `(company_obligation_id, period_label)` is **unique**. `period_label` is deterministic per occurrence (`2026Q1`, `2026-07`, `FY2026`, `WK-31-2026`). Re-running the generator **upserts** — it never creates duplicates and never disturbs an instance whose status has advanced.

### 4.1 Working-day adjustment

If a computed due date falls on a weekend or holiday and the rule has `working_day_adjustment: "next"`, the date shifts to the next working day; the instance is flagged `working_day_adjusted: true`.

- Holiday source: a configurable holiday table (national + RBI + state). Phase-1 ships a seed set; the content/ops team maintains it.
- **Verified:** in the golden run, **92 of 367** due dates were shifted off non-working days — material enough that getting this wrong would mis-state a large share of deadlines.

> **Statutory nuance for the content team:** a few statutes specify "preceding working day" rather than "next." The rule carries the mode per obligation; default is `next`. Verify per obligation during the content pass.

---

## 5. DEPENDENCY HANDLING

Two distinct dependency types exist in the library:

### 5.1 Schedule dependency (due date anchored to another instance's actual date)

The due date cannot be computed from the calendar alone — it depends on when a predecessor *actually* happened.

- **Example:** AOC-4 is due **30 days after the AGM**. The AGM is itself an instance; its due date is statutory (within 6 months of FY end) but its *actual* date is set when the board schedules/holds it.
- **Mechanism:** the dependent instance is created in a **parked** state (`due_date = null`, status `awaiting_anchor`) until the anchor instance's actual date is recorded. When the AGM instance is marked complete with an actual date, the generator computes `anchor_date + days`, applies working-day adjustment, and activates the dependent instance.
- The `dependencies` array on the template declares the anchor (e.g., `ca_aoc4` depends on `ca_agm`).

### 5.2 Sequencing dependency (cannot start until predecessor done)

Soft ordering for owners — e.g., *Form 16A issuance* follows the *TDS return*. Both have computable dates, but the dependent should not be actionable before the predecessor completes.

- **Mechanism:** the dependent instance is generated with its computed date but carries a `blocked_by` reference; the UI surfaces it as blocked until the predecessor reaches `completed`. It does not block the due date or overdue clock — only the workflow affordance.

> Phase-1 keeps dependencies to the explicit ones in the library (`days_after_agm`, `days_after_tds_return`, and `dependencies[]` links). No general dependency graph engine — that is deliberate scope control.

---

## 6. EVENT-DRIVEN INSTANCES

Event-driven obligations have no schedule. The generator registers the `company_obligation` as a listener; an instance is created when the event is reported.

| Step | Behavior |
|---|---|
| **Trigger** | A business event is recorded (share allotment, director change, charge creation, suspicious transaction, account opening, cyber incident, foreign remittance) — via UI action, integration, or copilot. |
| **Creation** | On trigger, create one instance: `due_date = event_date + days` (or `event_date − lead` for `before_event`; `+hours` for `hours_after_event`). |
| **High-frequency events** | `days_after_account_open` (CKYCR) and `per_loan_disbursal` (KFS) can fire at high volume. Phase-1 models these as a **periodic batch obligation** (e.g., "CKYCR uploads — this month") rather than one instance per account, to avoid millions of rows. Per-transaction tracking is explicitly out of Phase-1 scope. |
| **`risk_based_periodic`** | re-KYC is portfolio-level in Phase 1: an annual review instance, not per-customer scheduling. |

**Verified:** the golden profile yielded **21 event-driven** obligations correctly held back from scheduled generation, and **3 continuous controls** with no dated instances.

---

## 7. STATUS STATE MACHINE

```
                ┌─────────── not_applicable (admin) ───────────┐
                │                                               │
  pending ──► in_progress ──► ready_for_review ──► completed    │
     │             │                  │                ▲        │
     │             │                  └── rejected ────┘        │
     └─────────────┴──────────► overdue ◄────────────(time)     │
                                  (auto, reversible)            │
   any state ─────────────────────────────────────────────────►┘
```

| Status | Meaning | Transition |
|---|---|---|
| `pending` | generated, not started | → in_progress / overdue / not_applicable |
| `in_progress` | owner working on it | → ready_for_review / overdue |
| `ready_for_review` | preparer submitted (Maker) | → completed (approver) / in_progress (rejected) |
| `completed` | approved with evidence (Checker) | terminal; reopenable by admin (audited) |
| `overdue` | past due, not completed | computed; auto-clears on completion |
| `not_applicable` | admin-excluded for this period | terminal |

**Maker-Checker:** preparer → `ready_for_review`; compliance_admin/head → `completed` or reject back to `in_progress`. Single-level approval in Phase 1 (no multi-level chains).

---

## 8. OVERDUE LOGIC

- **Definition:** an instance is overdue when `today > due_date` and `status ∉ {completed, not_applicable}`.
- **Computation:** a **daily sweep job** flips qualifying instances to `overdue` and emits escalation events; status is also evaluated on read so the dashboard is never stale between sweeps.
- **No grace period** by default for statutory obligations — overdue begins the day after the due date. (Reminders fire *before* the due date to prevent this; see §9.)
- **Reversibility:** completing an overdue instance moves it to `completed`; the fact that it *was* overdue is preserved in the audit log and feeds the dashboard's risk-weighting (an obligation repeatedly completed late is higher-risk even when currently green).
- **Escalation on overdue:** owner notified day +1; compliance_admin day +3; head day +7 (configurable). High-risk obligations escalate faster (see §9).

---

## 9. REMINDERS

Reminders are derived deterministically from each instance's `due_date`.

| Phase | Default schedule | Channel |
|---|---|---|
| **Pre-due** | 7, 3, 1 days before due | email + Slack to owner |
| **Due day** | on due date | owner |
| **Overdue escalation** | +1 (owner), +3 (admin), +7 (head) | email + Slack |
| **Maker-Checker** | on `ready_for_review` → approver; on reject → preparer | email + Slack |

**Risk weighting:** `risk_level = high` obligations use an earlier/denser cadence (e.g., 15/7/3/1 pre-due) and faster escalation. Lead times are configurable per org (PRD onboarding Step 6).

**Reminder recomputation:** reminders are a pure function of `(due_date, risk_level, org_config)`. Any change to the due date (§10) recomputes the schedule; already-sent reminders are not re-sent (tracked in `notifications`).

```
reminder_schedule(due, lead=(7,3,1), overdue=(1,3,7)) →
  { pre_due: [due-7, due-3, due-1], overdue_escalation: [due+1, due+3, due+7] }
```

---

## 10. RESCHEDULING

Due dates change for legitimate reasons. The generator handles four triggers; all are audited and never silently drop completion state.

| Trigger | Behavior |
|---|---|
| **Statutory extension** (govt notification) | Ops updates the instance (or a date-override on the template version); `due_date` updated, reminders recomputed, owner notified, audit logged. |
| **Working-day shift** | Handled at generation (§4.1); if the holiday table changes, the nightly run re-derives and reschedules affected *pending* instances. |
| **Anchor date set/changed** (e.g., AGM held later) | Dependent parked instances (§5.1) activate or shift; recompute `anchor + days`. |
| **Profile change** | Applicability engine re-runs; new obligations generate instances, removed ones deactivate (`is_active=false`); existing dated instances are untouched unless their `company_obligation` is deactivated. |

**Invariants:**
- A `completed` instance is **never** reopened or moved by rescheduling.
- Rescheduling a `pending`/`in_progress`/`overdue` instance updates the date and recomputes reminders; the overdue clock resets to the new date.
- Every reschedule writes a `before → after` record to the audit log.

---

## 11. AUDIT TRAIL

Every generator action is recorded to the append-only `audit_log` (PRD schema). This is non-negotiable: the audit trail *is* the compliance evidence.

| Event | Logged fields |
|---|---|
| Instance generated | actor=`system`, company_obligation_id, period_label, due_date, library_version, generation_run_id |
| Status change | actor (user/system), from_status → to_status, timestamp |
| Reschedule | actor, due_date before → after, reason |
| Reminder sent | channel, recipient, instance_id, timestamp |
| Completion/approval | completed_by, approved_by, linked evidence document ids |
| Reopen / mark N/A | actor, reason (required) |

**Determinism for audit:** identical `(company_obligations, calendar context, library version)` → identical instance set. Each generation run carries a `generation_run_id` and records the library version, so any instance traces back to the exact rules and inputs that produced it.

---

## 12. ARCHITECTURE & SCHEDULING

| Concern | Phase-1 approach |
|---|---|
| **Runtime** | BullMQ job on Redis (from PRD stack). Nightly full sweep + on-demand runs on profile change / anchor completion / event trigger. |
| **Nightly sweep** | (1) extend generation window; (2) upsert new instances; (3) flip overdue; (4) enqueue due reminders. |
| **Idempotency** | unique `(company_obligation_id, period_label)`; upsert semantics. |
| **Performance** | 100 obligations → 367 instances/yr computed in well under a second; trivially scales to first-20-customers volume. No sharding needed in Phase 1. |
| **Failure handling** | each `company_obligation` generated independently; a failure on one is logged as a gap and does not block others; the run is safely re-entrant. |
| **Unknown `due_rule.type`** | generates nothing, logs a coverage gap for engineering/content — never guesses a date. |

---

## 13. EDGE CASES

| Case | Handling |
|---|---|
| Mid-period onboarding | Generate from `window_start = onboarding_date` forward; prior-period instances are not back-created (optional backfill marked `historical`, excluded from overdue). |
| Due date on weekend/holiday | Working-day adjustment per rule; `working_day_adjusted` flagged. |
| Leap day / short months | `day_of_month` clamps to the last valid day (e.g., day 30 in February → 28/29). |
| Anchor never set (AGM not held) | Dependent stays `awaiting_anchor`; the AGM's own overdue logic drives escalation. |
| Licence expiry unknown | `license_renewal` parks until expiry is captured from an uploaded document. |
| Statutory extension after reminders sent | Reschedule updates date; future reminders recompute; sent ones not duplicated. |
| Obligation deactivated mid-cycle | Future `pending` instances cancelled; completed history preserved. |
| QRMP vs monthly GST | `day_of_month` carries `qrmp_alt`; generator selects branch from the org's `gst_scheme`. |
| March TDS special date | `day_of_month.march_special` overrides (deposit by 30 Apr, not 7 Apr). |
| Duplicate generation run | Upsert on unique key → no duplicates. |

---

## 14. TESTING STRATEGY

| Test class | What it locks down |
|---|---|
| **Strategy unit tests** | One per `due_rule.type`: assert exact dates over a fixed window (incl. `march_special`, `qrmp_alt`, `annual_days`). |
| **Working-day tests** | Weekend/holiday inputs shift correctly; flag set. |
| **Idempotency tests** | Running twice yields identical instance set; advanced-status instances untouched. |
| **Dependency tests** | Parked until anchor; activates on anchor completion with correct offset. |
| **Overdue tests** | Sweep flips only qualifying instances; completion clears; history retained. |
| **Reminder tests** | Schedule derivation; recompute on reschedule; no double-send. |
| **Golden regression** | Profile B (middle-layer, 4 states) → **367 instances**, 21 event-driven, 3 continuous, 92 working-day-adjusted. Locked as a fixture so library/engine changes that shift the calendar are caught. |

> As with the applicability engine: these tests prove the generator computes dates correctly. Whether a `due_rule` is *legally* correct (e.g., the exact CIMS return deadline) remains a content-team verification item against the `DRAFT_UNVERIFIED` gate.

---

## APPENDIX — REFERENCE IMPLEMENTATION

`instance_generator.py` (shipped with this spec) implements the scheduled, governance-cadence, dependency-anchored, and data-anchored families; the working-day adjuster with a holiday table; the overdue predicate; and the reminder-schedule function. It chains directly off `applicability_engine.py` and the live seed, and reproduces every figure in this document.

```
python instance_generator.py
```

Verified output (FY2026-27 window, golden Profile B):
```
Applicable company_obligations: 100
Dated instances generated:      367
Event-driven (trigger-created):  21
Continuous controls:              3
Working-day-adjusted due dates:  92
```

*Phase 1 only. Deterministic, idempotent, audit-logged; event-driven and continuous obligations handled out-of-band; wired to the same DRAFT_UNVERIFIED content gate.*
