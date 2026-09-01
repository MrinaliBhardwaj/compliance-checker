"use client";
// Compliance profile → applicability preview → confirmed calendar generation.
//
// Rework notes:
//  • Three explicit steps instead of one long scroll. Generating a calendar is
//    the single highest-consequence action in the product — it decides which
//    laws apply to a regulated entity — so it gets a review step, not a button
//    at the bottom of a form.
//  • "Human-confirmed" is now literal: each AI-derived field must be ticked,
//    and contradictions must be acknowledged, before generation is enabled.
//    Previously the design contract was stated in prose and never enforced.
//  • Gap questions are ranked by how many obligations they resolve, so the user
//    can see what answering one more question actually buys them.
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { generateCalendar, profilePreview, type ProfilePreview } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errMessage, useToast } from "@/lib/toast";
import { humanize, pluralize } from "@/lib/format";
import Shell from "@/components/Shell";
import { IconAlert, IconArrowRight, IconCheck, IconCheckCircle, IconSparkle } from "@/components/icons";
import {
  Badge, Checkbox, Definition, Empty, Field, Meter, Note, PermissionDenied, Spinner,
} from "@/components/ui";

type Step = 1 | 2 | 3;

export default function OnboardingPage() {
  return <Shell><Onboarding /></Shell>;
}

function Onboarding() {
  const router = useRouter();
  const { entityId, can, principal } = useAuth();
  const toast = useToast();

  const [step, setStep] = useState<Step>(1);
  const [raw, setRaw] = useState<Record<string, unknown>>({
    asset_size: "3000", turnover: "450", deposit_taking: "No", has_listed_debt: "Yes",
    operating_states: ["MH", "KA", "TN", "DL"], branch_count: 22, employee_count: 260,
    gst_registered: "Yes", has_foreign_investment: "Yes",
  });
  const [preview, setPreview] = useState<ProfilePreview | null>(null);
  const [confirmed, setConfirmed] = useState<Set<string>>(new Set());
  const [ackIssues, setAckIssues] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!can("generate_calendar")) {
    return (
      <div>
        <div className="page-head"><h1>Compliance profile</h1></div>
        <PermissionDenied what="the compliance profile" who="compliance admins"
          action={<a className="btn" href="/dashboard">Back to Today</a>} />
      </div>
    );
  }

  const set = (k: string, v: unknown) => { setRaw((r) => ({ ...r, [k]: v })); setPreview(null); };

  const num = (v: unknown) => String(v ?? "");
  const invalid = useMemo(() => {
    const e: Record<string, string> = {};
    if (!String(raw.asset_size ?? "").trim() || Number(raw.asset_size) <= 0) {
      e.asset_size = "Asset size drives most RBI thresholds — enter a figure in ₹ crore.";
    }
    if (!String(raw.turnover ?? "").trim() || Number(raw.turnover) < 0) {
      e.turnover = "Enter turnover in ₹ crore.";
    }
    return e;
  }, [raw]);

  const runPreview = async () => {
    if (Object.keys(invalid).length > 0) return;
    setBusy(true);
    try {
      const p = await profilePreview(raw);
      setPreview(p);
      setConfirmed(new Set());
      setAckIssues(false);
      setStep(2);
    } catch (e) {
      toast.err("Couldn’t analyse the profile", errMessage(e));
    } finally { setBusy(false); }
  };

  const generate = async () => {
    if (!entityId) { toast.err("No entity selected", "Pick a legal entity in the sidebar first."); return; }
    setBusy(true);
    try {
      const res = await generateCalendar(entityId, raw);
      toast.ok(
        `Calendar generated — ${pluralize(res.instances, "dated obligation")}`,
        `${res.company_obligations} applicable obligations across your profile.`,
      );
      router.push("/obligations");
    } catch (e) {
      toast.err("Generation failed", errMessage(e));
    } finally { setBusy(false); }
  };

  const contradictions = (preview?.issues ?? []).filter((i) => i.severity === "contradiction");
  const derived = preview?.derived_to_confirm ?? [];
  const allConfirmed = derived.every((f) => confirmed.has(f));
  const readyToGenerate = !!preview && allConfirmed && (contradictions.length === 0 || ackIssues);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Compliance profile</h1>
          <p className="lede">
            Regis derives which laws apply to this entity from its scale, structure and
            footprint. You confirm every derived value before any calendar is written.
          </p>
        </div>
        <Badge tone="neutral" title="This entity">
          {principal?.entities.find((e) => e.id === entityId)?.legal_name ?? "Entity"}
        </Badge>
      </div>

      <Stepper step={step} onGo={(s) => { if (s < step || (s === 2 && preview)) setStep(s); }}
        hasPreview={!!preview} />

      {step === 1 && (
        <div className="stack">
          <div className="panel">
            <div className="panel-head">
              <h3>Scale</h3>
              <span className="micro faint">Drives most RBI layer and threshold tests</span>
            </div>
            <div className="panel-body" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 14 }}>
              <Field label="Asset size" required error={invalid.asset_size}
                hint="₹ crore, as at the last audited balance sheet.">
                {(p) => <input className="input" inputMode="decimal" value={num(raw.asset_size)}
                  onChange={(e) => set("asset_size", e.target.value)} {...p} />}
              </Field>
              <Field label="Annual turnover" required error={invalid.turnover} hint="₹ crore.">
                {(p) => <input className="input" inputMode="decimal" value={num(raw.turnover)}
                  onChange={(e) => set("turnover", e.target.value)} {...p} />}
              </Field>
              <Field label="Employees" hint="Headcount drives labour-law obligations.">
                {(p) => <input className="input" inputMode="numeric" value={num(raw.employee_count)}
                  onChange={(e) => set("employee_count", Number(e.target.value) || 0)} {...p} />}
              </Field>
              <Field label="Branches" hint="Used for state-level registrations.">
                {(p) => <input className="input" inputMode="numeric" value={num(raw.branch_count)}
                  onChange={(e) => set("branch_count", Number(e.target.value) || 0)} {...p} />}
              </Field>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h3>Structure</h3>
              <span className="micro faint">Each “yes” can add an entire law to your calendar</span>
            </div>
            <div className="panel-body" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(230px,1fr))", gap: 14 }}>
              <YesNo label="Accepts public deposits" v={raw.deposit_taking} on={(v) => set("deposit_taking", v)}
                hint="Deposit-taking NBFCs carry a materially heavier RBI return burden." />
              <YesNo label="Listed debt (NCDs)" v={raw.has_listed_debt} on={(v) => set("has_listed_debt", v)}
                hint="Brings SEBI LODR obligations into scope." />
              <YesNo label="GST registered" v={raw.gst_registered} on={(v) => set("gst_registered", v)} />
              <YesNo label="Foreign investment" v={raw.has_foreign_investment}
                on={(v) => set("has_foreign_investment", v)}
                hint="Triggers FEMA reporting such as FLA and FC-GPR." />
            </div>
          </div>

          <div className="between">
            <span className="micro faint">Nothing is written until you confirm in step 3.</span>
            <button className="btn primary" onClick={runPreview}
              disabled={busy || Object.keys(invalid).length > 0}>
              {busy ? <Spinner onDark /> : <IconSparkle size={13} />}
              Analyse profile
            </button>
          </div>
        </div>
      )}

      {step === 2 && preview && (
        <div className="stack">
          <div className="panel">
            <div className="panel-head">
              <h3>
                <Definition tip="Share of the profile fields the engine could resolve from what you supplied. Unresolved fields fall back to conservative defaults, which usually means more obligations, not fewer.">
                  Profile completeness
                </Definition>
              </h3>
              <span className="num" style={{ fontWeight: 600 }}>{preview.completeness.pct}%</span>
            </div>
            <div className="panel-body stack-sm">
              <Meter pct={preview.completeness.pct}
                tone={preview.completeness.pct >= 80 ? "good" : "warn"} />
              <span className="micro muted">
                {preview.completeness.known} of {preview.completeness.total} fields resolved.
              </span>
            </div>
          </div>

          {contradictions.length > 0 && (
            <div className="panel" style={{ borderColor: "var(--crit-line)" }}>
              <div className="panel-head">
                <h3 className="row" style={{ gap: 6, color: "var(--crit)" }}>
                  <IconAlert size={14} /> Contradictions to resolve
                </h3>
                <Badge tone="crit">{contradictions.length}</Badge>
              </div>
              <div className="panel-body stack-sm">
                {contradictions.map((i, n) => (
                  <Note key={n} tone="crit">
                    <b>{humanize(i.field)}.</b> {i.detail}
                  </Note>
                ))}
                <label className="row" style={{ gap: 8, alignItems: "flex-start", paddingTop: 4 }}>
                  <Checkbox checked={ackIssues} onChange={setAckIssues}
                    label="Acknowledge the contradictions and proceed" />
                  <span className="micro">
                    I understand these contradictions and accept that the generated calendar may be
                    wider or narrower than it should be until they’re corrected.
                  </span>
                </label>
              </div>
            </div>
          )}

          {preview.issues.filter((i) => i.severity !== "contradiction").length > 0 && (
            <div className="panel">
              <div className="panel-head"><h3>Warnings</h3></div>
              <div className="panel-body stack-sm">
                {preview.issues.filter((i) => i.severity !== "contradiction").map((i, n) => (
                  <Note key={n} tone="warn"><b>{humanize(i.field)}.</b> {i.detail}</Note>
                ))}
              </div>
            </div>
          )}

          <div className="panel">
            <div className="panel-head">
              <div>
                <h3>Derived values — confirm each</h3>
                <div className="micro faint" style={{ marginTop: 1 }}>
                  Inferred rather than stated. Each one changes which obligations apply.
                </div>
              </div>
              <Badge tone={allConfirmed ? "good" : "warn"} dot>
                {confirmed.size} of {derived.length} confirmed
              </Badge>
            </div>
            {derived.length === 0 ? (
              <Empty icon={<IconCheckCircle size={16} />} title="Nothing was inferred"
                hint="Every field came directly from what you entered — there is nothing to confirm." />
            ) : (
              <div className="panel-body stack-sm">
                {derived.map((f) => {
                  const prov = preview.provenance[f];
                  const on = confirmed.has(f);
                  return (
                    <div key={f} className="row" style={{
                      gap: 10, alignItems: "flex-start", padding: "9px 10px",
                      border: "1px solid var(--rule)", borderRadius: "var(--r)",
                      background: on ? "var(--good-wash)" : "var(--surface-2)",
                      borderColor: on ? "var(--good-line)" : "var(--rule)",
                    }}>
                      <span style={{ marginTop: 1 }}>
                        <Checkbox checked={on} label={`Confirm ${humanize(f)}`}
                          onChange={(v) => setConfirmed((s) => {
                            const n = new Set(s);
                            if (v) n.add(f); else n.delete(f);
                            return n;
                          })} />
                      </span>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div className="row-wrap" style={{ gap: 7 }}>
                          <b style={{ fontSize: 12.5 }}>{humanize(f)}</b>
                          <span className="tag is-mono">{String(preview.profile[f] ?? "—")}</span>
                          {prov && (
                            <span className="micro faint">
                              {humanize(prov.source)} · {Math.round(prov.confidence * 100)}% confidence
                            </span>
                          )}
                        </div>
                        {prov?.note && <div className="micro muted" style={{ marginTop: 2 }}>{prov.note}</div>}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            {derived.length > 0 && !allConfirmed && (
              <div className="panel-foot">
                <button className="btn sm" onClick={() => setConfirmed(new Set(derived))}>
                  Confirm all {derived.length}
                </button>
                <span className="micro faint" style={{ marginLeft: 8 }}>
                  Only if you’ve actually read them — an auditor may ask.
                </span>
              </div>
            )}
          </div>

          {preview.gap_questions.length > 0 && (
            <div className="panel">
              <div className="panel-head">
                <div>
                  <h3>Answer these to sharpen the calendar</h3>
                  <div className="micro faint" style={{ marginTop: 1 }}>
                    Ranked by how many obligations each one resolves. Optional — unanswered
                    gaps fall back to conservative defaults.
                  </div>
                </div>
              </div>
              <div className="panel-body stack-sm">
                {preview.gap_questions.slice(0, 6).map((g) => (
                  <div key={g.field} className="row" style={{ gap: 10, alignItems: "flex-start" }}>
                    <span className="badge t-accent num" style={{ flex: "none", minWidth: 34, justifyContent: "center" }}>
                      +{g.yield}
                    </span>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 12.5 }}>{g.question}</div>
                      <div className="micro faint">
                        {g.hard ? "Material to applicability" : "Refines detail only"}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="between">
            <button className="btn" onClick={() => setStep(1)}>Back to profile</button>
            <button className="btn primary" onClick={() => setStep(3)} disabled={!readyToGenerate}
              title={!readyToGenerate ? "Confirm every derived value first" : undefined}>
              Review and generate <IconArrowRight size={13} />
            </button>
          </div>
          {!readyToGenerate && (
            <div className="micro faint" style={{ textAlign: "right" }}>
              {!allConfirmed
                ? `Confirm the remaining ${derived.length - confirmed.size} derived ${derived.length - confirmed.size === 1 ? "value" : "values"} to continue.`
                : "Acknowledge the contradictions to continue."}
            </div>
          )}
        </div>
      )}

      {step === 3 && preview && (
        <div className="stack">
          <Note tone="warn">
            <b>This writes your compliance calendar.</b> Regis will create every applicable
            obligation and its dated instances for this entity. Existing items are reconciled,
            not duplicated — but obligations that no longer apply will be removed.
          </Note>

          <div className="panel">
            <div className="panel-head"><h3>What you’re confirming</h3></div>
            <div className="panel-body">
              <dl className="kv">
                <dt>Entity</dt>
                <dd>{principal?.entities.find((e) => e.id === entityId)?.legal_name ?? "—"}</dd>
                <dt>Profile completeness</dt>
                <dd>{preview.completeness.pct}% ({preview.completeness.known} of {preview.completeness.total} fields)</dd>
                <dt>Derived values</dt>
                <dd className="row" style={{ gap: 6 }}>
                  <IconCheck size={13} style={{ color: "var(--good)" }} />
                  All {derived.length} confirmed by you
                </dd>
                <dt>Unresolved issues</dt>
                <dd>
                  {contradictions.length === 0
                    ? <span style={{ color: "var(--good)" }}>None</span>
                    : <span style={{ color: "var(--crit)" }}>
                        {pluralize(contradictions.length, "contradiction")}, acknowledged
                      </span>}
                </dd>
              </dl>
            </div>
            <div className="panel-foot">
              Generation is recorded in the audit trail against your account, with the
              obligation-library version used.
            </div>
          </div>

          <div className="between">
            <button className="btn" onClick={() => setStep(2)} disabled={busy}>Back to review</button>
            <button className="btn primary lg" onClick={generate} disabled={busy}>
              {busy ? <Spinner onDark /> : <IconCheck size={14} />}
              Generate my compliance calendar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ================================================================= pieces */

function Stepper({ step, onGo, hasPreview }:
  { step: Step; onGo: (s: Step) => void; hasPreview: boolean }) {
  const steps: { n: Step; label: string; sub: string }[] = [
    { n: 1, label: "Profile", sub: "Tell us about the entity" },
    { n: 2, label: "Review", sub: "Confirm what was derived" },
    { n: 3, label: "Generate", sub: "Write the calendar" },
  ];
  return (
    <ol style={{
      listStyle: "none", margin: "0 0 20px", padding: 0, display: "grid",
      gridTemplateColumns: `repeat(${steps.length}, 1fr)`,
      border: "1px solid var(--rule)", borderRadius: "var(--r-lg)",
      overflow: "hidden", background: "var(--surface)",
    }}>
      {steps.map((s) => {
        const done = s.n < step;
        const current = s.n === step;
        const reachable = s.n < step || (s.n === 2 && hasPreview);
        return (
          <li key={s.n} style={{ borderLeft: s.n === 1 ? 0 : "1px solid var(--rule)" }}>
            <button
              onClick={() => reachable && onGo(s.n)}
              disabled={!reachable}
              aria-current={current ? "step" : undefined}
              style={{
                width: "100%", textAlign: "left", padding: "11px 14px", border: 0,
                background: current ? "var(--surface-2)" : "transparent",
                cursor: reachable ? "pointer" : "default", display: "flex", gap: 10,
                alignItems: "center", opacity: current || done ? 1 : .55,
              }}>
              <span aria-hidden="true" style={{
                width: 20, height: 20, borderRadius: "50%", flex: "none", display: "grid",
                placeItems: "center", fontSize: 10.5, fontWeight: 700,
                background: done ? "var(--good)" : current ? "var(--ink)" : "var(--surface-3)",
                color: done || current ? "var(--ink-on)" : "var(--ink-3)",
              }}>{done ? <IconCheck size={11} /> : s.n}</span>
              <span style={{ minWidth: 0 }}>
                <span style={{ display: "block", fontWeight: current ? 650 : 550, fontSize: 12.5 }}>
                  {s.label}
                </span>
                <span className="micro faint truncate" style={{ display: "block" }}>{s.sub}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function YesNo({ label, v, on, hint }:
  { label: string; v: unknown; on: (v: string) => void; hint?: string }) {
  const val = String(v ?? "No");
  return (
    <div className="field">
      <span className="lbl">{label}</span>
      <div className="segmented" role="group" aria-label={label}>
        {["Yes", "No"].map((opt) => (
          <button key={opt} type="button" aria-pressed={val === opt} onClick={() => on(opt)}>
            {opt}
          </button>
        ))}
      </div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}
