# Compliance Copilot — Specification (Phase 1)
## NBFC Compliance Platform

> **Component:** Compliance Copilot (read-only AI assistant)
> **Role:** Answers natural-language questions over the org's compliance instances, uploaded evidence, obligation library, and a regulatory knowledge base — grounded, cited, permission-aware, and read-only
> **Status:** Build-ready. A working reference implementation (`compliance_copilot.py`) accompanies this spec and runs against the live library + generated instances.
> **Scope:** Phase 1 only.

---

## 1. PURPOSE & POSITION IN THE SYSTEM

The copilot is the conversational surface over everything the other engines produce. A compliance officer asks *"what's overdue?"*, *"what does DNBS-02 require?"*, *"do we have evidence for the March PF filing?"* — and gets a grounded, cited answer in seconds, instead of navigating tables.

```
                ┌──────────── obligation_instances (structured)
                ├──────────── documents (uploaded evidence)
COPILOT  ◄──────┤
(read-only)     ├──────────── obligation library (templates + laws)
                └──────────── regulatory knowledge base (RAG corpus)
```

**Maps to PRD:** *AI Capability 4 — Compliance Copilot (read-only Q&A)*. It is the lowest-risk-by-design AI surface: it never acts, never writes, and answers only from retrieved sources.

**Two hard design commitments** (everything else follows from these):
1. **Read-only.** The copilot cannot file, submit, approve, or mark anything. Action requests are escalated back to the workflow.
2. **Grounded or silent.** Every factual claim must cite a retrieved source. If retrieval is empty or weak, the copilot abstains — it does not fall back on the model's parametric memory.

---

## 2. SOURCES & CONTEXT HIERARCHY

Four sources, ordered by trust. When sources could conflict on an **org-specific fact**, higher tiers win; the regulatory KB is authoritative only for **general law**, never for the org's own status.

| Tier | Source | Nature | Trust | Used for |
|---|---|---|---|---|
| 1 | **Org structured data** (`obligation_instances`, `company_obligations`) | exact, queryable | highest | "what's due/overdue", status, counts — anything about *this org's* calendar |
| 2 | **Uploaded evidence** (`documents` + extracted fields) | org-private, semi-structured + RAG | high | "what evidence do we have for X", "when was the PF challan paid" |
| 3 | **Obligation library** (templates + laws) | semi-structured | high (if verified) | "what does X require", due rule, penalty, form |
| 4 | **Regulatory knowledge base** (law text, circulars, master directions) | shared RAG corpus | medium, `DRAFT_UNVERIFIED`-gated | "what does the RBI SBR direction say" — general regulatory Q&A |

**Precedence rule:** a question like *"are we on track with DNBS-02?"* is answered from **Tier 1** (the org's actual instances), never from Tier 4. The copilot routes org-fact questions to structured retrieval first — this is the primary anti-hallucination mechanism (§7).

---

## 3. RETRIEVAL ARCHITECTURE

```
Query
  │
  1. INTENT ROUTER ───────────► escalate? (action / legal-opinion / out-of-scope)  → §8
  │                                  │ no
  2. PERMISSION SCOPING  (role → allowed rows, applied BEFORE retrieval)            → §4
  │
  3. RETRIEVAL (per intent):
  │     structured intents → bounded query templates over scoped instances (exact)
  │     evidence intents    → documents metadata + org-private vector namespace
  │     library intents     → obligation_templates / law_library lookup
  │     legal intents       → hybrid RAG over regulatory corpus (dense + recency rerank)
  │
  4. CONTEXT ASSEMBLY  (only retrieved rows/chunks; nothing else)
  │
  5. ANSWER GENERATION (LLM, closed-book over context, strict citation contract)
  │
  6. GROUNDING VERIFIER  (every claim cites a retrieved id; else refuse/regenerate)  → §6
  │
  7. CONFIDENCE + PROVISIONAL FLAG                                                   → §7
  │
  8. RESPONSE  +  AUDIT RECORD                                                       → §9
```

### 3.1 Intent router
Classifies the query into one of nine intents. In production an LLM classifier; the reference ships a deterministic pattern router (also the offline test oracle).

| Intent | Route |
|---|---|
| `DUE_WINDOW`, `STATUS_LOOKUP`, `COUNT_SUMMARY` | structured retrieval (Tier 1) |
| `EVIDENCE_LOOKUP` | documents (Tier 2) |
| `OBLIGATION_INFO` | library (Tier 3) |
| `LEGAL_QA` | regulatory KB / RAG (Tier 4) |
| `ACTION_REQUEST`, `LEGAL_OPINION`, `OUT_OF_SCOPE` | **escalate / decline** (§8) |

### 3.2 Structured retrieval (no arbitrary SQL)
Phase-1 structured queries use a **bounded set of parameterized templates** (due-window, status-lookup, count-summary) — never free-form LLM-authored SQL against the database. This eliminates an entire class of injection and correctness risks and makes structured answers exact and reproducible. New query shapes are added as reviewed templates, not generated at runtime.

### 3.3 RAG (Tiers 2 & 4)
Hybrid retrieval per the PRD architecture: dense vector similarity + recency re-rank (a recent circular outranks an older one on the same topic), over (a) the org's private document namespace and (b) the shared regulatory corpus. Retrieval quality (`strong`/`weak`) feeds confidence (§7).

---

## 4. PERMISSION-AWARE ACCESS

Permission scoping is applied **before retrieval**, at the row level — not by filtering the answer afterward. The copilot can never retrieve, reason over, or cite data the user is not entitled to see.

| Role | Scope |
|---|---|
| `compliance_admin` | all org instances, documents, library |
| `head` / CFO | all org instances, documents, library (view) |
| `preparer` | **only their assigned instances and own uploads** |

When a preparer asks an org-wide question, the copilot answers within their scope and says so. **Verified:** for *"what's due this week?"* the admin saw **18** obligations; the preparer saw **13** (their assigned subset) with the note *"Scoped to your assigned obligations (preparer access)."* Same question, correctly different answers — because scoping happened at retrieval, not in the prose.

Tenant isolation (`organization_id` + RLS) is enforced underneath all of this; the copilot operates strictly within one org.

---

## 5. SOURCE GROUNDING & CITATIONS

Every factual claim carries ≥1 typed citation. Citation types:

| Citation | Resolves to | Verifiability |
|---|---|---|
| `instance:<id>` | an obligation instance | exact |
| `document:<id>` | an uploaded document | exact |
| `template:<id>` | a library obligation | exact |
| `law:<id>` | a law_library entry | exact |
| `regchunk:<id>` | a chunk in the reg corpus | exact (shows snippet + source) |
| `derived:<desc>` | a computed aggregate over scoped rows | grounded by computation |

**Citation contract for the LLM:** answer *only* from the assembled context; attach the source id to every claim; if the context doesn't support a claim, don't make it. Structured answers cite the exact instance/document ids (the verified run cited all 18 due-this-week instances individually). Aggregate answers (counts, summaries) are grounded *by computation* over the permission-scoped row set and carry a `derived:` citation. RAG answers cite the chunk and render the source snippet on demand.

---

## 6. GROUNDING VERIFIER (HALLUCINATION GATE)

After generation, a deterministic verifier checks the answer's citations against the retrieved id set:

```
verify_grounding(answer_citations, retrieved_ids):
   unknown = citations not present in retrieved_ids
   grounded = (citations non-empty) and (no unknown)
```

- **Any citation not in the retrieved set ⇒ the answer is not grounded ⇒ refuse or regenerate.** This catches a model inventing an instance id, a form, or a circular that was never retrieved.
- A factual answer with **zero** citations is rejected (except escalations and computed aggregates, which carry a `derived:` source).
- The verifier is pure and reproducible — part of the audit trail.

---

## 7. CONFIDENCE & HALLUCINATION PREVENTION

### 7.1 Confidence model

| Answer basis | Confidence |
|---|---|
| Structured retrieval (exact query over scoped rows) | **0.97** |
| Evidence/document lookup (exact metadata) | 0.97 |
| Library lookup, template **VERIFIED** | 0.85 |
| Library lookup, template `DRAFT_UNVERIFIED` | **≤ 0.70** (capped) + provisional |
| Reg-KB RAG, strong retrieval | 0.70 |
| Reg-KB RAG, weak retrieval | 0.45 → abstain/escalate |

**Verified:** structured queries returned 0.97; the *"what does DNBS-02 require?"* library answer and the SBR legal-QA answer both returned **0.70 with `provisional=true`**, because the underlying content is `DRAFT_UNVERIFIED`.

### 7.2 Layered hallucination prevention

1. **Structured-first routing** — org-fact questions never touch the LLM's parametric memory; they hit deterministic query templates.
2. **Closed-book generation** — system prompt forbids outside knowledge; answer only from assembled context.
3. **Grounding verifier** (§6) — every claim must map to a retrieved id.
4. **Abstention** — empty/weak retrieval ⇒ "I don't have enough to answer that" rather than a guess. (A structured query returning zero rows is a valid, grounded *"nothing found"*.)
5. **Confidence floor** — below threshold, the copilot does not assert; it escalates (§8).
6. **`DRAFT_UNVERIFIED` cap** — unverified library/reg content is capped at 0.70 and shown with a provisional disclaimer — the same content gate that runs through every other engine.
7. **No-opinion guard** — interpretive legal/financial questions are never answered as fact (§8).

---

## 8. ESCALATION RULES

The copilot recognizes three categories it must **not** answer, and routes them appropriately. Escalation is decided **first**, before retrieval.

| Trigger | Detection | Response |
|---|---|---|
| **Action request** (file, submit, pay, mark complete, approve, send) | intent `ACTION_REQUEST` | *Read-only* refusal: "I can't take actions — I'm read-only. Here's the obligation and its evidence so you can act in the tracker." |
| **Legal opinion** (are we compliant? will we be fined? can we skip…?) | intent `LEGAL_OPINION` | *Consult professional*: shows the facts, declines the opinion, routes to compliance head / qualified professional. |
| **Out of scope** (litigation, contracts, audit, ERM, IFC) | intent `OUT_OF_SCOPE` | *Scope decline*: states these aren't covered in V1 (NBFC statutory compliance only). |

**Verified:** *"File my GST return for me"* → read-only escalation; *"Are we definitely compliant with RBI?"* → consult-professional escalation; *"Help me with our litigation case"* → out-of-scope decline. None of the three produced a substantive answer.

**Additional soft escalation:** if structured data reveals a likely breach (e.g., an overdue high-risk obligation), the copilot states it factually and suggests human review — it surfaces, it does not advise or alarm.

---

## 9. AUDIT LOGS

Every turn is recorded — non-negotiable in a regulated setting where you must reconstruct exactly what the copilot was asked, what it could see, and what it said.

Extends the PRD `copilot_messages` schema:

| Field | Captured |
|---|---|
| `user_id`, `role`, `organization_id` | who asked, with what permissions |
| `query` | verbatim question |
| `intent` | router classification |
| `retrieved_context` | the source ids retrieved (the grounding set) |
| `citations` | source ids cited in the answer |
| `confidence`, `provisional` | scoring + content-gate flag |
| `escalation` | reason if escalated/declined |
| `grounding` | verifier result (grounded / unknown citations) |
| `model_version` | classifier + generator version |
| `created_at` | timestamp |

**Reproducibility:** routing, scoping, structured retrieval, and grounding are deterministic; the `retrieved_context` + `model_version` make any AI-phrased answer traceable to the exact data and model that produced it.

---

## 10. ARCHITECTURE

| Concern | Phase-1 approach |
|---|---|
| **LLM** | Claude — intent classification (cheap/fast) + answer generation (closed-book, strict citations) |
| **Structured layer** | bounded parameterized query templates over Postgres (RLS-scoped) |
| **RAG** | vector DB: per-tenant `company-documents` namespace + shared `regulatory-corpus`; hybrid retrieval + recency rerank |
| **Streaming** | Vercel AI SDK streaming UI; persistent sidebar (PRD UX) |
| **Caching** | cache embeddings + frequent structured answers (short TTL tuned to data freshness) |
| **Cost control** | structured intents skip the LLM for retrieval entirely; LLM used for phrasing + RAG synthesis |
| **Latency** | structured answers near-instant; RAG answers stream |
| **Security** | permission scope + tenant RLS before retrieval; reg corpus read-only; no write paths exist |

---

## 11. EDGE CASES

| Case | Handling |
|---|---|
| Question spans two sources ("is the DNBS-02 filed *and* what does it require?") | multi-intent: structured status (Tier 1) + library info (Tier 3); both cited |
| Structured query returns nothing | grounded *"nothing due this week"* — not a guess |
| Preparer asks org-wide question | answered within their scope + explicit scope note |
| Ambiguous obligation reference ("the RBI return") | copilot asks to disambiguate or lists candidates with ids |
| Regulatory question on unverified content | answered with ≤0.70 confidence + provisional disclaimer + "confirm with legal" |
| Model returns an uncited claim | grounding verifier rejects → regenerate or abstain |
| User pushes for a yes/no compliance verdict | held to the legal-opinion escalation; facts yes, verdict no |
| Out-of-window historical question | answers from stored instances/audit log if present; abstains if not tracked |
| Prompt-injection in an uploaded document | retrieved content is treated as data, not instructions; the system prompt isolates context from directives |

---

## 12. TESTING STRATEGY

| Test class | What it locks down |
|---|---|
| **Router tests** | each intent classified correctly incl. the three escalation intents |
| **Permission tests** | preparer-scoped vs admin results differ correctly (verified 13 vs 18) |
| **Structured-answer tests** | due-window / status / count return exact rows for a fixed instance set + `today` |
| **Grounding tests** | uncited/invented-id answers rejected; valid citations pass; aggregates grounded by `derived:` |
| **Confidence tests** | structured 0.97; unverified library/RAG capped 0.70 + provisional |
| **Escalation tests** | action / legal-opinion / out-of-scope produce no substantive answer (verified) |
| **Abstention tests** | empty retrieval → grounded "nothing found", never fabrication |
| **Audit tests** | every turn writes query, retrieved_context, citations, confidence, escalation, model_version |
| **Golden transcript regression** | the 10-query reference transcript locked as a fixture |

> As with the other engines: tests prove the copilot retrieves, scopes, grounds, and routes correctly. Whether the underlying regulatory content is *legally* correct remains a content-team item against the `DRAFT_UNVERIFIED` gate — which is exactly why unverified content is confidence-capped and flagged provisional here.

---

## APPENDIX — REFERENCE IMPLEMENTATION

`compliance_copilot.py` (shipped with this spec) implements the deterministic scaffolding: the intent router, permission scoping, the bounded structured-retrieval templates, the grounding verifier, the confidence model with the `DRAFT_UNVERIFIED` cap, the escalation rules, and audit-record assembly. LLM generation and RAG are behind clean interfaces (stubbed). It runs against the live library and a generated 367-instance org set and reproduces every figure in this document.

```
python compliance_copilot.py
```

Verified transcript (selected):
```
"What's due this week?"        (admin)    → DUE_WINDOW   conf 0.97  18 cited instances
"What's due this week?"        (preparer) → DUE_WINDOW   conf 0.97  13 (scoped) + scope note
"What's overdue?"              (admin)    → DUE_WINDOW   conf 0.97  10 cited
"Status of DNBS-02?"           (admin)    → STATUS       conf 0.97  4 cited
"File my GST return for me"               → ACTION_REQUEST   → read-only escalation
"Are we definitely compliant with RBI?"   → LEGAL_OPINION    → consult-professional
"Help me with our litigation case"        → OUT_OF_SCOPE     → scope decline
"What does DNBS-02 require?"               → OBLIGATION_INFO  conf 0.70 provisional
"What does the RBI SBR direction say?"     → LEGAL_QA         conf 0.70 provisional
```

*Phase 1 only. Read-only; structured-first; grounded-or-silent; permission-scoped before retrieval; escalates action and legal-opinion requests; audit-logged; wired to the same DRAFT_UNVERIFIED content gate.*
