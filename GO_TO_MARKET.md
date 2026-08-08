# Go-to-Market — Regis

Status: **proposed, not decided.** This is a plan, not policy. Promote anything you
commit to into `DECISIONS.md` in the usual format.

Written 2026-08-08 against the repo as of `375c5a6`. **Rev. 2.**

Rev. 2 corrects three regulatory claims in rev. 1: the CCO mandate dates from the RBI
circular of **11 April 2022**, not 2026; the ₹1 lakh crore Upper-Layer threshold is a
**draft** proposal, not in force; and the Amendment Directions of 29 April 2026
concern **Type I registration exemption and CoR surrender**, not Base/Middle/Upper
layer thresholds. Regulatory context here is assembled from legal-press analysis —
`rbi.org.in` was not reachable from the authoring environment. **Re-derive every
figure from the primary notification before it reaches a customer.**

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

## Why now — the honest version

**Do not use the CCO framing.** RBI's circular on the *Compliance Function and Role
of the Chief Compliance Officer*, covering NBFC-UL and NBFC-ML, is dated **11 April
2022**. The buyer has held that title for four years. An opener claiming the role is
newly mandated tells a CCO in one line that we don't know the sector — disqualifying
in compliance sales. (Also not in force: the ₹1 lakh crore Upper-Layer threshold —
that is a *draft* proposal.)

### What 29 April 2026 actually did

RBI issued the *NBFC – Registration, Exemptions and Framework for Scale Based
Regulation* **Amendment** Directions, 2026, amending the 2025 Directions of the same
name, in force **1 July 2026**. The title carries "Scale Based Regulation," which is
why secondary summaries read it as a layer revision. It is not one. It:

- creates an **Unregistered Type I NBFC** category;
- exempts entities below ₹1,000 Cr with no public funds and no customer interface
  from CoR registration (s.45-IA) and reserve fund (s.45-IC);
- opens a one-time **CoR surrender window closing 30 September 2026**.

Direction of travel is *out of* the perimeter, not up into heavier layers. Nobody was
pushed into Middle Layer on 1 July. The entities in motion are sub-₹1,000 Cr captives
and group finance companies deregistering — already excluded by the PRD's
anti-personas. They are churn, not prospects. **Do not chase the 30 September CoR
deadline; it is not our deadline.**

Quieter consequence worth having: the registered universe is pruned from the bottom,
so the remainder skews toward public funds and customer interface — real burden, and
the ₹3–6 lakh price point. Fewer in count, purer in fit.

### The actual catalyst

Weaker than we'd like, and worth stating plainly rather than manufacturing a third
framing — the third would be wrong too. **There is no dramatic regulatory event
minting new buyers this quarter.** What exists is enforcement getting specific:

> On **9 March 2026** RBI imposed a **₹2.70 lakh penalty on Manappuram Finance** for
> paying certain KMPs their entire variable compensation upfront with no deferral,
> contrary to the Governance Directions 2025 (notified 28 November 2025). Named
> entity, named failure mode, dated.

Use it as evidence RBI now penalises governance *process* — **not** as a claim Regis
would have caught it. Regis does not track compensation deferral, and a CCO will spot
that overclaim instantly. Same discipline that killed the CCO line.

Underneath everything sits the unglamorous reason that is probably the real pitch:
**the incumbent is Excel**, and quarter-close hurts every ninety days regardless.

### The library is stale; the pipeline is the fix

6 templates key on `rbi_layer`, 8 on `asset_size_min_cr`, and the PRD still says
₹500–5,000 Cr. Re-derive every threshold from the primary notification text on
rbi.org.in — not from a summary, and not from this document.

**Design constraint:** neither `rbi.org.in` nor the law-firm PDF analysing these
Directions was reachable from the authoring environment (blocked by network egress
proxy). Two of three regulatory claims in rev. 1 came from secondary summaries and
one was flatly wrong. The lesson for `legal_updates`: **the update pipeline cannot be
a scraper that fetches RBI on demand.** It has to be a human-in-the-loop review queue
— notification PDFs mirrored into the repo, a named reviewer per template, a dated
sign-off. Slower, less impressive in a demo, and precisely what a competitor with
Claude and six weeks cannot reproduce.

## The 90 days

The forcing function: **September quarter-end (Sep 30)**, with the quarterly RBI
return due 15 days later per our own due rule. A calendar proves itself by surviving
a close — which means **users inside the product before 30 September, not signed
after it.** Rev. 1 put pilots at 10 October; that would have had them watching the
close from outside, selling a claim instead of a proof. Everything is pulled forward.

### Weeks 1–2 (Aug 8–22) — Buy content review; don't wait to recruit it
We cannot verify a single template ourselves, so this gates everything downstream —
which is exactly why it must not depend on someone believing in the company first.
Thirteen days to find a CS willing to stake their registration on a pre-revenue,
student-founded product is a hope, not a plan.
- **Primary path — a paid engagement** with a practising CS at per-template review
  rates. Slower, costs cash, requires no belief and no equity negotiation.
  Purchasable this week.
- **Parallel, longer horizon — the co-founder.** Whoever owns content permanently
  owns the moat and the liability shield; that is equity work, run over months, off
  the critical path. A reviewer already paid to work on the library is a far warmer
  co-founder prospect than a stranger.
- Where: ICSI chapter networks, FIDC member firms, signatory names on NBFC filings.
- **Gate:** review capacity contracted by 22 Aug. Not a person convinced — an
  engagement signed.

### Weeks 1–4 (Aug 8–Sep 5) — Ten discovery calls, no demo
Run in parallel; independent of the content work. One question: what does this
person do on the 15th of the month, and what does it cost when it slips?
- Target CCOs / CSs at registered NBFCs *with* public funds or customer interface —
  the ones staying inside the perimeter after 1 July.
- Expect Excel + a shared drive as the real incumbent, not a competitor product.
- Don't demo. Demoing ends the learning.
- **Gate:** if <6 of 10 name deadline tracking as a top-three pain, the wedge is
  wrong — fix that before writing another line.

### Weeks 3–5 (Aug 22–Sep 12) — Verify 25 templates, not 106
Compressed from rev. 1, because this now gates live pilots rather than trailing them.
- The recurring RBI core (quarterly/monthly returns, ALM, KYC/AML) — the `rbi`
  category is 35 templates; the genuinely recurring set is far smaller.
- Companies Act annual filings, GST, TDS — hit by every entity regardless of profile.
- Re-derive `rbi_layer` and `asset_size_min_cr` from primary notification text while
  the reviewer is already in the file.
- **Gate:** 25 templates signed off by name, with the source notification cited per
  template.

### By Sep 15 — Three pilots live, free if that's what it takes
The immovable date. Free vs. paid is a pricing question; being inside the product on
30 September is an existential one. If charging costs two weeks, don't charge — take
the logo and the usage, invoice in October once the close has proved the calendar.
- Onboard each personally. Watch where the generated calendar is wrong.
- Every obligation marked N/A is a content bug — review it *daily* through the close.
- Write the security posture doc now (RLS, audit immutability, cookie sessions,
  India data residency). Asked for in every deal; the work is already done.
- **Gate:** three live calendars with real obligations and real owners, before the
  quarter ends.

### Sep 30 → Oct 15 — The close happens inside the product
Three NBFCs run the fortnight on Regis and miss nothing. That produces the only
asset that matters at this stage: a customer who will take a reference call. **Then**
convert to paid, off a proof rather than a promise.

## Money

**Pricing.** No freemium, no self-serve, no per-seat. Annual contracts, one number.

| Stage | Price | Why it holds |
|---|---|---|
| Design partner (Sep free → Oct invoice) | ₹0 → ₹1,00,000 | Getting inside the September close outranks collecting in September. Invoicing in October off a proved calendar is a stronger position than a promise |
| Middle-Layer NBFC | ₹3–6 lakh/yr | < a quarter of a junior compliance hire, against penalty and supervisory-action exposure; well under enterprise GRC suites |
| Multi-entity group | Per entity | The schema already separates obligations per `entity_id` — a pricing axis we built for free |

**Fundraising.** Not yet. Pitching an unverified library and zero customers prices
badly or not at all. The plan above *is* the prep — three NBFCs through a real close,
a verified core, a named reviewer on the content, a case study.

As a student founder the realistic first money is an accelerator or angel round, not
institutional pre-seed, and the credibility gap closes via the CS's name on the
content and a customer who takes the reference call — not via the founder's CV. Pilot
revenue at ₹1 lakh a logo funds the next round of template verification; bootstrapping
off the pilots is a live option, not a consolation prize.

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
