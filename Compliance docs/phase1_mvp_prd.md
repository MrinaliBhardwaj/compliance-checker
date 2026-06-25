# Product Requirements Document — Phase 1 MVP
## AI-Native Compliance Platform for Indian NBFCs

> **Scope:** Phase 1 only (Months 1–6)
> **Objective:** Ship a focused, AI-assisted compliance platform that delivers value in under 30 minutes and proves product-market fit with 20 paying NBFC customers.
> **Working product name:** *Regis* (placeholder)
> **Status:** Build-ready blueprint
> **Date:** June 2026

---

## 0. THE ONE-LINE PRODUCT THESIS

> An NBFC compliance officer signs up, answers a short profile questionnaire, and within 30 minutes has a complete, accurate compliance calendar with owners assigned, deadlines tracked, evidence repository ready, and an AI copilot that answers "what's due, what changed, what's at risk" — replacing weeks of manual setup and spreadsheet management.

Everything in this document serves that thesis. If a feature does not directly support time-to-value, daily usability, or compliance accuracy, it is out of Phase 1.

---

## 1. CORE PRODUCT SCOPE

### 1.1 In Scope (V1)

| # | Capability | Why it's in V1 |
|---|---|---|
| 1 | Self-serve signup + AI-guided onboarding | The core differentiator; drives time-to-value |
| 2 | AI compliance calendar generation (from company profile) | The "aha" moment; replaces weeks of manual setup |
| 3 | Compliance obligation tracker (recurring + one-time) | The daily-use core loop |
| 4 | Evidence document repository with AI auto-tagging | Audit trail + reduces manual filing |
| 5 | Real-time legal updates feed (NBFC priority laws, AI-summarized) | Keeps the calendar current; high perceived value |
| 6 | Compliance dashboard (status, overdue, due-soon, health score) | Oversight layer for heads/CFOs |
| 7 | Compliance Copilot v1 (read-only Q&A over their data + reg knowledge) | Differentiation; low-risk AI |
| 8 | Notifications: email + Slack | Drives engagement; reduces missed deadlines |
| 9 | Role-based access (3 roles) | Required for team adoption |
| 10 | Multi-entity support (basic) | NBFC groups often have 2–3 entities; cheap to model now |

### 1.2 Explicitly Out of Scope (V1)

These are deferred to later phases. Listing them prevents scope creep.

| Excluded | Reason for exclusion in V1 |
|---|---|
| Contract / Litigation / Audit / IFC / ERM modules | Breadth before depth kills time-to-value; NBFC compliance calendar is the wedge |
| Autonomous agents that *take actions* (file, submit, send externally) | Legal risk + trust; V1 AI is assistive and read-only |
| AI drafting of legal notice responses / board resolutions | Accuracy and liability risk too high for MVP |
| Government portal integrations (RBI COSMOS, MCA21, GSTN write/verify) | No public APIs; high effort, low V1 ROI |
| Native mobile app | Responsive web is sufficient for V1; mobile is Phase 2 |
| Predictive ML risk scoring / benchmarking | Requires data scale we won't have yet |
| Public API / white-label / consulting multi-tenant portal | Not needed for first 20 direct customers |
| International / multi-jurisdiction compliance | India NBFC only |
| Custom workflow builder, custom frameworks | Configurability is a Phase 2+ enterprise need |

### 1.3 Scope Guardrail

**The V1 build rule:** if a request requires the AI to *act on the user's behalf in the external world* (file a return, send a response to a regulator, submit a form), it is out. V1 AI only **reads, generates internal content, classifies, summarizes, and answers**. A human always acts.

---

## 2. PRIMARY ICP — NON-BANKING FINANCIAL COMPANIES (NBFCs)

### 2.1 The Pick

**Middle-Layer and Base-Layer NBFCs under RBI's Scale-Based Regulation (SBR)** — asset size roughly ₹500 Cr to ₹5,000 Cr, typically 50–500 employees, with a dedicated compliance function but limited compliance-tech tooling.

### 2.2 Why NBFCs (Justification)

| Factor | Why NBFC wins as the V1 wedge |
|---|---|
| **Regulatory intensity** | RBI regulates NBFCs tightly: periodic returns (DNBS), KYC/AML, fair practices code, SBR-tier obligations, statutory auditor requirements. High volume of recurring, deadline-driven compliance — exactly what a calendar+tracker solves. |
| **Bounded compliance universe** | Unlike pharma (multi-state factory acts, pollution, drug licenses across geographies), NBFC compliance is more centralized under RBI + Companies Act + tax. This makes the **content library buildable in 6 months** — critical for MVP. |
| **Mandated compliance roles** | RBI requires designated compliance officers / principal officers for certain NBFC layers. The buyer and daily user **already exist as a defined role** — no need to create the category. |
| **Acute, quantifiable pain** | RBI penalties, supervisory action, and license risk are severe and well understood. Compliance heads have budget and urgency. |
| **Concentrated, reachable community** | NBFCs cluster in identifiable networks (FIDC, sector events, RBI circular watchers). Sellable without a large sales team. |
| **Willingness to pay** | Regulated financial entities buy compliance tooling readily; ACV supports the pricing tiers. |
| **Recurring obligations = sticky product** | Monthly/quarterly RBI returns mean the product is used continuously, not seasonally. Drives retention and habit. |

### 2.3 Anti-personas (who we do NOT build for in V1)

- Large banks / Upper-Layer NBFCs (procurement-heavy, need enterprise features we don't have yet)
- Tiny unregistered lenders / fintech startups without a compliance function (no buyer, no budget)
- Non-financial SMBs (different compliance universe; dilutes content focus)

---

## 3. USER PERSONAS & WORKFLOWS

### 3.1 Persona A — Compliance Officer / Company Secretary (PRIMARY, daily user)

**Profile:** Qualified CS or compliance professional. Owns the day-to-day compliance calendar for the NBFC. Manages 80–300 recurring obligations across RBI, Companies Act, tax, and labour. Lives in spreadsheets and email today.

**Jobs to be done:**
- Know what is due this week and who owns it
- Ensure evidence is collected and filed for each completed obligation
- Stay current on RBI circulars and law changes
- Produce status for their Compliance Head on demand

**Exact daily workflow (current vs. V1):**

| Step | Today (spreadsheet) | With V1 |
|---|---|---|
| 1. Check what's due | Open Excel, scan dates manually | Open dashboard → "Due this week" surfaces automatically |
| 2. Follow up with owners | Manual email to each preparer | One-click reminder; Slack/email auto-nudge |
| 3. Collect evidence | Email attachments, save to shared drive | Owner uploads to the obligation; AI tags it |
| 4. Mark complete | Update Excel cell color | Mark complete; status + audit log auto-recorded |
| 5. Check law changes | Read RBI website / circular emails | Legal Updates feed, AI-summarized, flagged "affects you" |
| 6. Report to head | Build a manual summary | Dashboard is the report; export PDF |

### 3.2 Persona B — Compliance Head / CFO (oversight, weekly user)

**Profile:** Carries regulatory liability. Doesn't manage tasks daily. Needs confidence and board-ready visibility.

**Jobs to be done:** See overall compliance health, spot at-risk items, get an evidence trail for auditors/RBI inspection, review what changed.

**Weekly workflow:**
1. Open dashboard → read AI health summary ("87% on-track; 3 items at risk this week")
2. Drill into overdue / at-risk items
3. Ask Copilot: "Show me everything overdue across both entities"
4. Export a compliance status PDF before a board/audit committee meeting

### 3.3 Persona C — Preparer / Maker (junior, task-level user)

**Profile:** Finance/ops team member who actually prepares a return or gathers a document. Limited platform access.

**Jobs to be done:** See assigned tasks, upload evidence, mark ready for review.

**Workflow:**
1. Receive notification (email/Slack) of an assigned obligation
2. Open the task → see what's required + reference to the law
3. Upload the prepared document/proof
4. Mark "Ready for review" → routes to Compliance Officer

> **Note:** V1 has a simple **Maker → Checker** flow (Preparer submits, Compliance Officer approves). No multi-level approval chains in V1.

---

## 4. ONBOARDING FLOW (STEP BY STEP)

**Goal: account created → live compliance calendar in under 30 minutes.**

### Step 0 — Signup (2 min)
- Email + password, or Google / Microsoft SSO
- No credit card, no demo call (14-day free trial)
- Email verification

### Step 1 — Organization setup (2 min)
- Organization name
- Number of legal entities (1–3 in V1)
- For each entity: legal name, CIN, NBFC registration number (CoR), PAN

### Step 2 — Compliance profile questionnaire (5–7 min)
The AI uses these answers to generate the applicable obligation set. Structured, button-driven (low typing):
- NBFC type (Investment & Credit / Infrastructure / Microfinance / Factor / others)
- RBI layer under SBR (Base / Middle Layer)
- Asset size band
- Deposit-taking or non-deposit-taking
- Listed or unlisted
- States of operation (for state-level labour/professional tax)
- Number of branches
- Does it have foreign investment (FEMA applicability)?
- Statutory auditor appointed? (Y/N)

### Step 3 — AI generates the compliance universe (1–2 min, with progress UI)
- AI maps the profile to the curated NBFC obligation library
- Generates the applicable obligations, each with: governing law, frequency, due dates, and a short description
- Output screen: **"Based on your profile, we identified 142 applicable compliance obligations across 18 laws. Here is your compliance calendar."**
- Each obligation shows a confidence indicator; user can mark any as "Not applicable" with one click (this feedback also improves the library)

### Step 4 — Review & confirm (5 min)
- User reviews the generated calendar, grouped by law / frequency
- Bulk-accept or selectively deselect
- AI explains *why* each obligation was included on hover ("Included because: Middle-Layer NBFC + non-deposit-taking")

### Step 5 — Invite team & assign owners (3 min)
- Invite Compliance Head and Preparers by email
- AI suggests default owner assignments by role
- Set the primary compliance officer as default approver

### Step 6 — Connect notifications (2 min)
- Connect Slack (optional) and confirm email notification preferences
- Set reminder lead times (default: 7 days, 3 days, 1 day before due)

### Step 7 — First value moment (instant)
- Land on dashboard → **"3 obligations are due this week"** shown immediately
- Copilot prompt suggestion appears: *"Ask me what's due this month"*

**Onboarding success = user reaches a populated dashboard with at least one real upcoming deadline visible.**

---

## 5. CORE MODULES FOR V1

| Module | Description | Primary persona |
|---|---|---|
| **Onboarding & Profile** | Profile questionnaire + AI calendar generation + entity/team setup | Compliance Officer |
| **Compliance Calendar & Tracker** | The core: recurring + one-time obligations, due dates, owners, status, Maker-Checker | Compliance Officer, Preparer |
| **Evidence Repository** | Document upload, AI auto-tagging, link to obligations, expiry detection | Compliance Officer, Preparer |
| **Legal Updates Feed** | Curated NBFC-relevant regulatory changes, AI-summarized, applicability flag | Compliance Officer, Head |
| **Dashboard & Reporting** | Health score, overdue/at-risk, due-soon, AI narrative summary, PDF export | Head / CFO |
| **Compliance Copilot** | Read-only natural-language Q&A over the org's compliance data + reg knowledge | All roles |
| **Admin & Settings** | Entities, team, roles, notification config, profile editing | Compliance Officer (admin) |

---

## 6. DATABASE SCHEMA (V1)

PostgreSQL. Multi-tenant via `organization_id` + row-level security. Core insight: **obligation templates** (master content) are instantiated as **company obligations** per org, which spawn **obligation instances** (the recurring occurrences with real due dates).

### 6.1 Tenancy & Identity

```
organizations
  id              uuid PK
  name            text
  trial_ends_at   timestamptz
  plan_tier       text         -- starter | growth | scale
  created_at      timestamptz

entities                         -- legal entities under an org (1–3 in V1)
  id              uuid PK
  organization_id uuid FK -> organizations
  legal_name      text
  cin             text
  nbfc_cor_number text          -- RBI Certificate of Registration
  pan             text
  nbfc_type       text
  rbi_layer       text          -- base | middle
  deposit_taking  boolean
  is_listed       boolean
  created_at      timestamptz

locations                        -- registered office + branches (for state laws)
  id              uuid PK
  entity_id       uuid FK -> entities
  type            text          -- registered_office | branch
  state           text
  city            text

users
  id              uuid PK
  email           text UNIQUE
  full_name       text
  auth_provider   text          -- password | google | microsoft
  created_at      timestamptz

memberships                      -- user <-> org with role
  id              uuid PK
  user_id         uuid FK -> users
  organization_id uuid FK -> organizations
  role            text          -- compliance_admin | head | preparer
  status          text          -- invited | active
  created_at      timestamptz
```

### 6.2 Compliance Content Library (master, curated by content team)

```
law_library
  id              uuid PK
  name            text          -- e.g. "RBI Master Direction - NBFC SBR"
  regulator       text          -- RBI | MCA | Income Tax | EPFO | State
  category        text          -- rbi | corporate | tax | labour | fema
  reference_url   text
  last_reviewed_at timestamptz

obligation_templates             -- the reusable compliance items
  id              uuid PK
  law_id          uuid FK -> law_library
  title           text          -- e.g. "Filing of DNBS-02 Return"
  description     text
  frequency       text          -- one_time | monthly | quarterly | half_yearly | annual | event_based
  due_rule        jsonb         -- e.g. {"type":"day_of_month","day":15} or {"type":"days_after_period_end","days":15}
  applicability_rule jsonb       -- profile conditions that make this applicable
  form_reference  text          -- e.g. "DNBS-02"
  default_owner_role text        -- preparer | compliance_admin
  penalty_note    text
```

### 6.3 Per-Organization Compliance Data (instantiated)

```
company_obligations              -- templates applied to a specific entity
  id              uuid PK
  organization_id uuid FK
  entity_id       uuid FK -> entities
  template_id     uuid FK -> obligation_templates
  is_active       boolean        -- user can mark not-applicable
  applicability_confidence numeric -- AI confidence 0–1 at generation
  owner_user_id   uuid FK -> users  -- default owner
  created_at      timestamptz

obligation_instances             -- the actual recurring occurrences with due dates
  id              uuid PK
  company_obligation_id uuid FK -> company_obligations
  organization_id uuid FK         -- denormalized for RLS + fast queries
  period_label    text           -- e.g. "Mar 2026", "Q4 FY26"
  due_date        date
  status          text           -- pending | in_progress | ready_for_review | completed | overdue | not_applicable
  owner_user_id   uuid FK -> users
  completed_at    timestamptz
  completed_by    uuid FK -> users
  approved_by     uuid FK -> users
  created_at      timestamptz

  INDEX (organization_id, due_date, status)
```

### 6.4 Evidence & Documents

```
documents
  id              uuid PK
  organization_id uuid FK
  entity_id       uuid FK
  uploaded_by     uuid FK -> users
  file_url        text           -- S3 key
  file_name       text
  mime_type       text
  ai_doc_type     text           -- AI classification: challan | return_ack | certificate | board_minutes | other
  ai_extracted    jsonb          -- {dates:[], amounts:[], reference_numbers:[]}
  expiry_date     date           -- AI-extracted, if applicable
  created_at      timestamptz

document_links                   -- many-to-many: document <-> obligation instance
  id              uuid PK
  document_id     uuid FK -> documents
  obligation_instance_id uuid FK -> obligation_instances
```

### 6.5 Legal Updates

```
legal_updates                    -- master feed, curated + AI-summarized
  id              uuid PK
  law_id          uuid FK -> law_library
  title           text
  source_url      text
  published_date  date
  ai_summary      text           -- AI-generated plain-language summary
  ai_impact_note  text
  affects_filter  jsonb          -- which profiles this affects
  created_at      timestamptz

legal_update_status              -- per-org review state
  id              uuid PK
  organization_id uuid FK
  legal_update_id uuid FK -> legal_updates
  status          text           -- new | reviewed | applicable | not_applicable
  reviewed_by     uuid FK -> users
  reviewed_at     timestamptz
```

### 6.6 System & AI

```
audit_log                        -- append-only, immutable
  id              uuid PK
  organization_id uuid FK
  actor_user_id   uuid FK
  action          text           -- created | completed | approved | uploaded | marked_na | ...
  entity_type     text           -- obligation_instance | document | ...
  entity_id       uuid
  metadata        jsonb
  created_at      timestamptz

notifications
  id              uuid PK
  organization_id uuid FK
  user_id         uuid FK
  type            text           -- reminder | escalation | legal_update | assignment
  channel         text           -- email | slack
  payload         jsonb
  sent_at         timestamptz
  read_at         timestamptz

copilot_messages                 -- conversation log (also for quality review)
  id              uuid PK
  organization_id uuid FK
  user_id         uuid FK
  role            text           -- user | assistant
  content         text
  retrieved_context jsonb         -- what RAG/SQL data was used (for traceability)
  created_at      timestamptz
```

### 6.7 The key data model insight

A template like *"DNBS-02 Monthly Return"* (frequency=monthly) is applied once as a `company_obligation`, then a background job generates twelve `obligation_instances` per year, each with its own due date, owner, and status. **This is what makes recurring compliance trackable rather than a static checklist** — and it's the foundation the dashboard and reminders query against.

---

## 7. AI CAPABILITIES (V1 — PRACTICAL ONLY)

All V1 AI is **assistive, read-only, and human-confirmed**. No autonomous external actions.

### 7.1 AI Capability 1 — Compliance Calendar Generation (the core differentiator)
- **Input:** company profile from onboarding questionnaire
- **Method:** Retrieval over the curated NBFC obligation library + LLM applicability reasoning against `applicability_rule`
- **Output:** ranked list of applicable `obligation_templates` with confidence scores and plain-language rationale
- **Human gate:** user reviews and confirms; can mark any as not-applicable
- **Why it's safe:** it proposes; the human accepts. Errors are visible and correctable in the review step.

### 7.2 AI Capability 2 — Legal Update Summarization
- **Input:** raw regulatory circular / notification text (sourced by content team or monitored feeds)
- **Output:** plain-language summary + impact note + applicability filter
- **Human gate:** content team reviews summaries before publishing to the feed; org users then review applicability for their entity
- **Note:** V1 does NOT auto-monitor 1,500 sources autonomously (that's Phase 2). V1 covers a **curated set of priority NBFC laws** with a semi-automated summarization pipeline.

### 7.3 AI Capability 3 — Document Intelligence (classification + extraction)
- **Input:** uploaded evidence document (PDF/image)
- **Output:** document type classification, extracted dates/amounts/reference numbers, suggested obligation link, expiry date if present
- **Human gate:** suggestions are pre-filled but user confirms the obligation link
- **Value:** removes manual tagging; flags expiring licenses automatically

### 7.4 AI Capability 4 — Compliance Copilot (read-only Q&A)
- **Scope:** answers questions over (a) the org's own compliance data via structured queries, and (b) general NBFC regulatory knowledge via RAG over the reg corpus
- **Examples:** "What's due this week?", "Which obligations are overdue?", "What does DNBS-02 require?", "What changed in the last RBI circular that affects us?"
- **Guardrails:**
  - Read-only — cannot complete tasks, file, or send anything
  - Cites sources (law reference) and shows confidence for regulatory answers
  - For ambiguous/high-stakes legal interpretation, responds with "review with your legal team" rather than asserting
  - Every answer logs `retrieved_context` for traceability

### 7.5 What AI does NOT do in V1
- Does not file returns or submit to regulators
- Does not draft responses to RBI / legal notices
- Does not auto-mark obligations complete
- Does not make applicability decisions without human confirmation
- Does not give definitive legal advice on ambiguous matters

---

## 8. USER JOURNEYS

### 8.1 Journey — Onboarding
1. Compliance Officer signs up via Google SSO
2. Enters org + 1 entity (NBFC details: CoR, PAN, type, layer)
3. Answers the 9-question compliance profile
4. AI generates 142 obligations across 18 laws (90 sec, progress UI)
5. Officer reviews, deselects 6 not-applicable items, confirms
6. Invites Compliance Head + 2 preparers; accepts AI's suggested owner assignments
7. Connects Slack; sets reminder lead times
8. Lands on dashboard → sees "3 due this week" → tries Copilot: "what's due this month?"
9. **Outcome:** live calendar in ~22 minutes

### 8.2 Journey — Compliance Task Completion
1. Preparer gets Slack notification: "DNBS-02 return for Mar 2026 due in 3 days"
2. Clicks through → sees obligation detail, law reference, what's required
3. Prepares the return externally, uploads the filed acknowledgment PDF
4. AI classifies it as "return_acknowledgment", extracts filing date + reference number, suggests linking to this obligation
5. Preparer confirms the link, marks "Ready for review"
6. Compliance Officer gets notified → reviews evidence → approves → status = completed
7. `audit_log` records the full chain; dashboard health score updates
8. **Outcome:** obligation closed with evidence trail, zero spreadsheet edits

### 8.3 Journey — Document Upload
1. User drags a PF challan PDF into the Evidence Repository (or uploads to a task)
2. AI classifies: type = "challan", extracts deposit period + amount + date
3. AI suggests: "This looks like a PF payment for Mar 2026 — link to EPFO monthly obligation?"
4. User confirms link (or picks a different obligation)
5. Document stored, linked, searchable; if it carries an expiry (e.g., a license), AI sets `expiry_date` and schedules a renewal reminder
6. **Outcome:** tagged, linked evidence with no manual metadata entry

### 8.4 Journey — Legal Update Review
1. Content team publishes a new RBI circular to the feed (AI-summarized)
2. System matches `affects_filter` to the org's profile → flags it "May affect you"
3. Compliance Officer sees a dashboard alert + Legal Updates feed entry
4. Reads the AI plain-language summary and impact note (with link to source)
5. Marks it "Applicable" → (V1) creates a follow-up task manually, or "Not applicable" → dismissed with reason
6. Copilot can answer: "What does this circular change for our reporting?"
7. **Outcome:** the team learns about the change proactively, in plain language, with applicability pre-filtered

---

## 9. DASHBOARD STRUCTURE & INFORMATION HIERARCHY

**Design principle:** answer "what do I do right now?" in under 5 seconds. Risk-weighted, action-first.

```
┌─ TOP BAR ─────────────────────────────────────────────┐
│  Entity selector ▾     Compliance Health: 87% ●        │
└───────────────────────────────────────────────────────┘

┌─ ROW 1: AI NARRATIVE SUMMARY ─────────────────────────┐
│  "3 items need attention this week. DNBS-02 is due     │
│   Friday and unassigned. 1 obligation is overdue."     │
└───────────────────────────────────────────────────────┘

┌─ ROW 2: ACTION TILES ─────────────────────────────────┐
│  [ Overdue: 1 ]  [ Due this week: 3 ]  [ At risk: 2 ] │
│  [ Awaiting my review: 4 ]                             │
└───────────────────────────────────────────────────────┘

┌─ ROW 3: PRIORITY QUEUE (main work area) ──────────────┐
│  Obligation | Law | Due | Owner | Status | Action     │
│  ...sorted by risk (overdue → due-soon → at-risk)     │
└───────────────────────────────────────────────────────┘

┌─ ROW 4: SECONDARY ────────────────────────────────────┐
│  [ Legal Updates: 2 new ]   [ Expiring docs: 1 ]      │
└───────────────────────────────────────────────────────┘

┌─ PERSISTENT RIGHT SIDEBAR ────────────────────────────┐
│  Copilot — "Ask what's due, what changed, what's at   │
│  risk"                                                 │
└───────────────────────────────────────────────────────┘
```

**Information hierarchy (most → least prominent):**
1. AI narrative summary (what matters now, in words)
2. Risk-weighted action counts (overdue first, never alphabetical)
3. The priority work queue (the actual list to act on)
4. Legal updates + expiring documents (awareness layer)
5. Copilot (always available, never blocking)

**Head/CFO view:** same dashboard, but defaults to the multi-entity rollup + "Export PDF" prominent.

---

## 10. PERMISSIONS & ROLE SYSTEM (V1)

Three roles. Deliberately simple.

| Capability | Compliance Admin (Officer/CS) | Head / CFO | Preparer |
|---|---|---|---|
| View dashboard & all obligations | ✅ | ✅ | Assigned only |
| Edit company profile / applicability | ✅ | ❌ | ❌ |
| Generate / regenerate calendar | ✅ | ❌ | ❌ |
| Assign owners | ✅ | ❌ | ❌ |
| Upload evidence | ✅ | ✅ | ✅ (assigned) |
| Mark "Ready for review" | ✅ | ❌ | ✅ |
| Approve / mark complete | ✅ | ✅ | ❌ |
| Mark obligation not-applicable | ✅ | ❌ | ❌ |
| Review legal updates | ✅ | ✅ | ❌ |
| Invite / manage team | ✅ | ❌ | ❌ |
| Use Copilot | ✅ | ✅ | ✅ (scoped to own data) |
| Export reports (PDF) | ✅ | ✅ | ❌ |
| Manage integrations / settings | ✅ | ❌ | ❌ |

**Notes:**
- The **Compliance Admin** is the super-user for the org (first signup defaults to this).
- **Maker-Checker:** Preparer submits → Admin/Head approves. No deeper chains in V1.
- Multi-entity: roles are per-org in V1 (not per-entity scoping) to keep it simple; entity selector filters the view.

---

## 11. REQUIRED INTEGRATIONS (V1)

Minimal, high-leverage only. **No government portal integrations in V1.**

| Integration | Purpose | Effort |
|---|---|---|
| **Google / Microsoft SSO** | Frictionless signup + enterprise trust | Low (Auth provider) |
| **Email (AWS SES / Resend)** | Reminders, escalations, invites, digests | Low |
| **Slack** | Notifications + reminders in-workflow | Low–Medium |
| **Calendar export (.ics feed)** | Push due dates into Google/Outlook calendars | Low |
| **S3 (storage)** | Evidence document storage | Low |
| **Claude API** | All AI capabilities | Low (API) |

**Explicitly deferred:** RBI COSMOS, MCA21, GSTN, EPFO, ERP/accounting (Tally, Zoho), HRMS. These are Phase 2. V1 relies on manual evidence upload, not portal verification.

---

## 12. TECHNICAL ARCHITECTURE (SIMPLIFIED FOR MVP)

Lean, modular monolith. Optimize for shipping speed.

```
┌──────────────────────────────────────────────┐
│  FRONTEND                                      │
│  Next.js 14 (App Router) + TypeScript          │
│  Tailwind + shadcn/ui · TanStack Query         │
│  Vercel AI SDK (streaming Copilot)             │
└──────────────────────────────────────────────┘
                     │ REST/RPC
┌──────────────────────────────────────────────┐
│  BACKEND (modular monolith)                    │
│  Node.js + Fastify (TypeScript)                │
│  Modules: auth · onboarding · obligations ·    │
│  documents · legal-updates · copilot · notify  │
└──────────────────────────────────────────────┘
        │              │              │
┌───────────┐  ┌──────────────┐  ┌──────────────┐
│ PostgreSQL │  │   Redis      │  │  AWS S3      │
│ (Supabase) │  │ cache + queue│  │  documents   │
│ + RLS      │  │ (BullMQ)     │  │              │
└───────────┘  └──────────────┘  └──────────────┘
        │
┌──────────────────────────────────────────────┐
│  AI LAYER                                      │
│  Claude (Sonnet: copilot, summarize, classify)│
│  Vector DB (Qdrant or Pinecone) for reg corpus │
│  + per-org document namespace                  │
└──────────────────────────────────────────────┘

BACKGROUND JOBS (BullMQ on Redis):
  • obligation_instance generator (recurring due dates)
  • reminder/escalation scheduler
  • document AI processing
  • legal-update applicability matcher
```

**Key choices & rationale:**
- **Modular monolith, not microservices** — one deployable; faster to ship and debug at this stage.
- **Supabase Postgres + RLS** — managed, fast to start, hard tenant isolation built in.
- **BullMQ on Redis** — the recurring-instance generator and reminder scheduler are the backbone; needs a reliable queue.
- **Claude Sonnet** for all V1 AI — speed/cost balance; Opus reserved for harder reasoning later.
- **Data residency:** Indian AWS region (ap-south-1) — non-negotiable for NBFC trust + DPDP posture.
- **Hosting:** Vercel (frontend) + AWS (backend/services) or a single AWS deployment.

**Security baseline for V1 (financial-sector buyers expect it):**
- RLS tenant isolation + RBAC
- Encryption at rest (S3 SSE, DB encryption) + TLS in transit
- Field-level encryption for PAN/CIN
- Append-only audit log
- A documented security posture (ISO 27001 in progress) — even pre-certification, NBFCs will ask

---

## 13. SUCCESS METRICS — FIRST 20 CUSTOMERS

### 13.1 Activation (the make-or-break funnel)

| Metric | Target |
|---|---|
| Signup → completed onboarding (live calendar) | ≥ 80% |
| Time-to-first-value (signup → populated dashboard) | < 30 min (median) |
| % of AI-generated obligations accepted (not marked N/A) | ≥ 85% (proxy for content accuracy) |
| Teams that invite ≥ 1 additional member | ≥ 70% |

### 13.2 Engagement (is it becoming a habit?)

| Metric | Target |
|---|---|
| Weekly active compliance officers (per customer) | ≥ 1 (the daily user shows up weekly) |
| Obligations with evidence uploaded | ≥ 60% of completed |
| Copilot queries per active user per week | ≥ 3 |
| Legal updates reviewed (not ignored) | ≥ 50% within 7 days of publish |

### 13.3 Value & Retention

| Metric | Target |
|---|---|
| Trial → paid conversion | ≥ 40% |
| Logo retention at 90 days | ≥ 90% |
| Reported missed-deadline rate vs. pre-platform | Self-reported reduction |
| NPS (after 60 days of use) | ≥ 60 |
| Customers willing to be a reference | ≥ 8 of 20 |

### 13.4 The single north-star metric for Phase 1
**Weekly Active Compliance Officers across paying customers** — if the daily user logs in every week and acts, the product is working. Everything else is a leading indicator of this.

### 13.5 PMF signal
At least **10 of 20** customers would be "very disappointed" if the product disappeared (Sean Ellis test), and **≥ 3** refer a peer NBFC unprompted.

---

## 14. RISKS, EDGE CASES & OPERATIONAL DEPENDENCIES

### 14.1 Top Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **Compliance content accuracy** — wrong/missing obligations destroy trust instantly in a regulated sector | 🔴 Critical | Curated NBFC library reviewed by a qualified CS/compliance expert before launch; confidence scores + human review gate; tight feedback loop on "marked N/A" |
| **Content cold-start** — library not ready by launch | 🔴 Critical | Hire/contract 1–2 NBFC compliance researchers from Day 1; scope to NBFC-only to keep it buildable; start with the ~150 highest-frequency obligations |
| **LLM hallucination in Copilot legal answers** | 🟠 High | Read-only scope; mandatory source citation; "consult legal team" fallback for ambiguity; log all retrieved context; eval suite on common NBFC questions |
| **AI misclassifies applicability in onboarding** | 🟠 High | Human review/confirm step is mandatory; rationale shown; one-click correction feeds back to library |
| **Document AI mis-tags / mis-extracts** | 🟡 Medium | Suggestions are pre-filled, not auto-applied; user confirms link; allow manual override always |
| **Low engagement after onboarding** ("set and forget") | 🟠 High | Reminders + Slack nudges + weekly digest; the recurring-obligation model forces repeat use |
| **Trust barrier** — NBFCs cautious about cloud + data | 🟠 High | Data residency in India; security posture documented; field-level encryption; offer security questionnaire responses early |
| **Founder-led content doesn't scale past 20** | 🟡 Medium | Acceptable for Phase 1; productize content updates in Phase 2 |

### 14.2 Edge Cases to Handle in V1

- **Multi-entity with different profiles** — entity A is deposit-taking, entity B isn't → obligations must differ per entity (schema supports via `entity_id` on `company_obligations`)
- **Obligation due date falls on a holiday/weekend** — due-rule engine must support "next working day" adjustment
- **Mid-period onboarding** — a customer joining in March shouldn't be shown as "overdue" for January obligations they handled elsewhere; generate instances from onboarding date forward, with optional backfill marked "historical / not tracked"
- **User marks an obligation N/A that's actually applicable** — log it, allow re-activation, surface in admin review
- **Document uploaded but not linkable to any obligation** — allow "unlinked evidence" state in the repository
- **Profile change after generation** (e.g., NBFC layer reclassified) — support calendar regeneration with a diff view ("4 new obligations added, 2 removed")
- **Owner leaves / is removed** — obligations must reassign, not orphan
- **Legal update with no clean applicability match** — default to "review manually" rather than silently dropping it
- **Frequency edge cases** — half-yearly and event-based obligations (e.g., "within 30 days of board meeting") need flexible `due_rule` handling

### 14.3 Operational Dependencies

| Dependency | Owner | Criticality |
|---|---|---|
| **Curated NBFC obligation library** (laws, templates, due rules, applicability rules) | Compliance content team (CS/CA) | Blocking — product is empty without it |
| **Regulatory update pipeline** (someone sourcing + summarizing RBI/MCA changes) | Content team + AI pipeline | High — the "stays current" promise depends on it |
| **LLM API reliability + cost** (Claude) | Eng | Medium — cache, fallback gracefully |
| **Eval set for Copilot accuracy** | Eng + content | High — prevents accuracy regressions |
| **Design partner feedback loop** (weekly sessions) | Founder/PM | High — the source of truth for what to fix |
| **Security documentation** for NBFC procurement | Eng/Founder | Medium — gates some deals |

### 14.4 The single biggest dependency

**The compliance content library is the product's foundation, not a feature.** No amount of AI or UX compensates for an inaccurate or incomplete obligation set in a regulated financial vertical. Staffing a qualified NBFC compliance researcher from Day 1 is the highest-priority operational commitment in Phase 1. Treat content as a first-class engineering input.

---

## APPENDIX — PHASE 1 BUILD SEQUENCE (suggested)

| Weeks | Focus |
|---|---|
| 1–3 | Content library foundation (top ~150 NBFC obligations) + schema + auth/tenancy |
| 3–6 | Onboarding flow + AI calendar generation + review/confirm |
| 5–8 | Obligation tracker + recurring instance engine + Maker-Checker |
| 7–10 | Evidence repository + document AI (classify/extract/link) |
| 9–12 | Dashboard + health score + AI narrative + PDF export |
| 11–14 | Legal updates feed + summarization pipeline + applicability matching |
| 13–16 | Copilot v1 (read-only RAG + SQL) + eval suite |
| 15–18 | Notifications (email/Slack), reminders, escalations, calendar export |
| 17–22 | Hardening, security baseline, design-partner onboarding, fixes |
| 22–26 | Onboard first 20 customers; tight feedback + iteration |

---

*Phase 1 only. No Phase 2/3 features included by design. Prioritized for shipping speed, daily usability, and time-to-value. Built on the Indian GRC market opportunity assessment as base context.*
