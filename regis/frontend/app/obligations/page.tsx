"use client";
// Obligation tracker: filterable list with status/risk/due, click-through to the
// detail drawer (evidence + Maker-Checker). Preparers are scoped server-side.
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { getInstances, type Instance } from "@/lib/api";
import Shell from "@/components/Shell";
import ObligationDrawer from "@/components/ObligationDrawer";
import { Empty, ErrorState, Loading, RiskBadge, StatusBadge, fmtDate } from "@/components/ui";

const STATUSES = ["all", "overdue", "pending", "in_progress", "ready_for_review", "completed", "not_applicable"];

export default function ObligationsPage() {
  return (
    <Shell>
      <Suspense fallback={<Loading />}>
        <Tracker />
      </Suspense>
    </Shell>
  );
}

function Tracker() {
  const params = useSearchParams();
  const [status, setStatus] = useState(params.get("status") ?? "all");
  const [category, setCategory] = useState("all");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(params.get("open"));

  const all = useQuery({ queryKey: ["tracker"], queryFn: () => getInstances({}) });

  const categories = useMemo(() => {
    const set = new Set((all.data ?? []).map((i) => i.category));
    return ["all", ...Array.from(set).sort()];
  }, [all.data]);

  const rows = useMemo(() => {
    let r: Instance[] = all.data ?? [];
    if (status !== "all") r = r.filter((i) => i.status === status);
    if (category !== "all") r = r.filter((i) => i.category === category);
    if (q.trim()) r = r.filter((i) => i.title.toLowerCase().includes(q.toLowerCase()));
    return r;
  }, [all.data, status, category, q]);

  return (
    <div className="stack">
      <div className="between">
        <h1>Obligations</h1>
        <input className="input" style={{ maxWidth: 260 }} placeholder="Search obligations…"
          value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      <div className="stack" style={{ gap: 8 }}>
        <div className="pill-row">
          {STATUSES.map((s) => (
            <button key={s} className={`chip ${status === s ? "on" : ""}`} onClick={() => setStatus(s)}>
              {s === "all" ? "All statuses" : s.replace(/_/g, " ")}
            </button>
          ))}
        </div>
        <div className="pill-row">
          {categories.map((c) => (
            <button key={c} className={`chip ${category === c ? "on" : ""}`} onClick={() => setCategory(c)}>
              {c === "all" ? "All categories" : c}
            </button>
          ))}
        </div>
      </div>

      {all.isLoading && <Loading />}
      {all.isError && <ErrorState error={all.error} onRetry={all.refetch} />}
      {all.data && (
        <div className="card" style={{ padding: 0 }}>
          {rows.length === 0
            ? <Empty title="No obligations match" hint="Adjust the filters above." />
            : (
              <table className="table">
                <thead>
                  <tr><th>Obligation</th><th>Law</th><th>Risk</th><th>Due</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {rows.map((i) => (
                    <tr key={i.id} className="clickable" onClick={() => setOpen(i.id)}>
                      <td>
                        {i.title}{i.state ? ` [${i.state}]` : ""}
                        {i.form_reference && <span className="muted"> · {i.form_reference}</span>}
                      </td>
                      <td className="muted">{i.category}</td>
                      <td><RiskBadge level={i.risk_level} /></td>
                      <td>{fmtDate(i.due_date)}{i.working_day_adjusted ? " *" : ""}</td>
                      <td><StatusBadge status={i.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          <div className="muted" style={{ padding: "8px 12px", fontSize: 12 }}>
            {rows.length} shown · “*” = shifted to a working day
          </div>
        </div>
      )}

      <ObligationDrawer instanceId={open} onClose={() => setOpen(null)} />
    </div>
  );
}
