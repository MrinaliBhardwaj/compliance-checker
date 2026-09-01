"use client";
// Board-ready compliance report.
//
// Rework notes:
//  • Permission is now a *state*, not a silent redirect. A preparer who follows
//    a link here is told why they can't see it instead of being bounced to the
//    dashboard, which reads as a bug.
//  • The provisional banner is the first thing on the page when it applies —
//    exporting an unverified report into a board pack without knowing it is
//    unverified is the failure mode worth designing against.
//  • Section tables carry relative dates and risk, matching the tracker, so the
//    export and the app tell the same story.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { downloadReport, getReport } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errMessage, useToast } from "@/lib/toast";
import { fmtDate, fmtDateShort, pluralize, relativeDue } from "@/lib/format";
import Shell from "@/components/Shell";
import { IconCheckCircle, IconDownload, IconFile } from "@/components/icons";
import {
  Badge, Definition, Empty, ErrorState, Note, PermissionDenied, RiskMeter,
  Skeleton, SkeletonMetrics, SkeletonRows, Spinner, StatusBadge,
} from "@/components/ui";

export default function ReportsPage() {
  return <Shell><Reports /></Shell>;
}

function Reports() {
  const { can } = useAuth();
  const toast = useToast();
  const [exporting, setExporting] = useState<"pdf" | "html" | null>(null);
  const allowed = can("export_reports");

  const report = useQuery({ queryKey: ["report"], queryFn: getReport, enabled: allowed });

  if (!allowed) {
    return (
      <div>
        <div className="page-head"><h1>Reports</h1></div>
        <PermissionDenied what="compliance reports" who="compliance admins and heads"
          action={<a className="btn" href="/dashboard">Back to Today</a>} />
      </div>
    );
  }

  const exportAs = async (kind: "pdf" | "html") => {
    setExporting(kind);
    try {
      const blob = await downloadReport(kind);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `compliance-status.${kind}`; a.click();
      URL.revokeObjectURL(url);
      toast.ok(`${kind.toUpperCase()} downloaded`, "Generated from live data as of now.");
    } catch (e) {
      toast.err("Export failed", errMessage(e));
    } finally { setExporting(null); }
  };

  const d = report.data;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Compliance report</h1>
          <p className="lede">
            The standing position, in the form a board or an inspector expects.
            Generated from live data — nothing here is cached.
          </p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn" onClick={() => exportAs("html")} disabled={!!exporting || !d}>
            {exporting === "html" ? <Spinner /> : <IconFile size={13} />} HTML
          </button>
          <button className="btn primary" onClick={() => exportAs("pdf")} disabled={!!exporting || !d}>
            {exporting === "pdf" ? <Spinner onDark /> : <IconDownload size={13} />} Export PDF
          </button>
        </div>
      </div>

      {report.isLoading && (
        <div className="stack">
          <Skeleton h={40} r={8} />
          <SkeletonMetrics />
          <div className="panel"><SkeletonRows rows={6} cols={4} /></div>
        </div>
      )}
      {report.isError && <ErrorState error={report.error} onRetry={report.refetch} />}

      {d && (
        <div className="stack">
          {d.provisional && (
            <Note tone="warn">
              <b>Provisional report.</b> It draws on obligation-library entries marked{" "}
              <span className="mono">DRAFT_UNVERIFIED</span>, pending content-team verification.
              Exports carry the same marking — say so if you circulate this to a board.
            </Note>
          )}

          <div className="panel">
            <div className="panel-body">
              <div className="row-wrap" style={{ gap: 20, justifyContent: "space-between" }}>
                <div>
                  <div className="eyebrow">Entity</div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{d.entity}</div>
                  <div className="micro muted">{d.organization}</div>
                </div>
                <div>
                  <div className="eyebrow">As of</div>
                  <div className="num">{fmtDate(d.as_of)}</div>
                </div>
                <div>
                  <div className="eyebrow">Obligation library</div>
                  <div className="mono">{d.library_version}</div>
                </div>
                <div>
                  <div className="eyebrow">
                    <Definition tip="Health = 100 × (1 − overdue ÷ total obligations). It grades timeliness only, not evidence quality.">
                      Health
                    </Definition>
                  </div>
                  <div className="row" style={{ gap: 7, alignItems: "baseline" }}>
                    <span className="num" style={{ fontSize: 21, fontWeight: 620, letterSpacing: "-.02em" }}>
                      {d.health_score}%
                    </span>
                    <Badge tone={d.health_score >= 95 ? "good" : d.health_score >= 80 ? "warn" : "crit"} dot>
                      {d.health_score >= 95 ? "Healthy" : d.health_score >= 80 ? "At risk" : "Critical"}
                    </Badge>
                  </div>
                </div>
              </div>
            </div>
            {d.narrative && (
              <div className="panel-body" style={{ borderTop: "1px solid var(--rule)" }}>
                <div className="eyebrow" style={{ marginBottom: 5 }}>Summary</div>
                <p style={{ fontSize: 13, lineHeight: 1.6, maxWidth: "78ch" }}>{d.narrative}</p>
              </div>
            )}
          </div>

          <div className="metric-strip">
            <StaticMetric tone="crit" label="Overdue" value={d.tiles.overdue} />
            <StaticMetric tone="warn" label="Due in 7 days" value={d.tiles.due_this_week} />
            <StaticMetric tone="info" label="Awaiting review" value={d.tiles.awaiting_review} />
            <StaticMetric tone="good" label="Filed" value={d.tiles.completed}
              sub={`of ${d.totals.instances}`} />
          </div>

          <Section title="Overdue" tone="crit" rows={d.sections.overdue ?? []}
            empty="Nothing is past its statutory date." />
          <Section title="Due within 7 days" tone="warn" rows={d.sections.due_this_week ?? []}
            empty="Nothing falls due in the next week." />
          <Section title="Awaiting review" tone="info" rows={d.sections.awaiting_review ?? []}
            empty="No filings are waiting on a checker." />
        </div>
      )}
    </div>
  );
}

function StaticMetric({ tone, label, value, sub }: {
  tone: "crit" | "warn" | "info" | "good"; label: string; value: number; sub?: string;
}) {
  return (
    <div className={`metric tone-${tone}`} style={{ cursor: "default" }}>
      <span className="m-label eyebrow">{label}</span>
      <span className="m-value num">{value}</span>
      {sub && <span className="m-sub">{sub}</span>}
    </div>
  );
}

type Row = {
  period_label: string; title: string; due_date: string | null;
  form_reference: string | null; risk_level: string; status: string; evidence_count?: number;
};

function Section({ title, rows, tone, empty }: {
  title: string; rows: Row[]; tone: "crit" | "warn" | "info"; empty: string;
}) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h3>{title}</h3>
        <Badge tone={rows.length === 0 ? "good" : tone} dot>
          {rows.length === 0 ? "Clear" : pluralize(rows.length, "item")}
        </Badge>
      </div>
      {rows.length === 0 ? (
        <Empty icon={<IconCheckCircle size={16} />} title="Nothing here" hint={empty} />
      ) : (
        <div className="tbl-wrap">
          <table className="tbl">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr>
                <th>Obligation</th>
                <th className="tight">Risk</th>
                <th className="tight">Due</th>
                <th className="tight">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 50).map((r, n) => {
                const rel = relativeDue(r.due_date);
                return (
                  <tr key={`${r.title}-${n}`}>
                    <td>
                      <div className="truncate" style={{ maxWidth: 460, fontWeight: 550 }}>{r.title}</div>
                      <div className="micro faint">
                        {r.period_label}
                        {r.form_reference ? <> · <span className="mono">{r.form_reference}</span></> : null}
                      </div>
                    </td>
                    <td className="tight"><RiskMeter level={r.risk_level} compact /></td>
                    <td className="tight">
                      <div className="num">{fmtDateShort(r.due_date)}</div>
                      <div className="micro" style={{
                        color: rel.tone === "crit" ? "var(--crit)"
                          : rel.tone === "warn" ? "var(--warn)" : "var(--ink-3)",
                      }}>{rel.text}</div>
                    </td>
                    <td className="tight"><StatusBadge status={r.status} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {rows.length > 50 && (
        <div className="panel-foot">
          Showing the first 50 of {rows.length}. The exported PDF contains every item.
        </div>
      )}
    </div>
  );
}
