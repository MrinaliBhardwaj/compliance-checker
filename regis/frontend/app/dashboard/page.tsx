"use client";
// Dashboard (PRD §9): risk-weighted action tiles + priority queue + persistent
// read-only Copilot. Tiles link into the filtered tracker; PDF export for admin/head.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { downloadReport, getDashboard, getInstances } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/lib/toast";
import Shell from "@/components/Shell";
import Copilot from "@/components/Copilot";
import { Empty, ErrorState, Loading, RiskBadge, StatusBadge, fmtDate } from "@/components/ui";

export default function DashboardPage() {
  return <Shell><DashboardInner /></Shell>;
}

function DashboardInner() {
  const { can } = useAuth();
  const router = useRouter();
  const toast = useToast();

  const dash = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard });
  const queue = useQuery({ queryKey: ["queue"], queryFn: () => getInstances({}) });

  const exportPdf = async () => {
    try {
      const blob = await downloadReport("pdf");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "compliance-status.pdf"; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Export failed", "err");
    }
  };

  // priority order: overdue -> ready_for_review -> in_progress -> pending
  const order: Record<string, number> = {
    overdue: 0, ready_for_review: 1, in_progress: 2, pending: 3, completed: 4, not_applicable: 5,
  };
  const top = [...(queue.data ?? [])]
    .sort((a, b) => (order[a.status] - order[b.status]) || (a.due_date ?? "").localeCompare(b.due_date ?? ""))
    .slice(0, 12);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 16 }}>
      <main className="stack">
        <div className="between">
          <h1>Compliance</h1>
          <div className="row">
            {dash.data && <span className="badge completed">Health {dash.data.health_score}%</span>}
            {can("export_reports") && <button className="btn" onClick={exportPdf}>Export PDF</button>}
          </div>
        </div>

        {dash.isLoading && <Loading />}
        {dash.isError && <ErrorState error={dash.error} onRetry={dash.refetch} />}
        {dash.data && (
          <>
            <div className="card">
              <Narrative tiles={dash.data.tiles} />
            </div>
            <div className="grid-cards">
              <Tile n={dash.data.tiles.overdue} label="Overdue"
                onClick={() => router.push("/obligations?status=overdue")} />
              <Tile n={dash.data.tiles.due_this_week} label="Due this week"
                onClick={() => router.push("/obligations")} />
              <Tile n={dash.data.tiles.awaiting_review} label="Awaiting review"
                onClick={() => router.push("/obligations?status=ready_for_review")} />
              <Tile n={dash.data.tiles.completed} label="Completed"
                onClick={() => router.push("/obligations?status=completed")} />
            </div>
          </>
        )}

        <div className="card">
          <div className="between"><h3 style={{ margin: 0 }}>Priority queue</h3>
            <Link href="/obligations" className="muted" style={{ fontSize: 13 }}>View all →</Link></div>
          {queue.isLoading && <Loading />}
          {queue.isError && <ErrorState error={queue.error} onRetry={queue.refetch} />}
          {queue.data && (top.length === 0
            ? <Empty title="Nothing in the queue" hint="Generate your calendar from onboarding." />
            : (
              <table className="table">
                <thead><tr><th>Obligation</th><th>Risk</th><th>Due</th><th>Status</th></tr></thead>
                <tbody>
                  {top.map((i) => (
                    <tr key={i.id} className="clickable"
                      onClick={() => router.push(`/obligations?open=${i.id}`)}>
                      <td>{i.title}{i.state ? ` [${i.state}]` : ""}</td>
                      <td><RiskBadge level={i.risk_level} /></td>
                      <td>{fmtDate(i.due_date)}{i.working_day_adjusted ? " *" : ""}</td>
                      <td><StatusBadge status={i.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ))}
        </div>
      </main>

      <Copilot />
    </div>
  );
}

function Tile({ n, label, onClick }: { n: number; label: string; onClick: () => void }) {
  return (
    <button className="tile" onClick={onClick}
      style={{ textAlign: "left", cursor: "pointer" }}>
      <span className="n">{n}</span><span className="l">{label}</span>
    </button>
  );
}

function Narrative({ tiles }: { tiles: { overdue: number; due_this_week: number; awaiting_review: number } }) {
  const parts: string[] = [];
  if (tiles.overdue) parts.push(`${tiles.overdue} overdue`);
  if (tiles.due_this_week) parts.push(`${tiles.due_this_week} due this week`);
  if (tiles.awaiting_review) parts.push(`${tiles.awaiting_review} awaiting your review`);
  return <p style={{ margin: 0 }}>{parts.length ? `${parts.join(", ")}.` : "You're all caught up. Nothing overdue or imminent."}</p>;
}
