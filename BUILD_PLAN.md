# BUILD_PLAN — Regis (NBFC Compliance Platform, Phase 1)

> Status: **proposal for review.** No implementation code until this is approved.
> Scope: Phase 1 MVP per `phase1_mvp_prd.md`. Phase 2/3 features in the PRD "out of scope" list are **not** built.
> Source of truth for engine logic: the six reference `.py` files in `/Compliance docs`. They are **ported and hardened, not redesigned.**

---

## 0. What I verified before planning

I ran the references against the live seed (`nbfc_obligation_library_seed.json`, 106 obligations / 29 laws) and reproduced every quoted figure exactly:

- Profile A → **69 applicable / 1 review / 39 N/A / 22 laws**
- Profile B → **100 applicable / 1 review / 13 N/A / 26 laws**
- Profile C → **61 applicable / 27 review / 18 N/A**
- Instance generator (Profile B, FY2026-27) → **367 dated / 21 event-driven / 3 continuous / 92 working-day-adjusted**
- Clean onboarding payload → extracted profile → **99 applicable** (the PRD's "clean profile" end state)

Every one of these is a locked regression fixture below (§4). The seed ships `verification_status: DRAFT_UNVERIFIED` on **all 106** templates — the content gate is real data, not a doc footnote.

---

## 1. Backend recommendation: **Python (FastAPI) + Next.js**, not Node/Fastify

**Recommendation:** keep the PRD's Next.js 14 frontend, but run the backend in **Python (FastAPI)** so the four deterministic engines stay as the verified `.py` reference code rather than being re-implemented in TypeScript.

**Tradeoff (3 sentences).** The entire legal defensibility of this product rests on the deterministic cores — predicate evaluation, SBR-layer derivation, due-date math, confidence capping — and porting that line-by-line to TypeScript is exactly the kind of redesign that silently mis-states a regulatory deadline, so a Python backend buys us bit-for-bit parity with the proven references and regression tests that pass on day one. The cost is that we diverge from the PRD's stated Node stack and give up a single-language TS codebase plus the tightest Vercel-AI-SDK streaming integration. I judge that cost worth paying because the references *are* the product's risk surface; we still get Claude streaming via FastAPI SSE into the Next.js Copilot sidebar, and the AI calls are thin interfaces around a deterministic spine either way.

> If you'd rather hold the PRD's Node/Fastify line, say so and I'll re-plan with a TS port — but I'd then add a "differential test" milestone that runs the Python references and the TS port against the same seed and asserts identical output, because nothing else proves the port is correct.

---

## 2. Repository structure (modular monolith)

```
regis/
├─ BUILD_PLAN.md
├─ docker-compose.yml            # local: postgres + redis + minio(S3) + api + web
├─ infra/
│  └─ terraform/                 # AWS ap-south-1: RDS Postgres, ElastiCache, S3, ECS/Fargate
├─ backend/                      # Python 3.12, FastAPI, modular monolith
│  ├─ pyproject.toml
│  ├─ alembic/                   # migrations (the ~14+ tables)
│  ├─ app/
│  │  ├─ core/                   # config, db session, RLS context, auth, audit helper
│  │  ├─ engines/                # ← PORTED REFERENCE LOGIC (pure, deterministic, no I/O)
│  │  │  ├─ profile_extraction.py
│  │  │  ├─ applicability.py
│  │  │  ├─ instance_generator.py
│  │  │  ├─ document_intelligence.py
│  │  │  └─ copilot.py
│  │  ├─ ai/                     # Claude/OCR/RAG interfaces — the engines' stubbed seams
│  │  │  ├─ llm.py               # one Anthropic client; claude-sonnet for V1
│  │  │  ├─ ocr.py               # Tesseract adapter + cloud-OCR interface
│  │  │  └─ rag.py               # vector store interface (per-tenant + reg corpus)
│  │  ├─ modules/                # PRD module = router + service per bounded context
│  │  │  ├─ auth/  onboarding/  obligations/  documents/
│  │  │  ├─ legal_updates/  copilot/  dashboard/  notify/
│  │  ├─ models/                 # SQLAlchemy ORM (1:1 with migrations)
│  │  ├─ jobs/                   # background workers (instance gen, reminders, doc AI)
│  │  └─ seed/                   # seed loader for nbfc_obligation_library_seed.json
│  └─ tests/
│     ├─ golden/                 # the regression fixtures from §4 (the contract)
│     ├─ unit/                   # predicate/strategy/validator unit tests
│     └─ integration/            # full chain + API
├─ frontend/                     # Next.js 14 App Router, TS, Tailwind + shadcn/ui
│  ├─ app/(onboarding|dashboard|obligations|evidence|updates|settings)/
│  ├─ components/  lib/api/  lib/ai/   # TanStack Query; SSE client for Copilot
└─ shared/
   └─ openapi.json               # generated from FastAPI; frontend types derive from it
```

**Job runner:** the PRD specifies BullMQ-on-Redis (Node). With a Python backend I'll use **Celery or Arq on the same Redis** — identical role (nightly instance sweep, reminder scheduler, async doc processing), one less language. Flagging this as the one deliberate stack swap that follows from the backend choice.

---

## 3. Data model — ~14 PRD tables + the gates made explicit

Migrations come first (Milestone 1). Mapping to the PRD schema (§6), grouped:

| Group | Tables |
|---|---|
| Tenancy & identity | `organizations`, `entities`, `locations`, `users`, `memberships` |
| Content library (curated) | `law_library`, `obligation_templates` |
| Per-org compliance | `company_obligations`, `obligation_instances` |
| Evidence | `documents`, `document_links` |
| Legal updates | `legal_updates`, `legal_update_status` |
| System & AI | `audit_log`, `notifications`, `copilot_messages` |

That is the PRD set (16 tables; "~14"). **Additions the specs require** (small, Phase-1-scoped, called out so they're not a surprise):

- `company_profiles` — the structured 32-field profile **plus per-field provenance/confidence and the raw input** (profile-extraction spec §11 "Audit": profile origin must be reconstructable). Without it the onboarding review screen and re-extraction/diff have nowhere to live.
- `holiday_calendar` — national/RBI/state holidays for the working-day adjuster (instance-gen spec §4.1). Seeded, ops-maintained.
- `event_listeners` — registrations for the 21 event-driven obligations that are *not* pre-generated (instance-gen spec §6).
- `reg_corpus_chunks` (or external vector store metadata) — Copilot Tier-4 RAG (`regchunk:` citations). May live in the vector DB; a metadata table keeps audit/citation resolution in Postgres.

**The two hard gates, encoded in the schema (not just docs):**

1. **DRAFT_UNVERIFIED content gate.** `obligation_templates.verification_status` (`DRAFT_UNVERIFIED | VERIFIED`) and `law_library.last_reviewed_at` are columns the engines read at runtime. A template flips to `VERIFIED` only via a content-team action (its own audited mutation + role), never by app code. Until flipped, the applicability engine caps confidence at 0.70 and sets `library_provisional: true`; the Copilot caps unverified answers at 0.70 + provisional flag. This is wired through, end to end.
2. **Read-only / human-confirmed AI.** No table or endpoint lets an AI path write a terminal state. `obligation_instances.status` transitions go through the Maker-Checker service only (preparer → `ready_for_review`; admin/head → `completed`). `document_links` are written only after human link confirmation. `copilot_messages` is append-only and the Copilot has no write path at all.

**Cross-cutting (PRD §12 security baseline):** every tenant table carries `organization_id` with Postgres **RLS** set from a request-scoped session GUC; `audit_log` is **append-only** (no UPDATE/DELETE grant; enforced by trigger); **field-level encryption** for PAN/CIN/TAN; S3 SSE; all in **ap-south-1**.

---

## 4. Build order — discrete, independently testable milestones

Each milestone ends with green tests and is shippable/reviewable on its own. **M1–M4 are the mandated opening sequence** (schema → seed loader → the profile→applicability→instance chain).

### M1 — Schema + migrations + RLS + audit_log
- Alembic migrations for all tables in §3. RLS policies + session-GUC tenant scoping. Append-only `audit_log` with deletion-blocking trigger. Field-level encryption for identifiers.
- **Test:** migrations up/down clean; RLS denies cross-org reads; audit_log rejects UPDATE/DELETE; encrypted columns round-trip.

### M2 — Seed loader for `nbfc_obligation_library_seed.json`
- Idempotent loader: 29 laws → `law_library`, 106 templates → `obligation_templates`, all `verification_status=DRAFT_UNVERIFIED`. Re-runnable (upsert on `template_id`/`law_id`). Loads `holiday_calendar` seed too.
- **Test:** after load, `count(obligation_templates)=106`, `count(law_library)=29`, all DRAFT_UNVERIFIED; second run is a no-op (no dupes).

### M3 — Engine cores ported verbatim (pure, no DB)
- Port `applicability.py`, `instance_generator.py`, `profile_extraction.py`, `document_intelligence.py`, `copilot.py` into `app/engines/` as **pure functions** reading dict/JSON inputs — no DB, no I/O, AI seams stubbed. (Fix only the reference's hardcoded `/mnt/...` paths and the cross-import.)
- **Test = the golden fixtures (the contract):**
  - Applicability A/B/C → `69/1/39/22`, `100/1/13/26`, `61/27/18`.
  - Instance gen (B, FY2026-27) → `367 dated, 21 event-driven, 3 continuous, 92 working-day-adjusted`.
  - Profile extraction: clean → 99-applicable downstream; messy → states normalized, malformed CIN flagged, FDI gap (+3) ranked above intl-txn (+1), 61 applicable / 33 review composition.
  - Doc intelligence: 192 evidence strings mapped, 3 OTHER (98.4%); ITNS-281 challan vs TDS-Mar-2026 → all checks PASS; dedupe exact→block / near→warn; completeness 50% / primary_present / eligible.
  - Copilot: 10-query golden transcript — admin 18 vs preparer 13 scoping; structured conf 0.97; DNBS-02 + SBR answers 0.70 provisional; the 3 escalations produce no substantive answer.
  - Plus per-predicate, per-due_rule-type, and per-validation-check unit tests (each spec's §11–14 list).

### M4 — Persist the chain: profile → applicability → company_obligations → instances
- Onboarding service writes `company_profiles` (with provenance), runs applicability, writes `company_obligations` (with `applicability_confidence` + rationale), runs the generator, writes `obligation_instances`. `diff_universe` powers regenerate-with-diff (removed → `is_active=false`, never deleted). Audit every run with `library_version` + `generation_run_id`.
- **Test:** end-to-end on Profile B yields 100 `company_obligations` and 367 `obligation_instances` in DB; re-run is idempotent (upsert on `(company_obligation_id, period_label)`); profile edit produces correct diff.

### M5 — Auth, tenancy, onboarding API + wizard UI
- Google/Microsoft SSO + email; org/entity/location setup; 9-question profile wizard; review-and-confirm screen rendering provenance, derived-to-confirm, contradictions, and yield-ranked gap questions. **Human gate before commit.**
- **Test:** API contract tests; RBAC matrix (PRD §10) enforced; onboarding produces a populated, confirmed calendar.

### M6 — Obligation tracker + Maker-Checker + status/overdue jobs
- Tracker UI (priority queue), status state machine, Maker-Checker approval, daily overdue sweep, reminder schedule (`7/3/1` pre-due, `1/3/7` escalation; high-risk denser).
- **Test:** state-machine transitions; overdue sweep flips only qualifying instances and clears on completion; reminder derivation + no double-send.

### M7 — Evidence repository + Document Intelligence
- S3 (ap-south-1) upload, async processing job, `classify_and_extract` behind the AI seam (Tesseract + Claude), validation/dedupe/completeness (deterministic), human-confirmed linking, expiry → renewal trigger.
- **Test:** TDS-challan golden pipeline; entity-mismatch blocks link; exact/near dedupe; completeness gate feeds Maker-Checker.

### M8 — Dashboard + health score + AI narrative + PDF export
- Risk-weighted tiles, priority queue, health score, Claude narrative summary (grounded in structured counts), PDF export. Multi-entity rollup for Head/CFO.
- **Test:** health/counts computed deterministically from instances; narrative cites only real numbers.

### M9 — Legal Updates feed + summarization + applicability matcher
- Curated feed, Claude summary/impact (content-team-reviewed before publish), `affects_filter` matched to org profile, per-org review state, "review manually" default on no clean match.
- **Test:** matcher flags the right orgs; unmatched updates default to manual, never silently dropped.

### M10 — Copilot v1 (read-only RAG + structured) + eval suite
- Intent router, permission-scope-before-retrieval, bounded structured templates (no free SQL), RAG (per-tenant docs + reg corpus), grounding verifier, confidence + DRAFT_UNVERIFIED cap, escalation rules, append-only audit per turn, SSE streaming into the sidebar.
- **Test:** the golden transcript regression + grounding tests (invented-id → rejected) + escalation tests + abstention tests.

### M11 — Notifications (email/Slack) + .ics calendar export
- AWS SES/Resend email, Slack, reminder/escalation delivery, assignment + digest, `.ics` feed.
- **Test:** notification rows written; channel fan-out; idempotent send.

### M12 — Hardening + security posture + design-partner readiness
- RLS/RBAC audit, encryption verification, load check (well within sub-second engine budgets), security-questionnaire doc, ap-south-1 deployment via Terraform.
- **Test:** security regression; tenant-isolation fuzz; full golden suite green in CI.

---

## 5. Test strategy (the spine)

1. **Golden regression fixtures are the contract.** The exact numbers in §0/§4 are committed as fixtures in `backend/tests/golden/`. Any engine or library change that shifts them fails CI — that is the whole point in a regulated vertical. They run against the **real seed**, not mocks.
2. **Determinism is asserted, not assumed.** Same `(profile, library_version)` → identical applicability output; same `(company_obligations, ctx, library_version)` → identical instance set. Tests assert byte-stable output and that `generation_run_id`/`library_version` are recorded.
3. **Three layers per engine** (from each spec's testing section): predicate/strategy/validator **unit tests** → engine **golden** tests → **integration** tests through the API + DB.
4. **Gate tests.** (a) DRAFT_UNVERIFIED ⇒ confidence ≤ 0.70 + `library_provisional`/`provisional` everywhere it surfaces; (b) no AI path can write a terminal status or a link without human confirmation; (c) Copilot grounding verifier rejects any citation not in the retrieved set.
5. **Tenancy/RBAC tests.** RLS blocks cross-org; preparer-scoped Copilot returns the smaller set (13 vs 18) *by retrieval scoping*, not prose filtering.
6. **What tests do NOT cover (explicit):** whether a given obligation's *rule/due-date/evidence is legally correct* is a **content-team** task against the DRAFT_UNVERIFIED gate — the engines being correct ≠ the library being correct. Stated in every spec; honored here.

---

## 6. Open decisions for you

1. **Backend language** — approve Python/FastAPI (my rec, §1), or hold the PRD's Node/Fastify and I add a differential-test milestone.
2. **Job runner** — Celery/Arq on Redis (follows from Python) vs sticking to BullMQ (would need a small Node worker). Recommend Celery/Arq.
3. **Vector store** — Qdrant (self-host, ap-south-1, data-residency-clean) vs Pinecone (managed). Recommend Qdrant for residency posture.
4. **Auth** — Supabase Auth (fast, matches PRD's Supabase lean) vs roll-our-own SSO on FastAPI. Recommend Supabase to start.

---

**Stopping here for your review per the brief. No implementation code until you approve §1–§4.**
