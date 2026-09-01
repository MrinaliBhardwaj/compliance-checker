"use client";
// Audit trail — the evidence trail for auditors and RBI inspection.
//
// Rework notes:
//  • Quick date ranges (7 / 30 / 90 days) alongside the explicit from/to inputs.
//    "What happened this week" was previously two date-picker interactions.
//  • Reasons recorded against an action are shown inline. The reason a filing
//    was rejected or an evidence gate overridden is the most audit-relevant
//    field in the record, and it was invisible.
//  • Overrides and blocked actions are visually distinct — they're what an
//    inspector looks for first.
//  • Keyset paging keeps its position label, and filters no longer silently
//    reset the offset out from under you.
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { getAuditCatalog, listAudit, type AuditEvent } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, humanize, relativeTime } from "@/lib/format";
import Shell from "@/components/Shell";
import { IconAlert, IconSearch, IconShield, IconX } from "@/components/icons";
import {
  Avatar, Badge, Empty, ErrorState, PermissionDenied, SkeletonRows, useDebounced,
} from "@/components/ui";
import type { Tone } from "@/lib/format";

const PAGE = 50;

export default function AuditPage() {
  return <Shell><Audit /></Shell>;
}

/** Tone by consequence: blocked and override events must stand out. */
function toneFor(e: AuditEvent): Tone {
  if (e.action.endsWith("_blocked")) return "crit";
  if (e.meta?.override_evidence) return "crit";
  if (e.action.includes("removed")) return "warn";
  if (e.action === "instance_status_change") {
    const to = String(e.meta?.to ?? "");
    return to === "completed" ? "good" : to === "not_applicable" ? "neutral" : "info";
  }
  if (/uploaded|linked|accepted|generated|invited/.test(e.action)) return "good";
  return "neutral";
}

function detailOf(e: AuditEvent): string | null {
  const m = e.meta || {};
  const s = (k: string) => (m[k] == null ? null : String(m[k]));
  switch (e.action) {
    case "instance_status_change": {
      const from = s("from"), to = s("to");
      const base = from && to ? `${humanize(from)} → ${humanize(to)}` : s("action");
      return m.override_evidence ? `${base} · evidence gate overridden` : base;
    }
    case "member_role_changed":
      return s("from") && s("to") ? `${humanize(s("from")!)} → ${humanize(s("to")!)}` : null;
    case "member_removed": {
      const n = s("reassigned_instances");
      return n && n !== "0" ? `${n} obligation(s) reassigned` : "no obligations to reassign";
    }
    case "member_invited": return s("role") ? humanize(s("role")!) : null;
    case "document_upload_blocked":
    case "document_link_blocked": return s("reason") ? humanize(s("reason")!) : null;
    case "document_classified":
    case "document_classified_manual": return s("doc_type");
    case "legal_update_reviewed": return s("status") ? humanize(s("status")!) : null;
    case "calendar_generated": return s("library_version") ? `library ${s("library_version")}` : null;
    default: return null;
  }
}

function Audit() {
  const { can } = useAuth();
  const allowed = can("view_audit");

  const [action, setAction] = useState("");
  const [qInput, setQInput] = useState("");
  const q = useDebounced(qInput, 200);
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [offset, setOffset] = useState(0);

  const catalog = useQuery({
    queryKey: ["audit-catalog"], queryFn: getAuditCatalog, enabled: allowed, staleTime: 600_000,
  });
  const page = useQuery({
    queryKey: ["audit", { action, q, since, until, offset }],
    queryFn: () => listAudit({
      action: action || undefined, q: q || undefined,
      since: since || undefined, until: until || undefined, limit: PAGE, offset,
    }),
    enabled: allowed,
  });

  const events = page.data?.events ?? [];
  const hasMore = page.data?.has_more ?? false;
  const optionGroups = useMemo(
    () => Object.entries(catalog.data?.groups ?? {}), [catalog.data]);

  // Any filter change invalidates the current page position.
  const change = (fn: () => void) => { fn(); setOffset(0); };

  const quickRange = (days: number | null) => change(() => {
    if (days === null) { setSince(""); setUntil(""); return; }
    const d = new Date();
    d.setDate(d.getDate() - days);
    setSince(d.toISOString().slice(0, 10));
    setUntil("");
  });

  const activeDays = useMemo(() => {
    if (!since || until) return null;
    const diff = Math.round((Date.now() - new Date(since).getTime()) / 86_400_000);
    return [7, 30, 90].includes(diff) ? diff : null;
  }, [since, until]);

  const filtersActive = !!(action || q || since || until);

  if (!allowed) {
    return (
      <div>
        <div className="page-head"><h1>Audit trail</h1></div>
        <PermissionDenied what="the audit trail" who="compliance admins and heads"
          action={<a className="btn" href="/dashboard">Back to Today</a>} />
      </div>
    );
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Audit trail</h1>
          <p className="lede">
            Every state change in this workspace, append-only and immutable — your
            evidence trail for auditors and RBI inspection. Nothing here can be edited
            or deleted, including by an admin.
          </p>
        </div>
        <Badge tone="neutral" title="Records are written once and never modified">
          <IconShield size={12} /> Append-only
        </Badge>
      </div>

      <div className="panel">
        <div className="toolbar">
          <span style={{ position: "relative", flex: 1, minWidth: 200, maxWidth: 300, display: "flex" }}>
            <IconSearch size={13} style={{
              position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)",
              color: "var(--ink-3)", pointerEvents: "none",
            }} />
            <input className="input" style={{ paddingLeft: 27 }} value={qInput}
              placeholder="Actor, item or action…" aria-label="Search the audit trail"
              onChange={(e) => change(() => setQInput(e.target.value))} />
            {qInput && (
              <button className="btn icon ghost" aria-label="Clear search"
                style={{ position: "absolute", right: 2, top: "50%", transform: "translateY(-50%)" }}
                onClick={() => change(() => setQInput(""))}><IconX size={12} /></button>
            )}
          </span>

          <label><span className="sr-only">Filter by action</span>
            <select className="input" style={{ width: "auto", maxWidth: 240 }} value={action}
              onChange={(e) => change(() => setAction(e.target.value))}>
              <option value="">All actions</option>
              {optionGroups.map(([group, actions]) => (
                <optgroup key={group} label={humanize(group)}>
                  {actions.map((a) => (
                    <option key={a} value={a}>{catalog.data?.labels[a] ?? humanize(a)}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>

          <div className="segmented" role="group" aria-label="Quick date range">
            {([[7, "7d"], [30, "30d"], [90, "90d"], [null, "All"]] as const).map(([d, label]) => (
              <button key={label} aria-pressed={activeDays === d || (d === null && !since && !until)}
                onClick={() => quickRange(d)}>{label}</button>
            ))}
          </div>

          <span className="spacer" />

          <label className="row" style={{ gap: 5 }}>
            <span className="micro faint">From</span>
            <input className="input" type="date" style={{ width: "auto" }} value={since}
              onChange={(e) => change(() => setSince(e.target.value))} />
          </label>
          <label className="row" style={{ gap: 5 }}>
            <span className="micro faint">To</span>
            <input className="input" type="date" style={{ width: "auto" }} value={until}
              onChange={(e) => change(() => setUntil(e.target.value))} />
          </label>
          {filtersActive && (
            <button className="btn sm ghost" onClick={() => change(() => {
              setAction(""); setQInput(""); setSince(""); setUntil("");
            })}>Clear</button>
          )}
        </div>

        {page.isLoading && <SkeletonRows rows={12} cols={5} />}
        {page.isError && <div style={{ padding: 14 }}>
          <ErrorState error={page.error} onRetry={page.refetch} />
        </div>}

        {page.data && events.length === 0 && (
          <Empty icon={<IconSearch size={16} />} title="No matching events"
            hint={filtersActive
              ? "Widen the date range or clear a filter."
              : "Activity appears here as soon as anyone acts in this workspace."}
            action={filtersActive
              ? <button className="btn" onClick={() => change(() => {
                  setAction(""); setQInput(""); setSince(""); setUntil("");
                })}>Clear filters</button>
              : undefined} />
        )}

        {page.data && events.length > 0 && (
          <div className="tbl-wrap">
            <table className="tbl">
              <caption className="sr-only">Audit events</caption>
              <thead>
                <tr>
                  <th className="tight">When</th>
                  <th>Action</th>
                  <th className="tight">Who</th>
                  <th>Item</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => {
                  const tone = toneFor(e);
                  const detail = detailOf(e);
                  const reason = typeof e.meta?.reason === "string" ? e.meta.reason : null;
                  const flagged = tone === "crit";
                  return (
                    <tr key={e.id} data-urgency={flagged ? "overdue" : undefined}>
                      <td className="tight rail">
                        <div className="num micro">{relativeTime(e.created_at)}</div>
                        <div className="micro faint nowrap">
                          <time dateTime={e.created_at}>{fmtDateTime(e.created_at)}</time>
                        </div>
                      </td>
                      <td>
                        <span className="row" style={{ gap: 6 }}>
                          {flagged && <IconAlert size={12} style={{ color: "var(--crit)", flex: "none" }} />}
                          <Badge tone={tone} dot>{e.action_label}</Badge>
                        </span>
                      </td>
                      <td className="tight">
                        <span className="row" style={{ gap: 6 }}>
                          <Avatar label={e.actor_name} size={19} />
                          <span className="truncate" style={{ maxWidth: 130 }}>{e.actor_name}</span>
                        </span>
                      </td>
                      <td>
                        <span className="truncate" style={{ display: "block", maxWidth: 260 }}>
                          {e.target_label || <span className="faint">—</span>}
                        </span>
                        {e.entity_type && (
                          <span className="micro faint">{humanize(e.entity_type)}</span>
                        )}
                      </td>
                      <td>
                        {detail && <div className="micro">{detail}</div>}
                        {reason && (
                          <div className="micro" style={{
                            marginTop: 3, paddingLeft: 7, borderLeft: "2px solid var(--rule-2)",
                            color: "var(--ink-2)", maxWidth: 320,
                          }}>“{reason}”</div>
                        )}
                        {!detail && !reason && <span className="faint">—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {page.data && events.length > 0 && (
          <div className="panel-foot between">
            <span className="num">
              Showing {offset + 1}–{offset + events.length}
              {!hasMore && offset === 0 ? " (all events)" : ""}
            </span>
            <span className="row" style={{ gap: 8 }}>
              <button className="btn sm" disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE))}>← Newer</button>
              <button className="btn sm" disabled={!hasMore}
                onClick={() => setOffset(offset + PAGE)}>Older →</button>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
