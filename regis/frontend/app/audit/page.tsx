"use client";
// Audit trail (PRD §3 job-to-be-done: "evidence trail for auditors/RBI inspection,
// review what changed"). Read-only projection over the append-only log. Admin + head
// only — the route, nav entry, and backend all enforce the same role gate.
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  getAuditCatalog, listAudit, type AuditEvent,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import Shell from "@/components/Shell";
import { Empty, ErrorState, Loading } from "@/components/ui";

const PAGE = 50;

export default function AuditPage() {
  return <Shell><Audit /></Shell>;
}

// Action → badge color, reusing the status palette already in globals.css.
function toneFor(action: string): string {
  if (action.endsWith("_blocked")) return "overdue";
  if (action.includes("removed")) return "not_applicable";
  if (action === "instance_status_change") return "ready_for_review";
  if (action.includes("uploaded") || action.includes("linked")
    || action.includes("accepted") || action.includes("generated")) return "completed";
  return "in_progress";
}

function fmtWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString("en-IN", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

// Compact, human detail string from the row's meta (shapes vary per action).
function detail(e: AuditEvent): string | null {
  const m = e.meta || {};
  const s = (k: string) => (m[k] == null ? null : String(m[k]));
  switch (e.action) {
    case "instance_status_change": {
      const verb = s("action"); const from = s("from"); const to = s("to");
      const base = from && to ? `${from} → ${to}` : verb;
      return m.override_evidence ? `${base} · evidence override` : base;
    }
    case "member_role_changed":
      return s("from") && s("to") ? `${s("from")} → ${s("to")}` : null;
    case "member_removed": {
      const n = s("reassigned_instances");
      return n ? `${n} obligation(s) reassigned` : "no obligations to reassign";
    }
    case "member_invited":
      return s("role");
    case "document_upload_blocked":
    case "document_link_blocked":
      return s("reason");
    case "document_classified":
    case "document_classified_manual":
      return s("doc_type");
    case "legal_update_reviewed":
      return s("status");
    case "calendar_generated":
      return s("library_version") ? `library ${s("library_version")}` : null;
    default:
      return null;
  }
}

function Audit() {
  const { can } = useAuth();
  const [action, setAction] = useState("");
  const [q, setQ] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [offset, setOffset] = useState(0);

  const allowed = can("view_audit");
  const catalog = useQuery({
    queryKey: ["audit-catalog"], queryFn: getAuditCatalog, enabled: allowed,
  });
  const page = useQuery({
    queryKey: ["audit", { action, q, since, until, offset }],
    queryFn: () => listAudit({
      action: action || undefined, q: q || undefined,
      since: since || undefined, until: until || undefined, limit: PAGE, offset,
    }),
    enabled: allowed,
  });

  const groups = catalog.data?.groups ?? {};
  const events = page.data?.events ?? [];
  const hasMore = page.data?.has_more ?? false;

  const resetTo = (fn: () => void) => { fn(); setOffset(0); };

  const showingFrom = events.length ? offset + 1 : 0;
  const showingTo = offset + events.length;

  const optionGroups = useMemo(() => Object.entries(groups), [groups]);

  if (!allowed) {
    return (
      <div className="stack">
        <h1>Audit trail</h1>
        <Empty title="Restricted" hint="Only an admin or head can view the audit trail." />
      </div>
    );
  }

  return (
    <div className="stack">
      <h1>Audit trail</h1>
      <p className="muted">
        Every state change, append-only and immutable — your evidence trail for
        auditors and RBI inspection.
      </p>

      <div className="card">
        <div className="row" style={{ flexWrap: "wrap", alignItems: "flex-end", gap: 12 }}>
          <label className="field" style={{ minWidth: 200 }}><span>Action</span>
            <select className="input" value={action}
              onChange={(e) => resetTo(() => setAction(e.target.value))}>
              <option value="">All actions</option>
              {optionGroups.map(([group, actions]) => (
                <optgroup key={group} label={group}>
                  {actions.map((a) => (
                    <option key={a} value={a}>{catalog.data?.labels[a] ?? a}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          <label className="field" style={{ flex: 1, minWidth: 180 }}><span>Search</span>
            <input className="input" value={q} placeholder="actor, item, or action…"
              onChange={(e) => resetTo(() => setQ(e.target.value))} />
          </label>
          <label className="field"><span>From</span>
            <input className="input" type="date" value={since}
              onChange={(e) => resetTo(() => setSince(e.target.value))} />
          </label>
          <label className="field"><span>To</span>
            <input className="input" type="date" value={until}
              onChange={(e) => resetTo(() => setUntil(e.target.value))} />
          </label>
          {(action || q || since || until) && (
            <button className="btn sm ghost"
              onClick={() => resetTo(() => { setAction(""); setQ(""); setSince(""); setUntil(""); })}>
              Clear
            </button>
          )}
        </div>
      </div>

      {page.isLoading && <Loading label="Loading audit trail…" />}
      {page.isError && <ErrorState error={page.error} onRetry={page.refetch} />}
      {page.data && (events.length === 0 ? (
        <Empty title="No matching events"
          hint="Try widening the date range or clearing filters." />
      ) : (
        <>
          <div className="card" style={{ padding: 0 }}>
            <table className="table">
              <thead>
                <tr><th>When</th><th>Action</th><th>Who</th><th>Item</th><th>Details</th></tr>
              </thead>
              <tbody>
                {events.map((e) => {
                  const d = detail(e);
                  return (
                    <tr key={e.id}>
                      <td style={{ whiteSpace: "nowrap" }} className="muted">{fmtWhen(e.created_at)}</td>
                      <td>
                        <span className={`badge ${toneFor(e.action)}`}>
                          <span className="dot" />{e.action_label}
                        </span>
                      </td>
                      <td>{e.actor_name}</td>
                      <td>{e.target_label || <span className="muted">—</span>}</td>
                      <td className="muted">{d || ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="between">
            <span className="muted" style={{ fontSize: 12 }}>Showing {showingFrom}–{showingTo}</span>
            <div className="row" style={{ gap: 8 }}>
              <button className="btn sm ghost" disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE))}>← Newer</button>
              <button className="btn sm ghost" disabled={!hasMore}
                onClick={() => setOffset(offset + PAGE)}>Older →</button>
            </div>
          </div>
        </>
      ))}
    </div>
  );
}
