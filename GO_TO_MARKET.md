# Go-to-Market — Regis

Status: **proposed, not decided.** This is a plan, not policy. Promote anything you
commit to into `DECISIONS.md` in the usual format.

Written 2026-08-08 against the repo as of `375c5a6`.

---

## The read

The platform is shippable. The company is not.

| | State | Note |
|---|---|---|
| Platform | Shippable | 137 tests / 84% coverage / 34 endpoints, RLS multi-tenancy, append-only audit, httpOnly sessions, rate limiting, live CI |
| Content | **0 of 106 verified** | Every template is `DRAFT_UNVERIFIED`; the seed meta itself requires CS/CA sign-off before production use |
| Customers | 0 | No pilots or discovery calls on record |
| Liability cover | None | No sign-off, no ToS, no professional indemnity |

Nothing in the next 90 days should be code.

## Why the code isn't the moat

A competent engineer with Claude rebuilds this application layer in 6–8 weeks.
What can't be rebuilt in 8 weeks: 106 obligations a Chief Compliance Officer will
stake their job on, the pipeline that keeps them current as the law moves, and
reference customers. Regis is a regulatory *content* company that happens to have
finished its software first — which is the better half to have finished, since
content is the harder half to buy.

## Why now (this is the pitch, not "AI-native")

RBI's **revised Scale-Based Regulation framework (2026)** requires Middle- and
Upper-Layer NBFCs to maintain a Risk Management Committee, an **independent Chief
Compliance Officer**, and a board member with real banking/finance experience.
Upper-Layer identification moved to a flat ₹1 lakh crore asset threshold, replacing
parametric scoring.

RBI mandated the buyer into existence, at our ICP tier, with a budget line and a
job title. That is the cold-email opening.

The same revision dates our library: 6 templates key on `rbi_layer`, 8 on
`asset_size_min_cr`, and the PRD still describes the ICP as ₹500–5,000 Cr — a band
straddling the ₹1,000 Cr Base/Middle line the framework turns on. Re-cut those
constants. Note what this proves: a framework-level change touches ~a dozen rule
values, not the schema. The engine design held.

## The 90 days

The forcing function: **September quarter-end (Sep 30)**, with the quarterly RBI
return due 15 days later per our own due rule. A compliance calendar proves itself
by surviving a quarter close, not a demo. Every date below works backwards from it.

### Weeks 1–2 (Aug 8–22) — Get a Company Secretary onto the cap table
Gating hire, and not a contractor. Whoever owns content owns the moat, the sales
credibility, and the liability shield — co-founder work, paid in equity.
- Target a practicing CS/CA with live NBFC clients; they arrive carrying the first
  five customer conversations.
- Where: ICSI chapter events, FIDC member networks, signatory names on NBFC filings.
- **Gate:** verify nothing until this person exists. Self-verified content carries
  none of the authority we're buying.

### Weeks 1–4 (Aug 8–Sep 5) — Ten discovery calls, no demo
Run in parallel; independent of the content work. One question: what does this
person do on the 15th of the month, and what does it cost when it slips?
- Target Chief Compliance Officers / CSs at Middle-Layer NBFCs.
- Expect Excel + a shared drive as the real incumbent, not a competitor product.
- Don't demo. Demoing ends the learning.
- **Gate:** if <6 of 10 name deadline tracking as a top-three pain, the wedge is
  wrong — fix that before writing another line.

### Weeks 3–6 (Aug 22–Sep 19) — Verify 25 templates, not 106
The full sweep is a 6-month project that delays the only thing that matters.
- The recurring RBI core (quarterly/monthly returns, ALM, KYC/AML) — the `rbi`
  category is 35 templates; the recurring core is far smaller.
- Companies Act annual filings, GST, TDS — hit by every entity regardless of profile.
- Re-cut layer thresholds against the 2026 SBR revision while the CS is in the file.
- **Gate:** 25 templates signed off by name. ~₹1–2 lakh or equivalent equity time.

### Weeks 6–9 (Sep 19–Oct 10) — Three paid design partners at ₹1 lakh
Paid, not free. Free pilots produce polite feedback and no conversion.
- Onboard each personally. Watch where the generated calendar is wrong.
- Every obligation marked N/A is a content bug — we already log it; review weekly.
- Write the security posture doc now (RLS, audit immutability, cookie sessions,
  India data residency). Asked for in every deal; the work is already done.
- **Gate:** three signed pilots with live calendars before the quarter closes.

### Sep 30 → Oct 15 — Survive a real quarter close
Three NBFCs run the fortnight on Regis and miss nothing. That produces the only
asset that matters at this stage: a customer who will take a reference call.

## Money

**Pricing.** No freemium, no self-serve, no per-seat. Annual contracts, one number.

| Stage | Price | Why it holds |
|---|---|---|
| Design partner | ₹1,00,000 | Signable without procurement; buys real usage plus logo and quotes |
| Middle-Layer NBFC | ₹3–6 lakh/yr | < a quarter of a junior compliance hire, against penalty and supervisory-action exposure; well under enterprise GRC suites |
| Multi-entity group | Per entity | The schema already separates obligations per `entity_id` — a pricing axis we built for free |

**Fundraising.** Not yet. Pitching an unverified library and zero customers prices
badly or not at all. The plan above *is* the prep — three paying NBFCs, a verified
core, a named CS co-founder, and a quarter-close case study make a clean pre-seed.
The same conversation is materially different in November.

**Competition.** Komrisk (Lexplosion, 600+ companies), Ricago (1,500+ acts, 35,000+
obligations, 250+ companies), Legatrix (software + legal advisory). Real, funded,
entrenched.

> **Never compete on obligation count.** 106 vs 35,000 loses every time, and the
> comparison invites the buyer to think about breadth — our weakest axis.

Compete where they're structurally weak: horizontal, breadth-first platforms needing
weeks of consultant configuration, knowing nothing specific about being an NBFC. The
pitch is *"correct for an NBFC on day one, live in thirty minutes, and it tells you
when it isn't sure."*

## Three ways this dies

**1. Taking money on unverified content.** An NBFC misses a return because Regis
didn't list it — supervisory action for them, an existential claim for us from a
customer who can prove reliance. Before the first rupee: named CS/CA sign-off on
every `VERIFIED` template; ToS positioning Regis as a tracking tool, not legal
advice, with the customer's own professionals responsible for filings; professional
indemnity insurance; the provisional banner left visibly intact.

**2. Chasing breadth to look competitive.** Say yes to factory-act and state labour
coverage and in six months we have 400 shallow unverified obligations across four
verticals and have become a worse Ricago. The PRD already names the anti-personas
(§2.3) — re-read it whenever tempted.

**3. Founder-led content past customer ten.** The PRD flags this correctly. One
person hand-curating RBI circulars breaks at ~15 customers, right when stale-content
churn hurts most. **The one feature still worth building** is the regulatory update
pipeline — `legal_updates` is scaffolded with deterministic applicability matching;
turning it into a real sourcing-and-review workflow buys defensibility rather than
surface area.

## What to stop building

Nine modules and 34 endpoints is more product than zero customers can justify.

- Freeze the feature set. No new modules until a paying customer asks twice.
- Deploy what exists: one environment, Postgres with RLS on, India region, Alembic
  migrated. A day of work, then stop.
- Exception: the update pipeline above, and only after the first three pilots are live.

The instinct that produced two unprompted security-review passes pre-revenue is a
real asset and exactly the rigor this vertical rewards. It's currently pointed at the
half of the business that doesn't need it. Point it at the content library: same
standard of proof, applied to obligations rather than endpoints.

---

**Keep the `DRAFT_UNVERIFIED` gate.** The loader that refuses to auto-promote and the
`PROVISIONAL` banner in reports are the most commercially valuable things in the
codebase — they let us sell honestly before the library is complete. Don't flip flags
to make a demo look better.

*Not legal advice. Every regulatory claim here needs the CS's confirmation before it
reaches a customer.*
