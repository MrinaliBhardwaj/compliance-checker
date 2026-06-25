# Applicability-Rule Engine — Specification (Phase 1)
## NBFC Compliance Platform

> **Component:** Applicability-Rule Engine
> **Role:** Converts an onboarding company profile into the org's applicable compliance obligations
> **Status:** Build-ready. A working reference implementation (`applicability_engine.py`) accompanies this spec and runs against the live 106-obligation seed.
> **Scope:** Phase 1 only.

---

## 1. PURPOSE & POSITION IN THE SYSTEM

The applicability-rule engine is the logic behind the single most important onboarding moment: *"Based on your profile, we identified N applicable compliance obligations across M laws."* It takes a structured **company profile** and evaluates it against every `obligation_template` in the library, deciding for each one whether it applies, with what confidence, and **why**.

```
Onboarding questionnaire
        │  (LLM-assisted profile extraction → structured profile)
        ▼
┌─────────────────────────────┐
│  APPLICABILITY-RULE ENGINE   │  ← this spec
│  (deterministic core)        │
└─────────────────────────────┘
        │  applicable / needs_review / not_applicable
        ▼
Review & confirm screen  → user accepts/deselects (human gate)
        │
        ▼
company_obligations rows written  →  instance generator spawns due dates
```

**Design stance (aligned with platform principles):** the engine is **deterministic and auditable**. The AI/LLM layer sits *around* it — turning messy onboarding answers into a clean profile, phrasing rationales, and asking follow-up questions — but **never overrides a deterministic applicability decision**. The engine proposes; the human confirms. This is what makes the generated calendar defensible in a regulated financial vertical.

---

## 2. INPUTS

### 2.1 The Company Profile

The profile is the structured output of onboarding (Step 2 of the onboarding flow in the PRD). Every field below is referenced by at least one applicability rule in the live library. A field set to `None` / absent means **"not yet answered"** — which the engine treats as *unknown*, routing the obligation to `NEEDS_REVIEW` rather than silently deciding "No".

**Hard fields** (objective, asked directly, high trust):

| Field | Type | Example |
|---|---|---|
| `rbi_registered` | bool | `true` |
| `nbfc_category` | enum | `icc` \| `nd_si` \| `deposit_taking` |
| `rbi_layer` | enum | `base` \| `middle` \| `upper` |
| `deposit_taking` | bool | `false` |
| `is_listed` | bool | `false` |
| `has_listed_debt` | bool | `true` |
| `asset_size_cr` | number | `3000` |
| `turnover_cr` | number | `450` |
| `employee_count` | int | `260` |
| `branch_count` | int | `22` |
| `operating_states` | list | `["MH","KA","TN","DL"]` |
| `gst_registered` | bool | `true` |
| `gst_scheme` | enum | `regular` \| `qrmp` |
| `is_isd` | bool | `false` |
| `esi_applicable` | bool | `true` |

**Soft fields** (self-declared operational flags — lower trust when present, route to review when absent):

`has_foreign_investment`, `has_nonresident_payments`, `has_international_transactions`, `has_reportable_accounts`, `has_msme_dues`, `csr_applicable`, `has_sbo`, `has_capital_changes`, `has_ecb`, `has_odi`, `has_eligible_bonus_employees`, `does_digital_lending`, `has_dlg_arrangements`, `has_floating_rate_retail`, `is_secured_lender`, `is_large_corporate`, `has_borrowings` — all boolean.

### 2.2 The Library

The `obligation_templates` array from the seed (106 templates). Each carries an `applicability_rule` object and a `verification_status` (`DRAFT_UNVERIFIED` until content-team sign-off).

---

## 3. THE RULE LANGUAGE (DSL)

An `applicability_rule` is a JSON object. **Each (key, value) pair is one condition. All conditions in a rule are AND-ed.** A rule matches the profile iff every condition matches.

The entire live library reduces to **seven predicate types**, resolved by key pattern and value type:

| # | Predicate | Triggered when | Semantics | Example condition |
|---|---|---|---|---|
| 1 | **Universal** | key is `all` | always true | `{"all": true}` |
| 2 | **Numeric min (₹cr)** | key ends `_min_cr` | `profile[base] >= value` (base = key minus `_min`) | `{"asset_size_min_cr": 500}` |
| 3 | **Numeric min (alias)** | key ends `_min` | `profile[alias] >= value` via alias map | `{"has_employees_min": 20}` → `employee_count >= 20` |
| 4 | **State intersection** | key in `{pt_states, lwf_states}` | `operating_states ∩ value ≠ ∅` | `{"pt_states": ["MH","KA",...]}` |
| 5 | **Enum membership** | value is a list (not above) | `profile[key] ∈ value` | `{"rbi_layer": ["middle","upper"]}` |
| 6 | **Boolean** | value is `true` | `bool(profile[key]) == true` | `{"gst_registered": true}` |
| 7 | **Scalar equality** | value is scalar | `profile[key] == value` | `{"gst_scheme": "qrmp"}` |

**Alias map** (irregular numeric-min keys → profile field):
`has_employees_min → employee_count`, `has_branches_min → branch_count`.

**Worked examples from the live library:**

- `{"all": true}` → applies to every org. (e.g., board meetings, AOC-4, TDS)
- `{"rbi_layer": ["middle","upper"]}` → applies only if `rbi_layer` is middle or upper. (e.g., Chief Compliance Officer)
- `{"asset_size_min_cr": 100, "rbi_layer": ["middle","upper"]}` → AND: asset size ≥ ₹100cr **and** middle/upper layer. (e.g., ALM structural liquidity)
- `{"gst_registered": true, "turnover_min_cr": 5}` → GST-registered **and** turnover ≥ ₹5cr. (e.g., GSTR-9C)
- `{"has_employees_min": 1, "pt_states": ["MH","KA",...]}` → has employees **and** operates in a PT state. (Professional Tax — state-expanded; see §6)

> **Phase-1 deliberate constraint:** the DSL supports only **AND across conditions**. There is no `OR`/`NOT`/nesting. Every real obligation in the library is expressible this way. If a future obligation needs disjunction, model it as two templates rather than complicating the engine. (Scope discipline.)

---

## 4. EVALUATION ALGORITHM

### 4.1 Per-condition

```
eval_condition(key, value, profile) -> {passed, missing, near_boundary}
  resolve predicate type from key/value (table in §3)
  if referenced profile field is None -> {passed: false, missing: true}
  else compute passed per predicate semantics
  for numeric predicates: flag near_boundary if within ±10% of threshold
```

### 4.2 Per-template decision

Conditions are AND-ed, but **missing ≠ failed**. The decision rule:

```
hard_fail = any condition that FAILED on a KNOWN value
if hard_fail:                 decision = NOT_APPLICABLE
elif any condition MISSING:   decision = NEEDS_REVIEW
else (all passed):            decision = APPLICABLE
```

This three-state output is the core safety property: an obligation is only **excluded** when the profile gives a concrete reason to exclude it. Unknown inputs surface for human confirmation instead of disappearing.

### 4.3 Worked decision examples (from the reference run)

- `it_tds_deposit` rule `{"all": true}` → APPLICABLE for everyone.
- `sbr_cco` rule `{"rbi_layer": ["middle","upper"]}`, profile `rbi_layer = base` → **NOT_APPLICABLE** (known mismatch).
- `it_form3ceb_tp` rule `{"has_international_transactions": true}`, field absent → **NEEDS_REVIEW** (missing input, not a silent No).

---

## 5. CONFIDENCE MODEL

Each result carries a confidence score in `[0,1]`. Confidence is the **minimum** across the rule's conditions, then capped by template verification status:

| Situation | Confidence |
|---|---|
| Condition on a hard field, known | 1.00 |
| Condition on a soft field, known | 0.90 |
| Numeric condition within ±10% of threshold | 0.60 (near-boundary risk) |
| Condition references a missing field | 0.40 |
| Universal (`all`) | 1.00 |
| **Cap:** template is `DRAFT_UNVERIFIED` | ≤ 0.70 |

**Rationale for the cap:** because the entire Phase-1 library ships as `DRAFT_UNVERIFIED`, the engine must never present a generated obligation as fully certain until the content team verifies the underlying template. The output therefore carries a `library_provisional: true` flag whenever any applicable/review item rests on an unverified template — the UI shows the calendar as provisional until content sign-off. This wires the `DRAFT_UNVERIFIED` content gate directly into the engine's output.

**Near-boundary example:** Profile C has `asset_size_cr = 520` against a `asset_size_min_cr: 500` threshold — within 10%, so the obligation passes but is flagged near-boundary (0.60), prompting a human to confirm the asset figure before relying on the classification. This is exactly where misclassification is most dangerous.

---

## 6. STATE EXPANSION (106 templates → 150+ effective obligations)

State-scoped obligations expand into one `company_obligation` per matching operating state. This is the concrete mechanism that takes the 106-template library past 150 effective obligations for a multi-state NBFC.

**Triggers:**
- a rule containing `pt_states` or `lwf_states` (Professional Tax, Labour Welfare Fund), or
- a template in the per-location set (`lab_shops_renewal` — Shops & Establishment is registered per establishment/state).

**Expansion logic:**
```
if decision == APPLICABLE and template is state-scoped:
    states = operating_states ∩ allowed_states   (or all operating_states for per-location)
    emit one obligation per state, id = "<template_id>__<STATE>", title suffixed "[STATE]"
```

**Verified example (Profile B, operates MH/KA/TN/DL):**
`lab_pt_deposit` → `lab_pt_deposit__MH`, `__KA`, `__TN`, `__DL` (DL not in PT-state list → excluded correctly); `lab_lwf` → expands to MH/KA/TN/DL where matched. This single profile produced **100 applicable obligations** from 106 templates precisely because of state expansion.

> **Content-team follow-on:** state expansion currently uses a single consolidated PT/LWF/S&E template per state. As the content library matures, replace these with state-specific templates (different due dates and forms per state) — the engine needs no change; only the library grows.

---

## 7. OUTPUT CONTRACT

`generate_compliance_universe(library, profile)` returns:

```json
{
  "summary": {
    "applicable": 100,
    "needs_review": 1,
    "not_applicable": 13,
    "laws_touched": 26,
    "library_provisional": true
  },
  "applicable":     [ ObligationResult, ... ],
  "needs_review":   [ ObligationResult, ... ],
  "not_applicable": [ ObligationResult, ... ]
}
```

Each `ObligationResult`:
```json
{
  "template_id": "lab_pt_deposit__MH",
  "title": "Professional Tax – Deposit & Return (State-wise) [MH]",
  "category": "labour",
  "decision": "APPLICABLE",
  "confidence": 0.9,
  "rationale": "Included because: employees = 35 >= 1; operates in ['KA','MH'] (state-scoped).",
  "missing_fields": [],
  "state": "MH",
  "template_verified": false
}
```

The full per-condition trace (`conditions[]`) is retained internally for the audit log and is available on demand, but kept out of the compact top-level payload.

### 7.1 Rationale (explainability)

Rationales are generated **deterministically** from the condition results — not by an LLM — so they are testable and auditable. The PRD's "AI explains why each obligation was included on hover" reads directly from this field. An LLM may optionally rephrase for tone, but the facts originate in the deterministic builder.

---

## 8. RE-EVALUATION & DIFF

The engine re-runs when any of these change: **profile**, **library version**, or a **template's rule/verification status**.

`diff_universe(old_applicable_ids, new_result)` returns:
```json
{ "added": [...], "removed": [...], "unchanged": [...] }
```

**Rules:**
- `added` → new `company_obligations` created; instance generator schedules due dates.
- `removed` → obligations are **deactivated** (`is_active = false`), **never deleted** — history and prior evidence are preserved (audit integrity).
- This powers the PRD's "regenerate with diff view" (e.g., NBFC reclassified base → middle: *"4 obligations added, 0 removed"*).

---

## 9. INTEGRATION

| Concern | Phase-1 approach |
|---|---|
| **Where it runs** | Onboarding service (synchronous, < 1s for 106 templates); also callable on profile edit |
| **Persistence** | Writes `company_obligations` (one row per applicable obligation/state) with `applicability_confidence` and rationale; `obligation_instances` spawned by the instance generator |
| **Human gate** | Output rendered on the review screen; APPLICABLE pre-checked, NEEDS_REVIEW surfaced with the targeted question, user confirms before persistence |
| **LLM layer** | (a) profile extraction from conversational onboarding; (b) one follow-up question per NEEDS_REVIEW field; (c) optional rationale rephrase. Never alters a decision. |
| **Audit** | Each run logged to `audit_log`: actor, timestamp, library version, profile snapshot, output summary |

---

## 10. EDGE CASES

| Case | Handling |
|---|---|
| Field not answered | `NEEDS_REVIEW` + `missing_fields` lists it; never a silent exclusion |
| Numeric value near a threshold (±10%) | APPLICABLE but confidence 0.60 + near-boundary flag → ask user to confirm the figure |
| Empty rule `{}` | Treated as universal (`all`) → APPLICABLE |
| State in rule list but org doesn't operate there | Correctly excluded from expansion (verified: DL excluded from PT) |
| Org operates in a state with no library coverage yet | No obligation emitted; logged as a coverage gap for the content team |
| Template is `DRAFT_UNVERIFIED` | Confidence capped at 0.70; `library_provisional: true`; calendar shown as provisional |
| Profile change removes applicability | Obligation deactivated, not deleted; appears in diff `removed` |
| New template added to library later | Picked up on next re-evaluation; appears in diff `added` |
| Conflicting answers (e.g., `rbi_layer: base` but `asset_size_cr: 9000`) | Engine evaluates literally; LLM layer flags the inconsistency for the user during onboarding |

---

## 11. TESTING STRATEGY

A compliance engine must be tested against **golden profiles with expected outputs**. The reference implementation ships with three:

| Profile | Shape | Verified result |
|---|---|---|
| **A — Base-layer small ICC** | base, non-deposit, ₹200cr, 35 emp, MH+KA, digital lender | 69 applicable, 1 review, 39 N/A, 22 laws |
| **B — Middle-layer with listed NCDs** | middle, nd_si, ₹3000cr, 260 emp, 4 states, listed debt, FDI, ECB | 100 applicable, 1 review, 13 N/A, 26 laws |
| **C — Incomplete profile** | middle, ₹520cr (near boundary), soft flags unanswered | 61 applicable, 27 review, 18 N/A — review queue correctly populated |

**Required test categories:**
1. **Predicate unit tests** — one per predicate type (universal, numeric-min, alias-min, state-intersection, enum, boolean, scalar) including pass/fail/missing.
2. **Decision tests** — hard-fail → N/A; missing → review; all-pass → applicable.
3. **State-expansion tests** — N states in, N (filtered) obligations out; non-matching state excluded.
4. **Confidence tests** — hard vs soft vs missing vs near-boundary vs unverified cap.
5. **Diff tests** — add/remove/unchanged on profile change.
6. **Golden-profile regression** — the three profiles above; outputs locked as fixtures so library or engine changes that shift results are caught.

> **Content-accuracy testing is separate and owned by the content team:** the engine being correct does not mean an obligation's *rule* is correct. Golden profiles test the engine; CS/CA verification tests the library.

---

## 12. PERFORMANCE & GOVERNANCE

- **Performance:** 106 templates × a handful of simple predicates = sub-millisecond per profile in pure Python; trivially scales. No optimization needed in Phase 1.
- **Determinism:** identical (profile, library version) → identical output. Required for audit and for the diff to be meaningful.
- **Versioning:** the library carries a version; every generation logs the version used, so an org's calendar is always traceable to the exact rule set that produced it.
- **The hard gate:** while the library is `DRAFT_UNVERIFIED`, all output is provisional by construction. Verification of the underlying templates — not engine work — is what lifts the calendar to production-trusted.

---

## APPENDIX — REFERENCE IMPLEMENTATION

`applicability_engine.py` (shipped alongside this spec) is the runnable reference: the full profile schema, all seven predicates, the three-state decision logic, the confidence model, state expansion, the output contract, the diff function, and the three golden profiles. It runs directly against `nbfc_obligation_library_seed.json` and reproduces every figure quoted in this document.

```
python applicability_engine.py
```

*Phase 1 only. Deterministic core; LLM-assistive, human-confirmed; wired to the DRAFT_UNVERIFIED content gate.*
