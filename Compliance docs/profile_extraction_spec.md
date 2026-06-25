# Onboarding Profile Extraction — Specification (Phase 1)
## NBFC Compliance Platform

> **Component:** Onboarding Profile Extraction
> **Role:** Turns onboarding input (questionnaire answers, free text, document-extracted identifiers) into the exact structured profile the applicability engine consumes — with provenance, derivation, validation, and yield-ranked gap-filling
> **Status:** Build-ready. A working reference implementation (`profile_extraction.py`) accompanies this spec and closes the loop into the applicability engine.
> **Scope:** Phase 1 only.

---

## 1. PURPOSE & POSITION IN THE SYSTEM

This is the front door. Everything downstream — the applicability engine, the instance generator, document intelligence, the copilot — depends on one structured object: the **company profile**. This component builds that object from whatever the user gives during onboarding, and does it well enough that the calendar is accurate and the onboarding stays under the 30-minute target.

```
Onboarding input (wizard answers · free text · uploaded CoR/financials)
        │
        ▼
┌────────────────────────────────┐
│  PROFILE EXTRACTION             │  ← this spec
│  normalize → derive → validate  │
│  → provenance → gap-fill        │
└────────────────────────────────┘
        │  structured profile (exact PROFILE_FIELDS contract)
        ▼
APPLICABILITY ENGINE → INSTANCE GENERATOR → live calendar
```

**This closes the loop.** The applicability engine defines a 32-field profile contract; this component's only job is to populate that contract correctly, mark what it's confident about, and surface what it isn't. **Verified:** a clean onboarding payload extracted here produces a profile that drives the applicability engine to **99 applicable obligations** — the same end state as a hand-built profile.

**Design stance (consistent with the platform):** extraction **proposes**; the user **confirms**. Derived and low-confidence fields are pre-flagged on the review screen. Unknown fields are left `None` — and because the applicability engine already routes `None` to `NEEDS_REVIEW`, the two components compose cleanly without this layer ever *guessing* a value into the calendar.

---

## 2. INPUTS

| Input | Path | Handling |
|---|---|---|
| **Structured questionnaire** | the onboarding wizard (PRD Step 2) | direct field mapping + normalization (deterministic, exact) |
| **Free text** | conversational onboarding / pasted description | LLM extraction → questionnaire-equivalent answers → same pipeline |
| **Document signals** | uploaded CoR, financials | identifier extraction (CIN/PAN), turnover/net-worth for derivations |

The structured wizard is the primary V1 path (button-driven, low-typing). Free text and documents are enrichment routes that funnel into the **same** normalize→derive→validate pipeline, so there is one source of truth for how a profile is built.

---

## 3. THE PROFILE CONTRACT (OUTPUT)

The output must match the applicability engine's `PROFILE_FIELDS` exactly — **32 fields, 15 hard + 17 soft**. Each field is emitted with a value, a **provenance**, and a **confidence**.

| Provenance | Meaning | Confidence | Review? |
|---|---|---|---|
| `ASKED` | answered directly in the questionnaire | 0.97 | no |
| `EXTRACTED` | parsed from free text / a document by the LLM | 0.90 | confirm |
| `DERIVED` | inferred from other fields (deterministic rule) | 0.80–0.85 | confirm |
| `DEFAULT_UNKNOWN` | not provided | 0.0 | → `NEEDS_REVIEW` downstream |

Every field whose provenance is `DERIVED`/`EXTRACTED` or whose confidence < 0.85 lands on the **review list** — the user confirms it on the onboarding review screen before the calendar is committed.

---

## 4. PIPELINE

```
extract_profile(raw):
  1. identifiers   → validate CIN / PAN / GSTIN / TAN format
  2. normalize     → states→codes, amounts→₹cr, yes/no→bool, business→category
  3. derive        → rbi_layer, nbfc_category, esi, gst_scheme, csr (deterministic)
  4. soft flags    → take if provided, else DEFAULT_UNKNOWN
  5. validate      → consistency conflicts (contradiction | warning)
  6. assemble      → profile + provenance + review_fields + gap_questions + completeness
```

---

## 5. NORMALIZATION & IDENTIFIER VALIDATION

**Normalizers (deterministic):**
- **States** → ISO-style codes (`"Maharashtra, Karnataka and Tamil Nadu"` → `["KA","MH","TN"]`), unrecognized names flagged. *Verified.*
- **Amounts** → numeric ₹crore, with band awareness (`"500-1000cr"` → midpoint, flagged near-boundary). Free-text amounts (`"around 3 thousand crore"`) are the **LLM extractor's** responsibility; the deterministic parser is a conservative fallback that routes uncertain parses to review rather than trusting them.
- **Booleans** → `true/false`; `"n/a"`/`"don't know"` → `DEFAULT_UNKNOWN` (not a silent `false`).
- **Business type** → regulatory category code (`"Investment and Credit Company"` → `icc`).

**Identifier validators (regex):** CIN, PAN, GSTIN, TAN format checks. A malformed identifier raises a `warning`, not a hard block (the user may be mid-entry). **Verified:** a truncated CIN `U65999MH` correctly raised `cin fails format check`.

---

## 6. DERIVATION RULES

The wizard asks ~12–14 questions; the contract needs 32 fields. Derivation closes the gap deterministically, and every derived value is flagged `DERIVED` → confirm. Phase-1 rules:

| Derived field | Rule (simplified) | Confidence notes |
|---|---|---|
| `rbi_layer` | deposit-taking → Middle; non-deposit asset ≥ ₹1000cr → Middle; specific categories (IFC/IDF/CIC/HFC) → Middle; else Base. **Upper Layer is RBI-designated, never self-derived.** | near ₹1000cr → confidence drops, forces confirm |
| `nbfc_category` | deposit-taking → `deposit_taking`; non-deposit ≥ ₹500cr → `nd_si`; else `icc` | 0.85 |
| `esi_applicable` | `employee_count ≥ 10` | 0.80 (state-dependent — confirm) |
| `gst_scheme` | turnover ≤ ₹5cr → QRMP-eligible else regular | 0.70 (QRMP is an *election* — confirm) |
| `csr_applicable` | turnover ≥ ₹1000cr → true; else needs net worth/profit → gap question | 0.80 / leave unknown |
| `is_large_corporate` | listed debt + large balance sheet → likely | 0.60 — confirm qualified borrowing |

> **Content-team gate:** every threshold here (the ₹1000cr layer line, ESI's 10-employee trigger, CSR's s.135 tests, QRMP's ₹5cr) must be verified against the current statute/RBI direction during the content pass. These are the same `DRAFT_UNVERIFIED` semantics that run through every engine — derivations are *suggestions to confirm*, not assertions.

---

## 7. CONSISTENCY VALIDATION

After assembly, a deterministic engine cross-checks fields for contradictions:

| Check | Severity | Example |
|---|---|---|
| Deposit-taking + asserted Base Layer | `contradiction` | "deposit-taking NBFCs are Middle Layer under SBR, not Base" |
| Asserted Base + asset ≥ ₹1000cr | `contradiction` | "answered Base but asset ₹3000cr implies Middle" |
| Branches > 0 + no operating states | `warning` | incomplete footprint |
| Listed debt + equity-listing unknown | `warning` | confirm listing status |
| Asset within ±10% of ₹1000cr line | `warning` | "near the layer boundary; confirm exact figure" |

Contradictions surface prominently on the review screen; the user resolves them before the calendar commits. This catches the most damaging onboarding error — a misclassified layer, which would generate the wrong obligation set entirely.

---

## 8. GAP HANDLING — ASK ONLY WHAT CHANGES THE CALENDAR

Unknown fields are not all equal. A field that gates one rarely-triggered obligation is low-value to ask; a field that gates many is high-value. The gap generator computes each field's **yield** (how many obligations it gates, read directly from the live library) and asks the **highest-impact questions first**.

```
gap_questions(profile, library):
   for each unknown field that has a targeted question:
       yield = how many obligations this field gates (from the library)
   rank by (hard_field, yield) descending
```

**Verified ranking** (messy Case 2): the generator surfaced *"Do you have any foreign investment (FDI)?"* (+3 obligations) ahead of *"transactions with overseas associated enterprises?"* (+1) — high-impact first. Fields with no targeted question flow silently to `NEEDS_REVIEW`.

**Composition with the applicability engine:** any field left unanswered after gap-filling is `None` → the engine routes its obligations to `NEEDS_REVIEW` → they appear on the same review screen the user already confirms. The two components compose without this layer guessing. **Verified:** the partial Case-2 profile produced **61 applicable + 33 needs-review** — the 33 are exactly the consequences of the unanswered gaps, correctly surfaced rather than silently decided.

---

## 9. THE LLM LAYER (bounded, human-confirmed)

The deterministic core above handles structured input exactly. The LLM sits **above** it for three jobs, none of which override a deterministic value:

1. **Free-text → answers** — turn *"we're a non-deposit ICC, ~₹3000cr AUM, listed NCDs, operate in MH/KA, some FDI"* into questionnaire-equivalent answers, which then flow through the same normalize→derive→validate pipeline (and are tagged `EXTRACTED` → confirm).
2. **Conversational onboarding** — ask the yield-ranked gap questions one at a time in natural language; map answers back to fields.
3. **Explanations** — phrase the "why" for derived fields ("we set you to Middle Layer because…") for the review screen.

The LLM never writes a field directly into the engine profile without it passing through normalization, validation, and the confidence/provenance tagging — so an LLM misread surfaces as a low-confidence, confirmable field, not a silent calendar error.

---

## 10. REVIEW & CONFIRMATION (HUMAN GATE)

The onboarding review screen (PRD Step 4) renders the extraction output:
- **Confirmed (ASKED, high-confidence)** — shown, editable.
- **Derived / extracted (confirm)** — pre-filled, visually flagged, with the derivation reason.
- **Contradictions** — surfaced at the top, must be resolved.
- **Gap questions** — the yield-ranked follow-ups, asked inline.

Only after the user confirms does the profile commit and the applicability engine + instance generator run. This is the human gate that makes AI-assisted onboarding safe: the system does the work; the qualified user signs off.

---

## 11. AUDIT & ARCHITECTURE

| Concern | Phase-1 approach |
|---|---|
| **Audit** | persist the raw input, the extracted profile, per-field provenance + confidence, validation issues, and the user's confirmations/edits — the profile's origin is fully reconstructable |
| **Runtime** | synchronous; < 1s deterministic; the LLM free-text/conversational path streams |
| **LLM** | Claude for free-text extraction, conversational gap-asking, and explanations (strict-JSON field output) |
| **Persistence** | writes the org/entity profile fields consumed by the applicability engine; provenance stored for the review screen and audit |
| **Re-extraction** | a profile edit re-runs derive→validate and triggers the applicability engine's re-evaluation + diff (the "regenerate with diff" flow) |

---

## 12. EDGE CASES

| Case | Handling |
|---|---|
| Free-text/messy amounts | LLM extraction primary; deterministic fallback routes uncertain parses to review (never trusts a shaky number) |
| Contradictory answers (Base + ₹3000cr) | `contradiction` raised; user resolves before commit |
| Unrecognized state name | flagged in normalization note; user corrects |
| Malformed identifier | `warning`, not block (mid-entry tolerance) |
| Upper-Layer NBFC | never self-derived; requires explicit confirmation (RBI-designated) |
| Near-threshold asset size | confidence lowered + boundary warning → confirm exact figure |
| User answers "don't know" | `DEFAULT_UNKNOWN` → gap question or `NEEDS_REVIEW`, never coerced to false |
| Sparse profile | extraction still produces a valid (partial) profile; gaps ranked; engine surfaces the rest as review |
| Profile edit post-onboarding | re-extract → re-evaluate → diff view |

---

## 13. TESTING STRATEGY

| Test class | What it locks down |
|---|---|
| **Normalizer tests** | states/amounts/bools/business mapping incl. messy inputs |
| **Identifier tests** | CIN/PAN/GSTIN/TAN format pass/fail |
| **Derivation tests** | SBR layer (incl. boundary), category, ESI, GST scheme, CSR — exact outputs + confidence |
| **Consistency tests** | each contradiction/warning fires on the right input |
| **Gap-ranking tests** | yield computed from the live library; high-impact questions ranked first (verified FDI +3 before intl-txn +1) |
| **Provenance tests** | every field tagged correctly; review list = derived ∪ low-confidence ∪ unknown |
| **Loop-closure regression** | clean payload → **99 applicable**; messy payload → **61 applicable / 33 review** — locked as fixtures |

> As elsewhere: these tests prove the extractor builds the profile correctly. Whether a derivation *threshold* is legally current remains a content-team item against the `DRAFT_UNVERIFIED` gate — which is exactly why derived fields are confidence-flagged and user-confirmed.

---

## APPENDIX — REFERENCE IMPLEMENTATION

`profile_extraction.py` (shipped with this spec) implements the deterministic core: normalization (states/amounts/bools/business), identifier validation, the SBR-and-statutory derivation rules, the consistency engine, provenance/confidence tagging, and the yield-ranked gap-question generator. The LLM free-text/conversational layer is behind a clean interface (stubbed). It runs against the live library and **closes the loop into the applicability engine**.

```
python profile_extraction.py
```

Verified output:
```
CASE 1 (clean)  → profile built; derived layer=middle, category=nd_si, esi=True
                → applicability: 99 applicable, 8 review, 7 N/A
CASE 2 (messy)  → states normalized; malformed CIN flagged; gap questions yield-ranked
                → applicability: 61 applicable, 33 review, 18 N/A
Loop closed: raw onboarding input → structured profile → obligation universe.
```

*Phase 1 only. Deterministic core; LLM-assistive and human-confirmed; unknowns flow to NEEDS_REVIEW by composition with the applicability engine; wired to the same DRAFT_UNVERIFIED content gate. This component closes the Phase-1 AI loop.*
