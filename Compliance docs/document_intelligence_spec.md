# Document Intelligence Engine — Specification (Phase 1)
## NBFC Compliance Platform

> **Component:** Document Intelligence (Evidence Repository AI)
> **Role:** Classifies, parses, validates, de-duplicates, and links uploaded compliance documents to the obligation instances they evidence; tracks evidence completeness
> **Status:** Build-ready. A working reference implementation (`document_intelligence.py`) accompanies this spec, grounded in the live 106-obligation library.
> **Scope:** Phase 1 only.

---

## 1. PURPOSE & POSITION IN THE SYSTEM

The instance generator produces dated obligations; this component handles the **proof** that each one was met. A compliance officer uploads a challan, an acknowledgment, a certificate, or board minutes; the engine works out *what the document is*, *what it says*, *which obligation instance it evidences*, and *whether that instance now has complete evidence* — then proposes the link for human confirmation.

```
obligation_instances  (dated, awaiting evidence)
        ▲
        │  document_links (suggested, human-confirmed)
┌──────────────────────────────┐
│  DOCUMENT INTELLIGENCE         │  ← this spec
│  classify → parse → validate   │
│  → dedupe → link → completeness│
└──────────────────────────────┘
        ▲
        │ upload (PDF / image / office doc)
   Compliance officer / preparer / smart inbox
```

**Maps to PRD:** the Evidence Repository module and *AI Capability 3 — Document Intelligence*. It writes the `documents` and `document_links` tables and feeds the Maker-Checker completion gate.

**Design stance:** the AI **suggests** the document type and the instance link; the **human confirms**. The engine never auto-marks an obligation complete — the Maker-Checker flow in the instance state machine is unchanged. Classification and extraction are AI (OCR + LLM); validation, de-duplication, and completeness are **deterministic and auditable**.

---

## 2. DOCUMENT TYPES (TAXONOMY)

The library's 106 obligations reference **192 evidence items** (188 distinct). These collapse to **11 canonical document types** + an `OTHER` fallback. The taxonomy is grounded in the real evidence corpus — verified to classify **98.4%** of evidence strings into a specific type (3 contract-like items legitimately fall to `OTHER`).

| Canonical type | What it is | Share of evidence corpus | Examples |
|---|---|---|---|
| `FILING_ACK` | Proof a return/form was filed | **52** (largest) | CIMS ack, ROC SRN, ITR-V, GSTR ack, FIU ack, FC-GPR ack, exchange receipt |
| `COMPUTATION_RECON` | Working / reconciliation | 21 | NOF/CRAR/LCR computation, ITC reco, 2B-vs-books, TP study, GSTR-9C |
| `REGISTER_MIS_LOG` | Standing register / log / MIS | 20 | Statutory registers, KYC identifier register, DLG register, SDD logs |
| `BOARD_SECRETARIAL` | Meeting/resolution artifacts | 20 | Minutes, notices, resolutions, MBP-1, DIR-8, attendance |
| `STATUTORY_CERTIFICATE` | Certificate signed by an authority/professional | 18 | SAC, FIRC, Form 16/16A, 3CD, 3CEB, MR-3, asset-cover, valuation |
| `RETURN_STATEMENT_FILE` | The return/statement file itself | 13 | ALM statement, FVU file, CRILC file, contribution statement, filed results |
| `PAYMENT_CHALLAN` | Tax/contribution payment proof | 11 | ITNS-281, TRRN, ESI/PT/LWF challan, PMT-06, advance-tax challan |
| `AUDITED_REPORT` | Audited/assurance report | 10 | Audited financials, IS audit, RBIA, BCP/DR test, actuarial valuation |
| `POLICY_DOC` | Board-approved policy | 9 | KYC/AML, FPC, interest-rate, outsourcing, IT/IS, code of conduct |
| `LICENSE_REGISTRATION` | Licence/registration/appointment | 8 | S&E certificate, CERSAI registration, CKYC, CCO/GRO appointment |
| `INTERNAL_NOTE` | Internal note/declaration | 7 | Suspicion note, BEN-1 declaration, due-diligence records |
| `OTHER` | Fallback | 3 | LSP agreements, insurance proof — routed to manual classification |

The evidence-to-type mapping is maintained as keyword rules ordered specific→general (see reference `TYPE_RULES`). New evidence phrasing added to the library is auto-classified; unmatched items surface as `OTHER` for taxonomy review.

---

## 3. EXTRACTION SCHEMA

Extraction output is stored in `documents.ai_extracted` (jsonb). The schema is **common fields + type-specific fields**.

**Common fields (every document):**
`document_date`, `period`, `reference_number`, `authority`, `entity_identifier`.

**Type-specific overlays (selected):**

| Type | Additional fields |
|---|---|
| `PAYMENT_CHALLAN` | `challan_number`, `bsr_code`, `payment_date`, `amount`, `assessment_year`, `tan_or_pan` |
| `FILING_ACK` | `srn_or_ack_no`, `form_number`, `filing_date`, `cin_or_gstin` |
| `RETURN_STATEMENT_FILE` | `return_type`, `return_period`, `gstin_or_tan`, `token_number` |
| `STATUTORY_CERTIFICATE` | `issuer`, `issue_date`, `valid_until`, `subject` |
| `LICENSE_REGISTRATION` | `license_number`, `issuing_authority`, `valid_from`, `valid_until` |
| `BOARD_SECRETARIAL` | `meeting_date`, `resolution_type`, `form_number` |
| `AUDITED_REPORT` | `report_period`, `auditor_name`, `sign_date` |
| `POLICY_DOC` | `approval_date`, `next_review_date`, `version` |

Each extracted field carries `{ value, confidence, source_span }`; `confidence` drives review routing (§6), and `valid_until` on a `LICENSE_REGISTRATION` / `STATUTORY_CERTIFICATE` is written to `documents.expiry_date` and triggers a renewal instance (links back to the generator's `license_renewal` rule).

> **Schema note:** this extends the PRD `ai_extracted` jsonb (`{dates, amounts, reference_numbers}`) into a typed, per-field structure. Backward compatible — the legacy arrays are derivable from the typed fields.

---

## 4. OCR & PARSING PIPELINE

```
Upload → S3 (encrypted)                      [sync: returns immediately]
   │
   └─► enqueue processing job (BullMQ)        [async: UI shows "Processing"]
          │
          1. MIME / integrity check  (reject corrupt, oversized, non-allowed)
          2. Document-kind routing:
               • text-PDF        → direct text + layout extraction
               • scanned PDF/img → rasterize → OCR
               • office (xlsx/docx) → native text extraction
          3. OCR (scanned only): Tesseract (Phase-1 default) or cloud OCR
               → page text + per-block OCR confidence
          4. Classification (LLM): text + layout → DocType + confidence
          5. Extraction (LLM): structured JSON to the §3 schema for that type
          6. Validation (deterministic, §7)
          7. Duplicate detection (deterministic, §8)
          8. Persist documents row + suggest document_link
          9. Recompute completeness for the target instance (§9)
```

**Pipeline rules:**
- **Allowed inputs (V1):** PDF, JPG/PNG, XLSX/DOCX. Max size configurable (e.g., 25 MB). Others rejected with a clear message.
- **Text vs scanned:** if a PDF yields sufficient embedded text, skip OCR (faster, more accurate). OCR only when needed.
- **OCR quality gate:** if mean OCR confidence < threshold, mark the document `low_ocr_quality` and route to manual review rather than trusting extraction.
- **Language:** English primary. Devanagari/regional OCR is flagged as a known limitation for V1 — documents detected as non-Latin route to manual.
- **Multi-page:** classification uses the whole document; extraction targets the page(s) with the relevant fields (e.g., the challan page in a bundle).
- **Async, non-blocking:** upload returns instantly; results stream in. The user is never blocked waiting for the model.

**AI interface (stub in reference):** `classify_and_extract(file_bytes, mime, hint)` → `{doc_type, classification_confidence, fields:{...}}`. The `hint` carries the instance the user uploaded against (if any), improving classification and giving extraction a target period/form.

---

## 5. CLASSIFICATION & ENTITY EXTRACTION

**Classification:** LLM assigns one `DocType` with a confidence score, using document text + layout signals (a challan looks different from minutes). The instance `hint` biases the prior (uploading against a TDS instance makes `PAYMENT_CHALLAN`/`FILING_ACK` more likely) but never forces it — a mismatch is itself a useful signal (§7).

**Entity extraction:** LLM returns the typed schema for the classified type. Entities of interest across NBFC documents:
- **Dates** — document/filing/payment date, period, validity dates
- **Reference numbers** — SRN, ARN, TRRN, challan/CIN, token/RRR, acknowledgment no.
- **Identifiers** — CIN, PAN, TAN, GSTIN (cross-checked against org master, §7.4)
- **Amounts** — tax/contribution paid
- **Parties** — deductee, counterparty, vendor, auditor
- **Form/return number** — 24Q, AOC-4, FC-GPR, GSTR-3B
- **Authority** — RBI, MCA, GSTN, EPFO, SEBI, FIU-IND

Extraction prompts demand strict JSON to the schema; the engine parses and validates structure before use. Low-confidence fields are surfaced for human correction rather than silently trusted.

---

## 6. CONFIDENCE MODEL & ROUTING

Two confidence signals: **classification confidence** (which DocType) and **per-field extraction confidence**. The document's overall confidence gates how it is presented.

| Overall confidence | Route | UX |
|---|---|---|
| ≥ 0.85 | `AUTO_SUGGEST` | Link to the hinted instance is **pre-checked**; type pre-filled; user confirms with one tap |
| 0.60 – 0.85 | `SUGGEST_REVIEW` | Type + link surfaced as a suggestion; user must actively confirm both |
| < 0.60 | `MANUAL` | User classifies and links manually; extraction shown as best-effort hints |

Low-confidence individual fields are flagged inline ("verify amount") even when overall confidence is high. **The human always confirms the link** before it is persisted and before the instance can be completed — confidence only changes how much typing the user saves.

---

## 7. VALIDATION ENGINE (deterministic)

After extraction, the engine cross-checks the document against the **target instance**, its **template**, and the **org master**. Each check returns `pass | warn | fail`. Validation informs the user and gates completion eligibility; it never silently rejects or auto-completes.

| Check | Logic | On failure |
|---|---|---|
| **period_match** | extracted `period` aligns with `instance.period_label` (normalized; quarter/month token overlap) | `warn` — likely wrong period; flag prominently |
| **date_in_window** | filing/payment date ≤ `due_date` + grace, and within the obligation period | `fail` — document may not evidence this instance |
| **form_match** | extracted `form_number` ⊇/⊆ `template.form_reference` | `warn` — possible wrong document |
| **entity_match** | extracted CIN/TAN/PAN/GSTIN ∈ org master identifiers | `fail` — document belongs to another entity |
| **amount_sanity** | amount > 0 (and within expected magnitude band, optional) | `fail` — extraction or document error |
| **expiry_capture** | `valid_until` present → write `expiry_date`, schedule renewal | n/a (informational) |

**Verified scenario (reference run):** an ITNS-281 challan extracted as `{period: "Mar 2026", payment_date: 2026-04-07, amount: 245000, tan: MUMT01234A}` validated against the *TDS-deposit, March 2026* instance (due 2026-04-30) returned **PASS** on period_match, date_in_window, entity_match, and amount_sanity — i.e., a confident auto-suggested link.

---

## 8. DUPLICATE DETECTION

Two layers, because the same evidence is often re-uploaded (re-saved scans differ byte-for-byte).

| Layer | Method | Verdict / action |
|---|---|---|
| **Exact** | SHA-256 of file bytes vs existing documents | `EXACT_DUPLICATE` → **block** (offer to link the existing doc instead) |
| **Near** | key tuple `(entity_id, form_number, period, reference_number)` matches an existing doc | `NEAR_DUPLICATE` → **warn**, allow override with reason |
| (else) | — | `UNIQUE` → accept |

The near-duplicate tuple fires only when fully populated (avoids false positives on sparse extractions). **Verified:** identical bytes → `EXACT_DUPLICATE/block`; different bytes but same entity+form+period+reference → `NEAR_DUPLICATE/warn`.

> A future content-similarity layer (text MinHash / perceptual hash for scans) is noted but **out of Phase-1 scope**; exact + key-tuple covers the common re-upload cases.

---

## 9. EVIDENCE-COMPLETENESS CHECKS

Each obligation's `required_evidence` (from the library) defines what "fully evidenced" means. The checker maps required items to canonical types, then compares against the doc types linked to the instance.

**Output:** `required[]`, `covered[]`, `missing[]`, `pct`, `primary_present`, `eligible_for_completion`.

- **Primary evidence** = the first required item (typically the filing ack or challan). The Maker-Checker completion gate requires at least the primary evidence present (configurable to require *all* required types).
- Partial completeness is shown in the UI ("50% — challan linked, TDS computation outstanding").

**Verified scenario:** for `it_tds_deposit` (required: *Challan (ITNS-281)* → `PAYMENT_CHALLAN`; *TDS computation* → `COMPUTATION_RECON`), with only the challan linked → **50% covered, primary_present=true, eligible_for_completion=true**, and `missing = [TDS computation]` surfaced. The Checker can approve (primary present) but sees the outstanding item.

---

## 10. LINKING WORKFLOW

```
Upload (optionally against a specific instance)
   → classify + extract + validate + dedupe
   → IF AUTO_SUGGEST: pre-checked link to hinted/best-match instance
     ELSE: ranked instance suggestions (by period + form + owner)
   → user confirms link  → write document_links  → recompute completeness
   → instance evidence state updated (does NOT auto-complete)
```

**Smart inbox (PRD):** documents emailed to a per-org address enter the same pipeline with no instance hint; the engine proposes the best-matching instance from period + form + entity. **Unlinked evidence** is a valid resting state — a document can live in the repository without a link until matched.

---

## 11. AUDIT TRAIL

Every action writes to the append-only `audit_log`. The document trail is itself compliance evidence and must be defensible.

| Event | Logged |
|---|---|
| Upload | actor, file_name, sha256, mime, size, timestamp |
| Classification | doc_type, confidence, model_version |
| Extraction | extracted field set, per-field confidence, model_version |
| Validation | each check result (pass/warn/fail) |
| Duplicate decision | verdict, matched doc id, override reason (if any) |
| Link confirmed/changed | actor, instance_id, prior/new link |
| Completeness change | instance_id, pct before→after, eligibility flip |

**Determinism for audit:** validation, dedupe, and completeness are pure functions of their inputs — re-runnable and reproducible. Classification/extraction record the `model_version` so an AI suggestion is always traceable to the model that produced it.

---

## 12. ARCHITECTURE

| Concern | Phase-1 approach |
|---|---|
| **Storage** | S3 (ap-south-1), server-side encryption; documents row holds metadata + `ai_extracted` |
| **Processing** | BullMQ async job; upload non-blocking; UI shows processing → results |
| **OCR** | Tesseract (default) with a cloud-OCR adapter interface for harder scans |
| **LLM** | Claude for classification + structured extraction (strict-JSON prompts) |
| **Cost control** | skip OCR for text-PDFs; cache by content hash; batch where possible |
| **Failure handling** | OCR/LLM failure → document saved as `unprocessed`, routed to manual; never blocks the upload or other documents |
| **Security** | tenant-isolated S3 prefixes + RLS on documents; signed URLs; field-level encryption for identifiers (PAN/CIN) |

---

## 13. EDGE CASES

| Case | Handling |
|---|---|
| Scanned/low-quality image | OCR confidence gate → `low_ocr_quality` → manual review |
| Document bundle (many docs in one PDF) | Classify per logical section; suggest multiple links; allow split |
| Right document, wrong instance hint | Classification proceeds on content; period/form mismatch raises `warn`; engine re-suggests correct instance |
| Document for a different entity | `entity_match` = `fail`; link blocked pending user override |
| Re-upload of same evidence | Exact → blocked with link-to-existing; near → warn |
| Evidence with no matching instance | Stored as **unlinked evidence**; logged as a possible coverage gap |
| Expiry-bearing certificate/licence | `valid_until` captured → `expiry_date` set → renewal instance scheduled |
| Non-English document | Detected → manual route (regional OCR is Phase-2) |
| Wrong document type but high OCR text | Classification confidence governs; low confidence → `MANUAL` |
| Period spans (annual return covering FY) | period normalizer matches `FY2026` / `2026-27` / quarter tokens |

---

## 14. TESTING STRATEGY

| Test class | What it locks down |
|---|---|
| **Taxonomy coverage** | Every `required_evidence` string maps to a type; `OTHER` rate stays low (currently 3/192). Regression-locked. |
| **Classification fixtures** | Labeled sample docs per type → expected `DocType` + confidence band |
| **Extraction fixtures** | Sample docs → expected field values (golden extractions) |
| **Validation unit tests** | Each check: pass/warn/fail cases incl. period normalization, date window, entity match |
| **Dedupe tests** | Exact (same bytes) → block; near (same key tuple) → warn; sparse tuple → no false positive |
| **Completeness tests** | required→covered→missing math; primary-present gate; full-required mode |
| **Pipeline integration** | Upload → classify → validate → dedupe → link → completeness on the TDS-challan golden scenario |

> As with the other engines: these tests prove the engine processes documents correctly. Whether a given `required_evidence` definition is *legally* sufficient remains a content-team item against the `DRAFT_UNVERIFIED` gate.

---

## APPENDIX — REFERENCE IMPLEMENTATION

`document_intelligence.py` (shipped with this spec) implements the deterministic core: the canonical taxonomy + evidence mapping (verified across all 192 evidence strings), the extraction schema, the confidence-routing thresholds, the validation engine, exact + key-tuple duplicate detection, and the completeness checker. OCR + LLM classification/extraction are behind the `classify_and_extract` interface (stubbed). It runs against the live seed and reproduces every figure in this document.

```
python document_intelligence.py
```

Verified output (selected):
```
Evidence strings mapped: 192   OTHER: 3 (98.4% typed)
TDS challan vs Mar-2026 instance: period/date/entity/amount → PASS
Classification PAYMENT_CHALLAN @0.93 → AUTO_SUGGEST
Completeness (challan only): 50%, primary_present=True, eligible_for_completion=True
Dedupe: exact→block, near→warn
```

*Phase 1 only. AI suggests (classification/extraction); humans confirm. Validation, de-duplication, and completeness are deterministic and audit-logged; wired to the same Maker-Checker gate and DRAFT_UNVERIFIED content gate.*
