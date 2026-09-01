"use client";
// Obligation tracker — the screen a compliance officer lives in.
//
// What changed, and why:
//  • Saved views (All / My work / Overdue / In review / Due in 7 days) replace a
//    wrapping wall of filter chips. The views encode the questions people
//    actually ask; the chips encoded the data model.
//  • All filter, sort and selection state lives in the URL, so a view is
//    shareable, bookmarkable and survives the back button. Previously the URL
//    was read once on mount and never written.
//  • Bulk selection + bulk lifecycle actions. Approving 20 filings used to mean
//    opening 20 drawers. Bulk runs are pre-flighted (ineligible rows are
//    identified and excluded *before* you confirm) and report per-item results.
//  • Rows carry relative due dates, owner, evidence state and a 2px urgency
//    rail, so triage is visual rather than arithmetic.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import {
  bulkAssign, bulkTransition, getInstances, listAssignable,
  type BulkOutcome, type Instance, type LifecycleAction, type Member,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errMessage, useToast } from "@/lib/toast";
import {
  daysFromToday, fmtDateShort, relativeDue, statusLabel, urgencyOf, pluralize,
} from "@/lib/format";
import Shell from "@/components/Shell";
import ObligationSheet from "@/components/ObligationSheet";
import {
  IconCheck, IconFilter, IconList, IconPaperclip, IconSearch, IconUser, IconX,
} from "@/components/icons";
import {
  Avatar, Checkbox, ConfirmDialog, Empty, ErrorState, Field, Modal, Note,
  ResultCount, RiskMeter, Segmented, Skeleton, SkeletonRows, SortableTh, Spinner,
  StatusBadge, useDebounced, type SortDir,
} from "@/components/ui";

/* =================================================================== views */

type ViewId = "all" | "mine" | "overdue" | "review" | "week";

const VIEWS: { id: ViewId; label: string; describe: string }[] = [
  { id: "all", label: "All", describe: "Every obligation, including filed and not-applicable" },
  { id: "mine", label: "My work", describe: "Assigned to you and still open" },
  { id: "overdue", label: "Overdue", describe: "Past the statutory due date" },
  { id: "review", label: "In review", describe: "Submitted, waiting on a checker" },
  { id: "week", label: "Next 7 days", describe: "Open and due within a week" },
];

const CLOSED = new Set(["completed", "not_applicable"]);

function matchesView(view: ViewId, i: Instance, myUserId?: string): boolean {
  switch (view) {
    case "mine": return i.owner_user_id === myUserId && !CLOSED.has(i.status);
    case "overdue": return i.status === "overdue";
    case "review": return i.status === "ready_for_review";
    case "week": {
      if (CLOSED.has(i.status)) return false;
      const n = daysFromToday(i.due_date);
      return n !== null && n >= 0 && n <= 7;
    }
    default: return true;
  }
}

type SortKey = "due" | "title" | "risk" | "status" | "category";
const RISK_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };
const STATUS_ORDER: Record<string, number> = {
  overdue: 0, ready_for_review: 1, in_progress: 2, pending: 3, completed: 4, not_applicable: 5,
};

/* ==================================================================== page */

export default function ObligationsPage() {
  return (
    <Shell>
      <Suspense fallback={<TrackerSkeleton />}>
        <Tracker />
      </Suspense>
    </Shell>
  );
}

function TrackerSkeleton() {
  return (
    <div className="stack">
      <div className="page-head"><Skeleton w={180} h={20} /></div>
      <div className="panel"><SkeletonRows rows={10} cols={6} /></div>
    </div>
  );
}

function Tracker() {
  const params = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const { principal, can } = useAuth();

  /* ---- URL-backed state ------------------------------------------------ */
  const view = (params.get("view") as ViewId) ?? inferViewFromLegacyParams(params);
  const status = params.get("status") ?? "";
  const category = params.get("category") ?? "";
  const sortKey = (params.get("sort") as SortKey) ?? "due";
  const sortDir = (params.get("dir") as SortDir) ?? "asc";
  const grouped = params.get("group") !== "off";
  const dense = params.get("density") === "compact";
  const openId = params.get("open");

  const [qInput, setQInput] = useState(params.get("q") ?? "");
  const q = useDebounced(qInput, 180);

  const setParams = useCallback((patch: Record<string, string | null>) => {
    const next = new URLSearchParams(Array.from(params.entries()));
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === "") next.delete(k); else next.set(k, v);
    }
    router.replace(next.toString() ? `/obligations?${next}` : "/obligations", { scroll: false });
  }, [params, router]);

  // Keep the debounced query string in the URL without a history entry per keystroke.
  useEffect(() => {
    if ((params.get("q") ?? "") !== q) setParams({ q: q || null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  /* ---- data ------------------------------------------------------------ */
  const all = useQuery({ queryKey: ["tracker"], queryFn: () => getInstances({}) });
  const members = useQuery({
    queryKey: ["assignable"], queryFn: listAssignable,
    enabled: can("assign") || can("approve"), staleTime: 300_000,
  });

  const ownerName = useCallback((id: string | null) => {
    if (!id) return null;
    if (id === principal?.user_id) return "You";
    const m = members.data?.find((x) => x.user_id === id);
    return m ? (m.full_name || m.email) : "Assigned";
  }, [members.data, principal?.user_id]);

  const rowsAll = all.data ?? [];

  const viewCounts = useMemo(() => {
    const c: Record<ViewId, number> = { all: 0, mine: 0, overdue: 0, review: 0, week: 0 };
    for (const v of VIEWS) c[v.id] = rowsAll.filter((i) => matchesView(v.id, i, principal?.user_id)).length;
    return c;
  }, [rowsAll, principal?.user_id]);

  const categories = useMemo(
    () => Array.from(new Set(rowsAll.map((i) => i.category))).sort(),
    [rowsAll]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rowsAll.filter((i) => {
      if (!matchesView(view, i, principal?.user_id)) return false;
      if (status && i.status !== status) return false;
      if (category && i.category !== category) return false;
      if (needle && !(
        i.title.toLowerCase().includes(needle)
        || (i.form_reference ?? "").toLowerCase().includes(needle)
        || i.period_label.toLowerCase().includes(needle)
      )) return false;
      return true;
    });
  }, [rowsAll, view, status, category, q, principal?.user_id]);

  const sorted = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    const cmp: Record<SortKey, (a: Instance, b: Instance) => number> = {
      due: (a, b) => (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999"),
      title: (a, b) => a.title.localeCompare(b.title),
      risk: (a, b) => (RISK_ORDER[a.risk_level] ?? 9) - (RISK_ORDER[b.risk_level] ?? 9),
      status: (a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9),
      category: (a, b) => a.category.localeCompare(b.category),
    };
    return [...filtered].sort((a, b) => cmp[sortKey](a, b) * dir
      || (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999"));
  }, [filtered, sortKey, sortDir]);

  /* ---- selection ------------------------------------------------------- */
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const visibleIds = useMemo(() => sorted.map((i) => i.id), [sorted]);
  // Drop selections that scroll out of the current filter — acting on rows you
  // can no longer see is a classic bulk-action footgun.
  useEffect(() => {
    setSelected((prev) => {
      const next = new Set([...prev].filter((id) => visibleIds.includes(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [visibleIds]);

  const selectedRows = useMemo(
    () => sorted.filter((i) => selected.has(i.id)), [sorted, selected]);
  const allChecked = visibleIds.length > 0 && selected.size === visibleIds.length;
  const someChecked = selected.size > 0 && !allChecked;

  const toggleAll = () =>
    setSelected(allChecked ? new Set() : new Set(visibleIds));
  const toggleOne = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });

  /* ---- bulk mutations -------------------------------------------------- */
  const [bulk, setBulk] = useState<null | "approve" | "submit" | "mark_na" | "assign">(null);
  const bulkRun = useMutation({
    mutationFn: async (job: { ids: string[]; action: LifecycleAction; reason?: string }) =>
      bulkTransition(job.ids, job.action, job.reason ? { reason: job.reason } : {}),
    onSuccess: (outcomes, job) => reportBulk(outcomes, job.action),
    onError: (e) => toast.err("Bulk action failed", errMessage(e)),
  });
  const bulkAssignRun = useMutation({
    mutationFn: async (job: { ids: string[]; owner: string }) => bulkAssign(job.ids, job.owner),
    onSuccess: (outcomes) => reportBulk(outcomes, "assign"),
    onError: (e) => toast.err("Bulk assign failed", errMessage(e)),
  });

  function reportBulk(outcomes: BulkOutcome[], what: string) {
    const ok = outcomes.filter((o) => o.ok).length;
    const failed = outcomes.length - ok;
    qc.invalidateQueries({ queryKey: ["tracker"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    setSelected(new Set());
    setBulk(null);
    if (failed === 0) {
      toast.ok(`${pluralize(ok, "obligation")} updated`, humanAction(what));
    } else {
      const firstErr = outcomes.find((o) => !o.ok)?.error;
      toast.err(
        `${ok} updated, ${failed} failed`,
        firstErr ? `First error: ${firstErr}` : "Some obligations could not be changed.",
      );
    }
  }

  /* ---- eligibility pre-flight ------------------------------------------ */
  // Bulk lifecycle verbs only apply from certain states. Compute what would
  // actually change *before* asking for confirmation, and say so plainly.
  const eligibility = useMemo(() => {
    const forAction = (fn: (i: Instance) => boolean) => {
      const eligible = selectedRows.filter(fn);
      return { eligible, skipped: selectedRows.length - eligible.length };
    };
    return {
      approve: forAction((i) => i.status === "ready_for_review"),
      submit: forAction((i) => ["pending", "in_progress", "overdue"].includes(i.status)),
      mark_na: forAction((i) => !CLOSED.has(i.status)),
      assign: forAction(() => true),
    };
  }, [selectedRows]);

  const onSort = (k: SortKey) =>
    setParams({ sort: k, dir: sortKey === k && sortDir === "asc" ? "desc" : "asc" });

  const filtersActive = !!(status || category || q.trim());
  const clearFilters = () => { setQInput(""); setParams({ status: null, category: null, q: null }); };

  /* ---- render ---------------------------------------------------------- */
  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Obligations</h1>
          <p className="lede">
            Every dated filing generated for this entity, with its owner, evidence and
            approval state. Select rows to act on many at once.
          </p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <Segmented
            label="Row density"
            value={dense ? "compact" : "comfortable"}
            onChange={(v) => setParams({ density: v === "compact" ? "compact" : null })}
            options={[{ value: "comfortable", label: "Comfortable" }, { value: "compact", label: "Compact" }]}
          />
        </div>
      </div>

      {/* Saved views */}
      <div className="row-wrap" style={{ gap: 6, marginBottom: 12 }}>
        {VIEWS.map((v) => (
          <button key={v.id} className="chip" aria-pressed={view === v.id} title={v.describe}
            onClick={() => { setSelected(new Set()); setParams({ view: v.id === "all" ? null : v.id, status: null }); }}>
            {v.label}
            <span className="n num">{viewCounts[v.id]}</span>
          </button>
        ))}
      </div>

      <div className="panel">
        {/* Toolbar */}
        <div className="toolbar">
          <div className="row" style={{ gap: 6, flex: 1, minWidth: 220, maxWidth: 340 }}>
            <span style={{ position: "relative", flex: 1, display: "flex" }}>
              <IconSearch size={13} style={{
                position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)",
                color: "var(--ink-3)", pointerEvents: "none",
              }} />
              <input className="input" style={{ paddingLeft: 27 }} value={qInput}
                onChange={(e) => setQInput(e.target.value)}
                placeholder="Filter by name, form or period…"
                aria-label="Filter obligations" />
              {qInput && (
                <button className="btn icon ghost" aria-label="Clear filter"
                  style={{ position: "absolute", right: 2, top: "50%", transform: "translateY(-50%)" }}
                  onClick={() => setQInput("")}><IconX size={12} /></button>
              )}
            </span>
          </div>

          <label className="row" style={{ gap: 5 }}>
            <span className="sr-only">Filter by status</span>
            <select className="input" style={{ width: "auto" }} value={status}
              onChange={(e) => setParams({ status: e.target.value || null })}>
              <option value="">All statuses</option>
              {["overdue", "pending", "in_progress", "ready_for_review", "completed", "not_applicable"]
                .map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
            </select>
          </label>

          <label className="row" style={{ gap: 5 }}>
            <span className="sr-only">Filter by category</span>
            <select className="input" style={{ width: "auto", maxWidth: 200 }} value={category}
              onChange={(e) => setParams({ category: e.target.value || null })}>
              <option value="">All categories</option>
              {categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>

          <span className="spacer" />

          <Segmented label="Grouping" value={grouped ? "on" : "off"}
            onChange={(v) => setParams({ group: v === "off" ? "off" : null })}
            options={[{ value: "on", label: "Group by urgency" }, { value: "off", label: "Flat" }]} />
        </div>

        {filtersActive && (
          <div className="filter-summary">
            <IconFilter size={12} />
            <span>Filtered:</span>
            {q.trim() && <span className="tag">“{q.trim()}”</span>}
            {status && <span className="tag">{statusLabel(status)}</span>}
            {category && <span className="tag">{category}</span>}
            <button className="btn sm ghost" onClick={clearFilters}>Clear all</button>
            <span className="spacer" />
            <ResultCount shown={sorted.length} total={viewCounts[view]} />
          </div>
        )}

        {/* Body */}
        {all.isLoading && <SkeletonRows rows={10} cols={6} />}
        {all.isError && <div style={{ padding: 14 }}><ErrorState error={all.error} onRetry={all.refetch} /></div>}

        {all.data && sorted.length === 0 && (
          filtersActive ? (
            <Empty icon={<IconSearch size={16} />} title="No obligations match these filters"
              hint="Try clearing a filter, or switch to a different view."
              action={<button className="btn" onClick={clearFilters}>Clear filters</button>} />
          ) : rowsAll.length === 0 ? (
            <Empty icon={<IconList size={16} />} title="No compliance calendar yet"
              hint="Answer the compliance profile questionnaire and Regis will generate every dated obligation this entity owes."
              action={can("generate_calendar")
                ? <a className="btn primary" href="/onboarding">Build the calendar</a>
                : <span className="micro faint">A compliance admin needs to generate it.</span>} />
          ) : (
            <Empty icon={<IconCheck size={16} />} title={`Nothing in “${VIEWS.find((v) => v.id === view)?.label}”`}
              hint="That is good news — this view is clear."
              action={<button className="btn" onClick={() => setParams({ view: null })}>See all obligations</button>} />
          )
        )}

        {all.data && sorted.length > 0 && (
          <div className="tbl-wrap">
            <table className={`tbl ${dense ? "dense" : ""}`}>
              <caption className="sr-only">
                Obligations, {VIEWS.find((v) => v.id === view)?.label}. {sorted.length} rows.
              </caption>
              <thead>
                <tr>
                  <th className="tight" style={{ paddingLeft: 14 }}>
                    <Checkbox checked={allChecked} indeterminate={someChecked} onChange={toggleAll}
                      label={allChecked ? "Deselect all rows" : "Select all rows"} />
                  </th>
                  <SortableTh id="title" sort={{ key: sortKey, dir: sortDir }} onSort={onSort}>Obligation</SortableTh>
                  <SortableTh id="category" sort={{ key: sortKey, dir: sortDir }} onSort={onSort}>Category</SortableTh>
                  <SortableTh id="risk" sort={{ key: sortKey, dir: sortDir }} onSort={onSort} className="tight">Risk</SortableTh>
                  <th className="tight">Owner</th>
                  <th className="tight">Evidence</th>
                  <SortableTh id="due" sort={{ key: sortKey, dir: sortDir }} onSort={onSort} className="tight">Due</SortableTh>
                  <SortableTh id="status" sort={{ key: sortKey, dir: sortDir }} onSort={onSort} className="tight">Status</SortableTh>
                </tr>
              </thead>
              <tbody>
                {renderRows({
                  rows: sorted, grouped, selected, toggleOne, ownerName,
                  onOpen: (id) => setParams({ open: id }),
                })}
              </tbody>
            </table>
          </div>
        )}

        {all.data && sorted.length > 0 && (
          <div className="panel-foot between">
            <ResultCount shown={sorted.length} total={rowsAll.length} />
            <span className="row-wrap" style={{ gap: 12, justifyContent: "flex-end" }}>
              <span className="row" style={{ gap: 5 }}>
                <i style={{ width: 2, height: 11, background: "var(--crit-solid)", display: "block" }} /> Overdue
              </span>
              <span className="row" style={{ gap: 5 }}>
                <i style={{ width: 2, height: 11, background: "var(--warn)", display: "block" }} /> Due within 7 days
              </span>
              <span className="row" style={{ gap: 5 }}>
                <i style={{ width: 2, height: 11, background: "var(--info)", display: "block" }} /> In review
              </span>
              <span>* date shifted to a working day</span>
            </span>
          </div>
        )}
      </div>

      {/* Bulk action bar */}
      {selected.size > 0 && (
        <div className="bulkbar" role="region" aria-label="Bulk actions">
          <span className="num" style={{ fontWeight: 600 }}>
            {pluralize(selected.size, "row")} selected
          </span>
          <span className="sep" aria-hidden="true" />
          {can("approve") && (
            <button className="btn sm" onClick={() => setBulk("approve")}
              disabled={eligibility.approve.eligible.length === 0}
              title={eligibility.approve.eligible.length === 0
                ? "None of the selected rows are awaiting review" : undefined}>
              <IconCheck size={12} /> Approve
            </button>
          )}
          {can("submit") && (
            <button className="btn sm" onClick={() => setBulk("submit")}
              disabled={eligibility.submit.eligible.length === 0}>
              Submit for review
            </button>
          )}
          {can("assign") && (
            <button className="btn sm" onClick={() => setBulk("assign")}>
              <IconUser size={12} /> Assign
            </button>
          )}
          {can("mark_na") && (
            <button className="btn sm" onClick={() => setBulk("mark_na")}
              disabled={eligibility.mark_na.eligible.length === 0}>
              Mark N/A
            </button>
          )}
          <span className="sep" aria-hidden="true" />
          <button className="btn sm" onClick={() => setSelected(new Set())}>Clear</button>
        </div>
      )}

      {/* Bulk confirmations */}
      <ConfirmDialog
        open={bulk === "approve"} onClose={() => setBulk(null)} busy={bulkRun.isPending}
        title={`Approve ${pluralize(eligibility.approve.eligible.length, "obligation")}`}
        description="Each one is checked against its evidence gate. Any that fail the gate are reported and left untouched."
        confirmLabel="Approve"
        consequences={<Preflight kind="awaiting review" {...eligibility.approve} />}
        onConfirm={() => bulkRun.mutate({
          ids: eligibility.approve.eligible.map((i) => i.id), action: "approve",
        })}
      />
      <ConfirmDialog
        open={bulk === "submit"} onClose={() => setBulk(null)} busy={bulkRun.isPending}
        title={`Submit ${pluralize(eligibility.submit.eligible.length, "obligation")} for review`}
        description="A checker will be asked to approve each one."
        confirmLabel="Submit"
        consequences={<Preflight kind="open and not yet submitted" {...eligibility.submit} />}
        onConfirm={() => bulkRun.mutate({
          ids: eligibility.submit.eligible.map((i) => i.id), action: "submit",
        })}
      />
      <ConfirmDialog
        open={bulk === "mark_na"} onClose={() => setBulk(null)} busy={bulkRun.isPending}
        title={`Mark ${pluralize(eligibility.mark_na.eligible.length, "obligation")} not applicable`}
        description="They leave the active queues and stop counting towards compliance health."
        confirmLabel="Mark not applicable" tone="danger"
        reasonLabel="Why do these not apply?" reasonRequired
        reasonHint="The same reason is recorded against every obligation in this batch."
        consequences={<Preflight kind="still open" {...eligibility.mark_na} />}
        onConfirm={(reason) => bulkRun.mutate({
          ids: eligibility.mark_na.eligible.map((i) => i.id), action: "mark_na", reason,
        })}
      />

      <BulkAssignDialog
        open={bulk === "assign"} onClose={() => setBulk(null)}
        count={selectedRows.length} members={members.data ?? []}
        busy={bulkAssignRun.isPending}
        onConfirm={(owner) => bulkAssignRun.mutate({ ids: selectedRows.map((i) => i.id), owner })}
      />

      <ObligationSheet instanceId={openId} onClose={() => setParams({ open: null })} />
    </div>
  );
}

/* ================================================================ row body */

function renderRows({ rows, grouped, selected, toggleOne, ownerName, onOpen }: {
  rows: Instance[]; grouped: boolean; selected: Set<string>;
  toggleOne: (id: string) => void; ownerName: (id: string | null) => string | null;
  onOpen: (id: string) => void;
}) {
  if (!grouped) {
    return rows.map((i) => (
      <Row key={i.id} i={i} selected={selected.has(i.id)} onToggle={toggleOne}
        ownerName={ownerName} onOpen={onOpen} />
    ));
  }

  // Urgency bands answer "what do I do first?" without sorting or reading dates.
  const bands: { key: string; label: string; test: (i: Instance) => boolean }[] = [
    { key: "overdue", label: "Overdue", test: (i) => i.status === "overdue" },
    { key: "review", label: "Awaiting review", test: (i) => i.status === "ready_for_review" },
    {
      key: "week", label: "Due within 7 days", test: (i) => {
        const n = daysFromToday(i.due_date);
        return !CLOSED.has(i.status) && n !== null && n >= 0 && n <= 7;
      },
    },
    {
      key: "month", label: "Due this month", test: (i) => {
        const n = daysFromToday(i.due_date);
        return !CLOSED.has(i.status) && n !== null && n > 7 && n <= 31;
      },
    },
    { key: "later", label: "Later", test: (i) => !CLOSED.has(i.status) },
    { key: "closed", label: "Closed", test: () => true },
  ];

  const assigned = new Set<string>();
  const out: React.ReactNode[] = [];
  for (const band of bands) {
    const members = rows.filter((i) => !assigned.has(i.id) && band.test(i));
    members.forEach((i) => assigned.add(i.id));
    if (members.length === 0) continue;
    out.push(
      <tr key={`g-${band.key}`} className="group-row">
        <td colSpan={8}>
          <span className="row" style={{ gap: 8 }}>
            <span className="eyebrow">{band.label}</span>
            <span className="tag num">{members.length}</span>
          </span>
        </td>
      </tr>,
    );
    for (const i of members) {
      out.push(
        <Row key={i.id} i={i} selected={selected.has(i.id)} onToggle={toggleOne}
          ownerName={ownerName} onOpen={onOpen} />,
      );
    }
  }
  return out;
}

function Row({ i, selected, onToggle, ownerName, onOpen }: {
  i: Instance; selected: boolean; onToggle: (id: string) => void;
  ownerName: (id: string | null) => string | null; onOpen: (id: string) => void;
}) {
  const rel = relativeDue(i.due_date);
  const owner = ownerName(i.owner_user_id);
  const urgency = urgencyOf(i.status, i.due_date);

  return (
    <tr className="row-link" data-selected={selected} data-urgency={urgency} tabIndex={0}
      onClick={() => onOpen(i.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter") { e.preventDefault(); onOpen(i.id); }
        if (e.key === " ") { e.preventDefault(); onToggle(i.id); }
      }}>
      <td className="tight rail" onClick={(e) => e.stopPropagation()}>
        <Checkbox checked={selected} onChange={() => onToggle(i.id)}
          label={`Select ${i.title}`} />
      </td>
      <td>
        <div className="truncate" style={{ fontWeight: 550, maxWidth: 420 }}>{i.title}</div>
        <div className="micro faint row" style={{ gap: 6 }}>
          <span>{i.period_label}</span>
          {i.form_reference && <><span aria-hidden="true">·</span><span className="mono">{i.form_reference}</span></>}
          {i.state && <><span aria-hidden="true">·</span><span>{i.state}</span></>}
        </div>
      </td>
      <td className="muted"><span className="truncate" style={{ maxWidth: 150, display: "block" }}>{i.category}</span></td>
      <td className="tight"><RiskMeter level={i.risk_level} /></td>
      <td className="tight">
        {owner ? (
          <span className="row" style={{ gap: 6 }}>
            <Avatar label={owner} size={19} />
            <span className="truncate" style={{ maxWidth: 110 }}>{owner}</span>
          </span>
        ) : (
          <span className="micro" style={{ color: "var(--warn)" }} title="No owner — this will not appear in anyone's queue">
            Unassigned
          </span>
        )}
      </td>
      <td className="tight">
        <EvidenceDot status={i.status} />
      </td>
      <td className="tight">
        <div className="num">{fmtDateShort(i.due_date)}{i.working_day_adjusted ? "*" : ""}</div>
        <div className="micro" style={{
          color: rel.tone === "crit" ? "var(--crit)" : rel.tone === "warn" ? "var(--warn)" : "var(--ink-3)",
          fontWeight: rel.tone === "crit" ? 600 : 400,
        }}>{rel.text}</div>
      </td>
      <td className="tight"><StatusBadge status={i.status} /></td>
    </tr>
  );
}

/**
 * The list endpoint doesn't carry per-row evidence counts, so this shows what
 * the row's state genuinely implies rather than inventing a number: a filed
 * obligation has passed the evidence gate, an open one hasn't been checked yet.
 */
function EvidenceDot({ status }: { status: string }) {
  if (status === "completed") {
    return <span title="Evidence gate satisfied at approval" className="row"
      style={{ gap: 4, color: "var(--good)" }}><IconPaperclip size={12} /></span>;
  }
  if (status === "not_applicable") return <span className="faint">—</span>;
  return <span className="faint" title="Open in the detail panel to see attached evidence">
    <IconPaperclip size={12} style={{ opacity: .4 }} />
  </span>;
}

/* ============================================================== bulk parts */

/** Says exactly what will and won't be touched, before the user commits. */
function Preflight({ eligible, skipped, kind }:
  { eligible: Instance[]; skipped: number; kind: string }) {
  return (
    <div className="stack-sm">
      <Note tone={eligible.length === 0 ? "crit" : "info"}>
        <b>{pluralize(eligible.length, "obligation")}</b> will be changed.
        {skipped > 0 && (
          <> {skipped} selected {skipped === 1 ? "row is" : "rows are"} not {kind} and will be
            left untouched.</>
        )}
      </Note>
      {eligible.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--ink-2)" }}>
          {eligible.slice(0, 5).map((i) => (
            <li key={i.id} className="truncate">{i.title} · {i.period_label}</li>
          ))}
          {eligible.length > 5 && <li className="faint">and {eligible.length - 5} more</li>}
        </ul>
      )}
    </div>
  );
}

function BulkAssignDialog({ open, onClose, count, members, busy, onConfirm }: {
  open: boolean; onClose: () => void; count: number; members: Member[];
  busy: boolean; onConfirm: (owner: string) => void;
}) {
  const [owner, setOwner] = useState("");
  const [touched, setTouched] = useState(false);
  useEffect(() => { if (open) { setOwner(""); setTouched(false); } }, [open]);
  const error = touched && !owner ? "Choose who should own these obligations." : null;

  return (
    <Modal open={open} onClose={onClose}
      title={`Assign ${pluralize(count, "obligation")}`}
      description="The new owner is notified and these obligations move into their queue."
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn primary" disabled={busy}
            onClick={() => { setTouched(true); if (owner) onConfirm(owner); }}>
            {busy && <Spinner onDark />}Assign
          </button>
        </>
      }>
      <Field label="New owner" required error={error}>
        {(p) => (
          <select className="input" value={owner} onChange={(e) => setOwner(e.target.value)} {...p}>
            <option value="">Select a team member…</option>
            {members.map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {(m.full_name || m.email)} · {m.role === "compliance_admin" ? "Admin"
                  : m.role === "head" ? "Head" : "Preparer"}
              </option>
            ))}
          </select>
        )}
      </Field>
      {members.length === 0 && (
        <div style={{ marginTop: 10 }}>
          <Note tone="warn">
            No assignable members. Invite teammates from the Team page first.
          </Note>
        </div>
      )}
    </Modal>
  );
}

/* =================================================================== utils */

function humanAction(a: string): string {
  switch (a) {
    case "approve": return "Approved and filed, with evidence checks recorded.";
    case "submit": return "Sent for review.";
    case "mark_na": return "Marked not applicable with your reason on record.";
    case "assign": return "Ownership transferred.";
    default: return "";
  }
}

/** Back-compat: old links used ?status=… without a view. */
function inferViewFromLegacyParams(params: URLSearchParams): ViewId {
  if (params.get("mine") === "1") return "mine";
  if (params.get("window") === "week") return "week";
  const s = params.get("status");
  if (s === "overdue") return "overdue";
  if (s === "ready_for_review") return "review";
  return "all";
}
