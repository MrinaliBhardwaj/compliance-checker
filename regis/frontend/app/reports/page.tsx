"use client";
// Reports: preview the grounded compliance summary on-screen, then export PDF/HTML.
// Admin/head only (route is hidden for preparers in the shell + guarded here).
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { downloadReport, getReport } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/lib/toast";
import Shell from "@/components/Shell";
import { Empty, ErrorState, Loading, fmtDate } from "@/components/ui";

export default function ReportsPage() {
  return <Shell><Reports /></Shell>;
}

function Reports() {
  const { can } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const report = useQuery({ queryKey: ["report"], queryFn: getReport, enabled: can("export_reports") });

  useEffect(() => {
    if (!can("export_reports")) router.replace("/dashboard");
  }, [can, router]);

  if (!can("export_reports")) return null;

  const exportAs = async (kind: "pdf" | "html") => {
    try {
      const blob = await downloadReport(kind);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `compliance-status.${kind}`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Export failed", "err");
    }
  };

  return (
    <div className="stack">
      <div className="between">
        <h1>Reports</h1>
        <div className="row">
          <button className="btn" onClick={() => exportAs("html")}>Export HTML</button>
          <button className="btn primary" onClick={() => exportAs("pdf")}>Export PDF</button>
        </div>
      </div>

      {report.isLoading && <Loading />}
      {report.isError && <ErrorState error={report.error} onRetry={report.refetch} />}
      {report.data && (
        <div className="stack">
          <div className="muted">
            {report.data.organization} · {report.data.entity} · as of {fmtDate(report.data.as_of)}
            · library {report.data.library_version}
          </div>
          {report.data.provisional && (
            <div className="banner prov">
              PROVISIONAL — generated from a DRAFT_UNVERIFIED obligation library pending
              content-team verification.
            </div>
          )}
          <div className="card"><b>Health {report.data.health_score}%.</b> {report.data.narrative}</div>
          <div className="grid-cards">
            <Tile n={report.data.tiles.overdue} l="Overdue" />
            <Tile n={report.data.tiles.due_this_week} l="Due this week" />
            <Tile n={report.data.tiles.awaiting_review} l="Awaiting review" />
            <Tile n={report.data.tiles.completed} l="Completed" />
          </div>
          <Section title="Overdue" rows={report.data.sections.overdue} />
          <Section title="Due this week" rows={report.data.sections.due_this_week} />
          <Section title="Awaiting review" rows={report.data.sections.awaiting_review} />
        </div>
      )}
    </div>
  );
}

function Tile({ n, l }: { n: number; l: string }) {
  return <div className="tile"><span className="n">{n}</span><span className="l">{l}</span></div>;
}

function Section({ title, rows }:
  { title: string; rows: { period_label: string; title: string; due_date: string | null; form_reference: string | null }[] }) {
  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>{title} ({rows.length})</h3>
      {rows.length === 0 ? <Empty title="None" /> : (
        <table className="table">
          <thead><tr><th>Period</th><th>Obligation</th><th>Form</th><th>Due</th></tr></thead>
          <tbody>
            {rows.slice(0, 50).map((r, n) => (
              <tr key={n}><td>{r.period_label}</td><td>{r.title}</td>
                <td className="muted">{r.form_reference ?? "—"}</td><td>{fmtDate(r.due_date)}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
