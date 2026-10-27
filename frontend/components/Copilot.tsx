"use client";
// Read-only Copilot.
//
// Rework notes:
//  • The grounding contract is shown as plain language, not as a row of raw
//    fields ("grounded ✓ · confidence 0.97"). Users need to know whether they
//    can act on an answer, not read telemetry.
//  • Unknown fact shapes no longer dump JSON at the user. They render as a
//    readable key/value list, with the raw payload behind a disclosure for
//    anyone who genuinely wants it.
//  • Escalations look like a handoff, not an error.
import { useState } from "react";
import { askCopilot, type CopilotTurn } from "@/lib/api";
import { humanize, statusLabel } from "@/lib/format";
import { IconAlert, IconSparkle, IconArrowRight } from "@/components/icons";
import { Badge, ErrorState, Note, Spinner } from "@/components/ui";

const SUGGESTIONS = [
  "What's due this week?",
  "What's overdue?",
  "What does DNBS-02 require?",
];

export default function Copilot() {
  const [q, setQ] = useState("");
  const [turn, setTurn] = useState<CopilotTurn | null>(null);
  const [asked, setAsked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  const ask = async (query: string) => {
    const text = query.trim();
    if (!text || busy) return;
    setBusy(true); setErr(null); setAsked(text);
    try { setTurn(await askCopilot(text)); }
    catch (e) { setErr(e); setTurn(null); }
    finally { setBusy(false); }
  };

  return (
    <section className="panel" aria-labelledby="copilot-h">
      <div className="panel-head">
        <h3 id="copilot-h" className="row" style={{ gap: 6 }}>
          <IconSparkle size={13} style={{ color: "var(--accent)" }} /> Copilot
        </h3>
        <Badge tone="neutral" title="Copilot can read your compliance data. It can never change it.">
          Read-only
        </Badge>
      </div>

      <div className="panel-body stack-sm">
        <p className="micro muted">
          Answers are drawn from your own calendar and the obligation library.
          It will say so rather than guess when it doesn’t know.
        </p>

        <div className="row" style={{ gap: 6 }}>
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") ask(q); }}
            placeholder="Ask about your obligations…" aria-label="Ask Copilot a question" />
          <button className="btn primary" onClick={() => ask(q)} disabled={busy || !q.trim()}>
            {busy ? <Spinner onDark /> : "Ask"}
          </button>
        </div>

        <div className="row-wrap" style={{ gap: 5 }}>
          {SUGGESTIONS.map((s) => (
            <button key={s} className="chip" onClick={() => { setQ(s); ask(s); }} disabled={busy}>
              {s}
            </button>
          ))}
        </div>

        {busy && (
          <div className="row micro muted" style={{ gap: 7, paddingTop: 4 }}>
            <Spinner /> Checking your calendar…
          </div>
        )}

        {!!err && <ErrorState error={err} title="Copilot is unavailable"
          onRetry={asked ? () => ask(asked) : undefined} />}

        {turn && !busy && (
          <div style={{ borderTop: "1px solid var(--rule)", paddingTop: 11, marginTop: 3 }}>
            {asked && <div className="micro faint" style={{ marginBottom: 7 }}>“{asked}”</div>}
            {turn.escalated ? (
              <Note tone="warn" icon={<IconArrowRight size={14} />}>
                <b>Handed to a human.</b>{" "}
                {String(turn.answer_facts.message ?? "This needs a person, not an assistant.")}
                {turn.escalation_reason && (
                  <div className="micro" style={{ marginTop: 4, opacity: .85 }}>
                    Reason: {humanize(turn.escalation_reason)}
                  </div>
                )}
              </Note>
            ) : (
              <>
                <Facts facts={turn.answer_facts} />
                <Grounding turn={turn} />
              </>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

/* ================================================================== facts */

function Facts({ facts }: { facts: Record<string, unknown> }) {
  if ("label" in facts && "count" in facts) {
    return (
      <div className="row" style={{ alignItems: "baseline", gap: 8 }}>
        <span className="num" style={{ fontSize: 26, fontWeight: 620, letterSpacing: "-.025em" }}>
          {String(facts.count)}
        </span>
        <span className="muted">{String(facts.label)}</span>
      </div>
    );
  }

  if ("by_status" in facts) {
    const by = facts.by_status as Record<string, number>;
    return (
      <div className="stack-sm">
        {Object.entries(by).map(([k, v]) => (
          <div key={k} className="between" style={{ fontSize: 12.5 }}>
            <span className="muted">{statusLabel(k)}</span>
            <span className="num" style={{ fontWeight: 600 }}>{v}</span>
          </div>
        ))}
      </div>
    );
  }

  if ("note" in facts) return <p className="muted" style={{ fontSize: 12.5 }}>{String(facts.note)}</p>;

  // Unknown shape: render readably rather than dumping JSON at the user.
  const entries = Object.entries(facts).filter(([, v]) => v !== null && v !== undefined);
  if (entries.length === 0) {
    return <p className="muted" style={{ fontSize: 12.5 }}>No facts were returned for that question.</p>;
  }
  return (
    <dl className="kv">
      {entries.map(([k, v]) => (
        <div key={k} style={{ display: "contents" }}>
          <dt>{humanize(k)}</dt>
          <dd>{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

/* =============================================================== grounding */

/**
 * Translates the backend's grounding contract into a decision the user can act
 * on: can I rely on this, and what is the caveat?
 */
function Grounding({ turn }: { turn: CopilotTurn }) {
  const g = turn.grounding;
  const reliable = g.grounded && !turn.provisional && turn.confidence >= 0.8;

  return (
    <div style={{ marginTop: 10 }}>
      {!g.grounded && (
        <Note tone="crit" icon={<IconAlert size={14} />}>
          <b>Not grounded in your data.</b> Don’t rely on this without checking the
          obligation itself.
        </Note>
      )}
      {g.grounded && turn.provisional && (
        <Note tone="warn">
          <b>Provisional.</b> Based on obligation-library entries still pending
          content-team verification.
        </Note>
      )}
      {reliable && (
        <div className="micro" style={{ color: "var(--good)" }}>
          Grounded in {turn.citations.length}{" "}
          {turn.citations.length === 1 ? "record" : "records"} from your workspace.
        </div>
      )}
      {turn.scope_note && (
        <div className="micro faint" style={{ marginTop: 5 }}>{turn.scope_note}</div>
      )}
      {turn.citations.length > 0 && (
        <details style={{ marginTop: 7 }}>
          <summary className="micro faint" style={{ cursor: "pointer" }}>
            Sources ({turn.citations.length})
          </summary>
          <ul className="micro muted" style={{ margin: "6px 0 0", paddingLeft: 16 }}>
            {turn.citations.map((c) => <li key={c} className="mono">{c}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}
