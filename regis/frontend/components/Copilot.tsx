"use client";
// Read-only Copilot. Surfaces grounding, confidence, provisional flag and
// escalations exactly as the backend returns them — the UI never hides the gate.
import { useState } from "react";
import { askCopilot, type CopilotTurn } from "@/lib/api";
import { Spinner } from "@/components/ui";

const SUGGESTIONS = ["What's due this week?", "What's overdue?", "What does DNBS-02 require?"];

export default function Copilot() {
  const [q, setQ] = useState("");
  const [turn, setTurn] = useState<CopilotTurn | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const ask = async (query: string) => {
    if (!query.trim()) return;
    setBusy(true); setErr(null);
    try { setTurn(await askCopilot(query)); }
    catch (e) { setErr(e instanceof Error ? e.message : "Copilot unavailable"); }
    finally { setBusy(false); }
  };

  return (
    <aside className="card" style={{ alignSelf: "start", position: "sticky", top: 70 }}>
      <h3 style={{ marginTop: 0 }}>Copilot</h3>
      <p className="muted" style={{ fontSize: 13 }}>
        Read-only. Ask what&apos;s due, what changed, what&apos;s at risk.
      </p>
      <div className="row">
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask(q)} placeholder="Ask a question…" />
        <button className="btn primary" onClick={() => ask(q)} disabled={busy}>
          {busy ? <Spinner /> : "Ask"}
        </button>
      </div>
      <div className="pill-row" style={{ marginTop: 8 }}>
        {SUGGESTIONS.map((s) => (
          <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>
        ))}
      </div>

      {err && <div className="banner err" style={{ marginTop: 12 }}>{err}</div>}

      {turn && (
        <div style={{ marginTop: 14 }}>
          {turn.escalated ? (
            <div className="banner" style={{ background: "rgba(232,179,57,.1)", color: "var(--warn)" }}>
              {String(turn.answer_facts.message)}
            </div>
          ) : (
            <>
              <Facts facts={turn.answer_facts} />
              <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                confidence {turn.confidence} · {turn.citations.length} citation(s)
                {turn.provisional && " · provisional (content unverified)"}
                {turn.grounding.grounded ? " · grounded ✓" : " · ungrounded ✗"}
              </div>
              {turn.scope_note && (
                <div className="muted" style={{ fontSize: 12 }}>{turn.scope_note}</div>
              )}
            </>
          )}
        </div>
      )}
    </aside>
  );
}

function Facts({ facts }: { facts: Record<string, unknown> }) {
  if ("label" in facts && "count" in facts) {
    return <div><b style={{ fontSize: 20 }}>{String(facts.count)}</b> {String(facts.label)}</div>;
  }
  if ("by_status" in facts) {
    const by = facts.by_status as Record<string, number>;
    return (
      <div className="pill-row">
        {Object.entries(by).map(([k, v]) => <span key={k} className="chip">{k}: {v}</span>)}
      </div>
    );
  }
  if ("note" in facts) return <div className="muted">{String(facts.note)}</div>;
  return <pre style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{JSON.stringify(facts, null, 2)}</pre>;
}
