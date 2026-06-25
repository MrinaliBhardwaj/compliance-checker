"use client";
// Onboarding (PRD §4): button-driven profile -> AI preview (provenance + gap
// questions + contradictions) -> human-confirmed calendar generation.
import { useRouter } from "next/navigation";
import { useState } from "react";
import { generateCalendar, profilePreview, type ProfilePreview } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/lib/toast";
import { Spinner } from "@/components/ui";

export default function Onboarding() {
  const router = useRouter();
  const { entityId, principal, loading } = useAuth();
  const toast = useToast();
  const [raw, setRaw] = useState<Record<string, unknown>>({
    asset_size: "3000", turnover: "450", deposit_taking: "No", has_listed_debt: "Yes",
    operating_states: ["MH", "KA", "TN", "DL"], branch_count: 22, employee_count: 260,
    gst_registered: "Yes", has_foreign_investment: "Yes",
  });
  const [preview, setPreview] = useState<ProfilePreview | null>(null);
  const [busy, setBusy] = useState(false);

  if (!loading && !principal) { router.replace("/"); return null; }

  const set = (k: string, v: unknown) => setRaw((r) => ({ ...r, [k]: v }));

  const runPreview = async () => {
    setBusy(true);
    try { setPreview(await profilePreview(raw)); }
    catch (e) { toast(e instanceof Error ? e.message : "Failed", "err"); }
    finally { setBusy(false); }
  };
  const confirm = async () => {
    if (!entityId) { toast("No entity selected", "err"); return; }
    setBusy(true);
    try {
      const res = await generateCalendar(entityId, raw);
      toast(`Generated ${res.company_obligations} obligations · ${res.instances} dated items`, "ok");
      router.push("/dashboard");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Generation failed", "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="container" style={{ maxWidth: 880 }}>
      <h1>Compliance profile</h1>
      <p className="muted">AI proposes; you confirm. Derived fields and gaps are flagged before anything commits.</p>

      <div className="card stack" style={{ marginTop: 8 }}>
        <div className="grid-cards" style={{ gridTemplateColumns: "repeat(2,1fr)" }}>
          <F label="Asset size (₹ cr)" v={String(raw.asset_size ?? "")} on={(v) => set("asset_size", v)} />
          <F label="Turnover (₹ cr)" v={String(raw.turnover ?? "")} on={(v) => set("turnover", v)} />
          <F label="Employees" v={String(raw.employee_count ?? "")} on={(v) => set("employee_count", Number(v) || 0)} />
          <F label="Branches" v={String(raw.branch_count ?? "")} on={(v) => set("branch_count", Number(v) || 0)} />
          <YN label="Deposit-taking?" v={raw.deposit_taking} on={(v) => set("deposit_taking", v)} />
          <YN label="Listed debt (NCDs)?" v={raw.has_listed_debt} on={(v) => set("has_listed_debt", v)} />
          <YN label="GST registered?" v={raw.gst_registered} on={(v) => set("gst_registered", v)} />
          <YN label="Foreign investment?" v={raw.has_foreign_investment} on={(v) => set("has_foreign_investment", v)} />
        </div>
        <button className="btn primary" onClick={runPreview} disabled={busy} style={{ justifyContent: "center" }}>
          {busy ? <Spinner /> : "Analyze profile"}
        </button>
      </div>

      {preview && (
        <div className="stack" style={{ marginTop: 16 }}>
          <Card title={`Derived — confirm (${preview.derived_to_confirm.length})`}>
            {preview.derived_to_confirm.map((f) => (
              <div key={f} style={{ padding: "5px 0", borderBottom: "1px solid var(--line)" }}>
                <b>{f}</b>: {String(preview.profile[f])}
                <span className="muted"> · {preview.provenance[f]?.note}</span>
              </div>
            ))}
          </Card>

          {preview.issues.length > 0 && (
            <Card title="Please resolve">
              {preview.issues.map((i, n) => (
                <div key={n} className="banner" style={{ marginTop: 6,
                  background: i.severity === "contradiction" ? "rgba(226,86,77,.1)" : "rgba(232,179,57,.1)",
                  color: i.severity === "contradiction" ? "var(--risk)" : "var(--warn)" }}>
                  [{i.severity}] {i.detail}
                </div>
              ))}
            </Card>
          )}

          <Card title="Quick questions (high-impact first)">
            {preview.gap_questions.slice(0, 6).map((g) => (
              <div key={g.field} style={{ padding: "5px 0", borderBottom: "1px solid var(--line)" }}>
                <span className="chip">+{g.yield}</span> {g.hard ? "key" : "optional"} — {g.question}
              </div>
            ))}
          </Card>

          <button className="btn primary" onClick={confirm} disabled={busy} style={{ justifyContent: "center" }}>
            {busy ? <Spinner /> : "Confirm & generate my calendar"}
          </button>
        </div>
      )}
    </main>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="card"><h3 style={{ marginTop: 0 }}>{title}</h3>{children}</section>;
}
function F({ label, v, on }: { label: string; v: string; on: (v: string) => void }) {
  return <label className="field"><span>{label}</span>
    <input className="input" value={v} onChange={(e) => on(e.target.value)} /></label>;
}
function YN({ label, v, on }: { label: string; v: unknown; on: (v: string) => void }) {
  return <label className="field"><span>{label}</span>
    <select className="input" value={String(v ?? "No")} onChange={(e) => on(e.target.value)}>
      <option>Yes</option><option>No</option>
    </select></label>;
}
