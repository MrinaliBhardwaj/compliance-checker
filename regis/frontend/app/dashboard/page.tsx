"use client";
// "Today" — the daily standing position.
//
// Rework notes:
//  • Hierarchy follows consequence. Overdue is stated in a banner before any
//    tile is read; the four tiles are one connected strip with tone rails, not
//    four identical floating cards where a crisis looks like good news.
//  • The health score is defined in the UI. A single number a board might
//    challenge has to be falsifiable, so the tooltip gives the exact formula
//    the backend uses and the inputs behind today's value.
//  • The priority queue is ordered by the same explainable triage score the
//    tracker uses, not by status-then-date. Oldest-overdue is not highest-risk:
//    a 153-day-late board minute was outranking a 3-day-late RBI return.
//  • Copilot moved out of a permanent 360px column into a panel that earns its
//    space — it was occupying the most valuable real estate on the screen while
//    idle.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";
import {
  downloadReport, getDashboard, getInstances, listAssignable, type Instance,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errMessage, useToast } from "@/lib/toast";
import {
  daysFromToday, fmtDate, fmtDateShort, PRIORITY_EXPLAINER, priorityOf,
  pluralize, relativeDue,
} from "@/lib/format";
import Shell from "@/components/Shell";
import Copilot from "@/components/Copilot";
import ObligationSheet from "@/components/ObligationSheet";
import {
  IconArrowRight, IconCheckCircle, IconClock, IconDownload, IconList,
} from "@/components/icons";
import {
  Avatar, Badge, Definition, DistBar, Empty, ErrorState, Note, PriorityBadge,
  RiskMeter, Skeleton, SkeletonMetrics, SkeletonRows, StatusBadge,
} from "@/components/ui";

export default function DashboardPage() {
  return (
    <Shell>
      <Suspense fallback={<DashSkeleton />}>
        <Today />
      </Suspense>
    </Shell>
  );
}

function DashSkeleton() {
  return (
    <div className="stack">
      <div className="page-head"><Skeleton w={140} h={20} /></div>
      <SkeletonMetrics />
      <div className="panel"><SkeletonRows rows={8} cols={5} /></div>
    </div>
  );
}

const CLOSED = new Set(["completed", "not_applicable"]);

function Today() {
  const { can, principal, entityId } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const toast = useToast();
  const openId = params.get("open");

  const dash = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard });
  const queue = useQuery({ queryKey: ["tracker"], queryFn: () => getInstances({}) });
  const members = useQuery({
    queryKey: ["assignable"], queryFn: listAssignable,
    enabled: can("assign") || can("approve"), staleTime: 300_000,
  });

  const entityName = principal?.entities.find((e) => e.id === entityId)?.legal_name
    ?? principal?.entities[0]?.legal_name;

  const ownerName = (id: string | null) => {
    if (!id) return null;
    if (id === principal?.user_id) return "You";
    const m = members.data?.find((x) => x.user_id === id);
    return m ? (m.full_name || m.email) : "Assigned";
  };

  const exportPdf = async () => {
    try {
      const blob = await downloadReport("pdf");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "compliance-status.pdf"; a.click();
      URL.revokeObjectURL(url);
      toast.ok("Report downloaded", "Board-ready compliance status as of today.");
    } catch (e) {
      toast.err("Export failed", errMessage(e));
    }
  };

  // Same triage score the tracker sorts by, so the two screens never disagree
  // about what matters most.
  const top = useMemo(() => [...(queue.data ?? [])]
    .filter((i) => !CLOSED.has(i.status))
    .sort((a, b) => priorityOf(b).score - priorityOf(a).score
      || (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999"))
    .slice(0, 10),
    [queue.data]);

  const unassignedOpen = useMemo(
    () => (queue.data ?? []).filter((i) => !CLOSED.has(i.status) && !i.owner_user_id).length,
    [queue.data]);

  const t = dash.data?.tiles;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Today</h1>
          <p className="lede">
            {entityName ? <><b>{entityName}</b> · </> : null}
            Standing compliance position as of {fmtDate(new Date().toISOString().slice(0, 10))}.
          </p>
        </div>
        {can("export_reports") && (
          <button className="btn" onClick={exportPdf}>
            <IconDownload size={13} /> Export board report
          </button>
        )}
      </div>

      {dash.isError && <div style={{ marginBottom: 16 }}>
        <ErrorState error={dash.error} onRetry={dash.refetch} />
      </div>}

      {dash.isLoading && <div className="stack"><SkeletonMetrics /></div>}

      {dash.data && (
        <div className="stack">
          <Headline tiles={dash.data.tiles} total={dash.data.total_instances} />

          <div className="metric-strip">
            <Metric tone="crit" label="Overdue" value={t!.overdue}
              sub={t!.overdue ? "Past the statutory date" : "Nothing past due"}
              onClick={() => router.push("/obligations?view=overdue")} />
            <Metric tone="warn" label="Due in 7 days" value={t!.due_this_week}
              sub="Open and imminent"
              onClick={() => router.push("/obligations?view=week")} />
            <Metric tone="info" label="Awaiting review" value={t!.awaiting_review}
              sub={can("approve") ? "Waiting on you to approve" : "With a checker"}
              onClick={() => router.push("/obligations?view=review")} />
            <Metric tone="good" label="Filed" value={t!.completed}
              sub={`of ${dash.data.total_instances} this cycle`}
              onClick={() => router.push("/obligations?status=completed")} />
          </div>

          <div className="split">
            <div className="stack">
              <PriorityQueue
                rows={top} loading={queue.isLoading} error={queue.error}
                onRetry={queue.refetch} ownerName={ownerName}
                onOpen={(id) => router.push(`/dashboard?open=${id}`)}
                canGenerate={can("generate_calendar")}
                totalOpen={(queue.data ?? []).filter((i) => !CLOSED.has(i.status)).length}
              />

              {unassignedOpen > 0 && can("assign") && (
                <Note tone="warn">
                  <b>{pluralize(unassignedOpen, "open obligation")} has no owner.</b>{" "}
                  Unowned obligations never enter a queue and never trigger reminders.{" "}
                  <Link href="/obligations?view=all">Assign them →</Link>
                </Note>
              )}
            </div>

            <div className="stack">
              <HealthPanel
                score={dash.data.health_score}
                byStatus={dash.data.by_status}
                total={dash.data.total_instances}
                overdue={t!.overdue}
              />
              <Copilot />
            </div>
          </div>
        </div>
      )}

      <ObligationSheet instanceId={openId} onClose={() => router.push("/dashboard")} />
    </div>
  );
}

/* ================================================================ headline */

/** One sentence, at the top, in plain language. Read before any number. */
function Headline({ tiles, total }: {
  tiles: { overdue: number; due_this_week: number; awaiting_review: number; completed: number };
  total: number;
}) {
  if (tiles.overdue > 0) {
    return (
      <Note tone="crit">
        <b>{pluralize(tiles.overdue, "obligation")} past the statutory due date.</b>{" "}
        Each open day increases penalty exposure — clear these before anything else.{" "}
        <Link href="/obligations?view=overdue" style={{ color: "inherit", fontWeight: 600 }}>
          Review overdue →
        </Link>
      </Note>
    );
  }
  if (tiles.due_this_week > 0 || tiles.awaiting_review > 0) {
    const parts: string[] = [];
    if (tiles.due_this_week) parts.push(`${tiles.due_this_week} due within 7 days`);
    if (tiles.awaiting_review) parts.push(`${tiles.awaiting_review} awaiting review`);
    return (
      <Note tone="info">
        <b>Nothing overdue.</b> {parts.join(" and ")} — on track if handled this week.
      </Note>
    );
  }
  return (
    <Note tone="good">
      <b>Fully current.</b> Nothing overdue and nothing due in the next seven days
      across {pluralize(total, "tracked obligation")}.
    </Note>
  );
}

function Metric({ tone, label, value, sub, onClick }: {
  tone: "crit" | "warn" | "info" | "good"; label: string; value: number;
  sub: string; onClick: () => void;
}) {
  return (
    <button className={`metric tone-${tone}`} onClick={onClick}>
      <span className="m-label eyebrow">{label}</span>
      <span className="m-value num">{value}</span>
      <span className="m-sub">{sub}</span>
    </button>
  );
}

/* =========================================================== health score */

/**
 * The score, its formula and its inputs together. A compliance officer who
 * cannot explain this number to a board cannot defend it, so the definition is
 * part of the component rather than tribal knowledge.
 */
function HealthPanel({ score, byStatus, total, overdue }: {
  score: number; byStatus: Record<string, number>; total: number; overdue: number;
}) {
  const tone = score >= 95 ? "good" : score >= 80 ? "warn" : "crit";
  const segments = [
    { key: "overdue", n: byStatus.overdue ?? 0, tone: "crit" as const, label: "Overdue" },
    { key: "ready_for_review", n: byStatus.ready_for_review ?? 0, tone: "warn" as const, label: "In review" },
    { key: "in_progress", n: byStatus.in_progress ?? 0, tone: "info" as const, label: "In progress" },
    { key: "completed", n: byStatus.completed ?? 0, tone: "good" as const, label: "Filed" },
    { key: "pending", n: byStatus.pending ?? 0, tone: "neutral" as const, label: "Not started" },
    { key: "not_applicable", n: byStatus.not_applicable ?? 0, tone: "neutral" as const, label: "N/A" },
  ];

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>
          <Definition tip={
            <>
              <b>Health = 100 × (1 − overdue ÷ total obligations)</b>
              <br /><br />
              Today: 1 − {overdue} ÷ {total} = <b>{score}%</b>.
              <br /><br />
              It measures only whether statutory dates were met. It does not grade
              evidence quality or approval rigour.
            </>
          }>
            Compliance health
          </Definition>
        </h3>
        <Badge tone={tone === "good" ? "good" : tone === "warn" ? "warn" : "crit"} dot>
          {score >= 95 ? "Healthy" : score >= 80 ? "At risk" : "Critical"}
        </Badge>
      </div>
      <div className="panel-body stack-sm">
        <div className="row" style={{ alignItems: "baseline", gap: 8 }}>
          <span className="num" style={{
            fontSize: 36, fontWeight: 620, letterSpacing: "-.03em", lineHeight: 1,
            color: tone === "crit" ? "var(--crit)" : tone === "warn" ? "var(--warn)" : "var(--ink)",
          }}>{score}%</span>
          <span className="micro faint">
            {overdue === 0 ? "no obligations past due" : `${overdue} of ${total} past due`}
          </span>
        </div>

        <div style={{ paddingTop: 4 }}>
          <DistBar segments={segments} />
          <div className="row-wrap" style={{ gap: 10, marginTop: 8 }}>
            {segments.filter((s) => s.n > 0).map((s) => (
              <span key={s.key} className="row micro" style={{ gap: 5 }}>
                <i aria-hidden="true" style={{
                  width: 7, height: 7, borderRadius: 2, display: "block",
                  background: s.tone === "crit" ? "var(--crit-solid)"
                    : s.tone === "warn" ? "var(--warn)"
                    : s.tone === "good" ? "var(--good)"
                    : s.tone === "info" ? "var(--info)" : "var(--rule-2)",
                }} />
                <span className="muted">{s.label}</span>
                <span className="num" style={{ fontWeight: 600 }}>{s.n}</span>
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="panel-foot">
        Counts every dated obligation generated for this entity in the current cycle.
      </div>
    </div>
  );
}

/* =========================================================== priority queue */

function PriorityQueue({ rows, loading, error, onRetry, ownerName, onOpen, canGenerate, totalOpen }: {
  rows: Instance[]; loading: boolean; error: unknown; onRetry: () => void;
  ownerName: (id: string | null) => string | null; onOpen: (id: string) => void;
  canGenerate: boolean; totalOpen: number;
}) {
  return (
    <div className="panel">
      <div className="panel-head">
        <div>
          <h3>Priority queue</h3>
          <div className="micro faint" style={{ marginTop: 1 }}>
            <Definition tip={PRIORITY_EXPLAINER}>Ranked by risk and time pressure</Definition>
          </div>
        </div>
        <Link href="/obligations" className="btn sm">
          All obligations <IconArrowRight size={12} />
        </Link>
      </div>

      {loading && <SkeletonRows rows={7} cols={5} />}
      {!!error && <div style={{ padding: 14 }}><ErrorState error={error} onRetry={onRetry} /></div>}

      {!loading && !error && rows.length === 0 && (
        totalOpen === 0 && rows.length === 0 ? (
          <Empty icon={<IconCheckCircle size={16} />} title="Queue is clear"
            hint="Nothing is open right now. New obligations appear here as their periods begin."
            action={canGenerate
              ? <Link className="btn" href="/onboarding">Review compliance profile</Link>
              : undefined} />
        ) : (
          <Empty icon={<IconList size={16} />} title="No compliance calendar yet"
            hint="Answer the profile questionnaire and Regis generates every dated obligation this entity owes."
            action={canGenerate
              ? <Link className="btn primary" href="/onboarding">Build the calendar</Link>
              : <span className="micro faint">A compliance admin needs to generate it.</span>} />
        )
      )}

      {!loading && rows.length > 0 && (
        <div className="tbl-wrap">
          <table className="tbl">
            <caption className="sr-only">Highest-priority open obligations</caption>
            <thead>
              <tr>
                <th style={{ paddingLeft: 14 }}>Obligation</th>
                <th className="tight">Priority</th>
                <th className="tight">Owner</th>
                <th className="tight">Due</th>
                <th className="tight">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((i) => {
                const rel = relativeDue(i.due_date);
                const owner = ownerName(i.owner_user_id);
                const n = daysFromToday(i.due_date);
                const urgency = i.status === "overdue" ? "overdue"
                  : i.status === "ready_for_review" ? "review"
                  : n !== null && n <= 7 ? "soon" : "none";
                return (
                  <tr key={i.id} className="row-link" data-urgency={urgency} tabIndex={0}
                    onClick={() => onOpen(i.id)}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); onOpen(i.id); } }}>
                    <td className="rail">
                      <div className="truncate" style={{ fontWeight: 550, maxWidth: 340 }}>{i.title}</div>
                      <div className="micro faint">
                        {i.period_label}
                        {i.form_reference ? <> · <span className="mono">{i.form_reference}</span></> : null}
                      </div>
                    </td>
                    <td className="tight">
                      <span className="row" style={{ gap: 8 }}>
                        <PriorityBadge p={priorityOf(i)} />
                        <RiskMeter level={i.risk_level} compact />
                      </span>
                    </td>
                    <td className="tight">
                      {owner ? (
                        <span className="row" style={{ gap: 6 }}>
                          <Avatar label={owner} size={19} />
                          <span className="truncate" style={{ maxWidth: 92 }}>{owner}</span>
                        </span>
                      ) : (
                        <span className="micro" style={{ color: "var(--warn)" }}>Unassigned</span>
                      )}
                    </td>
                    <td className="tight">
                      <div className="num">{fmtDateShort(i.due_date)}{i.working_day_adjusted ? "*" : ""}</div>
                      <div className="micro" style={{
                        color: rel.tone === "crit" ? "var(--crit)"
                          : rel.tone === "warn" ? "var(--warn)" : "var(--ink-3)",
                        fontWeight: rel.tone === "crit" ? 600 : 400,
                      }}>{rel.text}</div>
                    </td>
                    <td className="tight"><StatusBadge status={i.status} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {rows.length > 0 && (
        <div className="panel-foot between">
          <span>Showing the {rows.length} most urgent of {pluralize(totalOpen, "open obligation")}</span>
          <span className="row" style={{ gap: 6 }}>
            <IconClock size={11} /> Refreshed on load
          </span>
        </div>
      )}
    </div>
  );
}
