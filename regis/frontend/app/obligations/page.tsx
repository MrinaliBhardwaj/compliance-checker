"use client";
// Obligation tracker — the screen a compliance officer lives in.
//
// Second pass, focused on decision-making rather than presentation:
//  • Rows carry an explicit, explainable triage priority and sort by it. Sorting
//    109 overdue items by date alone put a 153-day-late board minute above a
//    3-day-late RBI return, which inverts real exposure. See priorityOf().
//  • The detail sheet navigates prev/next through the current filtered list, so
//    triaging 109 items is one pass instead of 109 open/close cycles.
//  • Bulk approve pre-checks the *evidence gate*, not just status. It used to
//    promise "5 obligations will be changed" and then fail all five, because the
//    server enforces a gate the list endpoint knows nothing about.
//  • Approve and mark-N/A offer Undo, since both are reversible via reopen.
//  • Row activation is a real button, so assistive tech announces it; j/k move
//    between rows and x toggles selection.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  bulkAssign, bulkTransition, checkEvidenceGates, getInstances, listAssignable,
  type BulkOutcome, type GateCheck, type Instance, type LifecycleAction, type Member,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errMessage, useToast } from "@/lib/toast";
import {
  daysFromToday, fmtDateShort, PRIORITY_EXPLAINER, priorityOf, relativeDue,
  statusLabel, urgencyOf, pluralize,
} from "@/lib/format";
import Shell from "@/components/Shell";
import ObligationSheet from "@/components/ObligationSheet";
import {
  IconCheck, IconFilter, IconList, IconSearch, IconUser, IconX,
} from "@/components/icons";
import {
  Avatar, Checkbox, ConfirmDialog, Definition, Empty, ErrorState, Field, InlineLoading,
  Modal, Note, PriorityBadge, ResultCount, RiskMeter, Segmented, Skeleton, SkeletonRows,
  SortableTh, Spinner, StatusBadge, useAnnounce, useDebounced, type SortDir,
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

type SortKey = "priority" | "due" | "title" | "risk" | "status" | "category";
const RISK_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };
const STATUS_ORDER: Record<string, number> = {
  overdue: 0, ready_for_review: 1, in_progress: 2, pending: 3, completed: 4, not_applicable: 5,
};
/** Bulk gate checks are one request per row; past this we ask rather than hammer. */
const GATE_CHECK_LIMIT = 60;

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
  const { announce, node: liveRegion } = useAnnounce();
  const tableRef = useRef<HTMLTableSectionElement>(null);

  /* ---- URL-backed state ------------------------------------------------ */
  const view = (params.get("view") as ViewId) ?? inferViewFromLegacyParams(params);
  const status = params.get("status") ?? "";
  const category = params.get("category") ?? "";
  // Priority is the default order: the product's job is "what do I do next",
  // and due-date order answers a different question (planning).
  const sortKey = (params.get("sort") as SortKey) ?? "priority";
  const sortDir = (params.get("dir") as SortDir) ?? (sortKey === "priority" ? "desc" : "asc");
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
    () => Array.from(new Set(rowsAll.map((i) => i.category))).sort(), [rowsAll]);

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
      priority: (a, b) => priorityOf(a).score - priorityOf(b).score,
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
  useEffect(() => {
    setSelected((prev) => {
      const next = new Set([...prev].filter((id) => visibleIds.includes(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [visibleIds]);

  const selectedRows = useMemo(() => sorted.filter((i) => selected.has(i.id)), [sorted, selected]);
  const allChecked = visibleIds.length > 0 && selected.size === visibleIds.length;
  const someChecked = selected.size > 0 && !allChecked;

  const toggleAll = () => {
    const next = allChecked ? new Set<string>() : new Set(visibleIds);
    setSelected(next);
    announce(next.size === 0 ? "Selection cleared" : `${pluralize(next.size, "row")} selected`);
  };
  const toggleOne = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      announce(n.size === 0 ? "Selection cleared" : `${pluralize(n.size, "row")} selected`);
      return n;
    });

  /* ---- keyboard triage -------------------------------------------------- */
  // j/k (and arrows) walk the rows; x selects; Enter opens via the row button.
  const onTableKeyDown = (e: React.KeyboardEvent) => {
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    const key = e.key.toLowerCase();
    const buttons = Array.from(
      tableRef.current?.querySelectorAll<HTMLButtonElement>("button.row-open") ?? []);
    const idx = buttons.indexOf(document.activeElement as HTMLButtonElement);

    if (key === "j" || e.key === "ArrowDown") {
      e.preventDefault();
      buttons[Math.min(idx + 1, buttons.length - 1)]?.focus();
    } else if (key === "k" || e.key === "ArrowUp") {
      e.preventDefault();
      buttons[Math.max(idx - 1, 0)]?.focus();
    } else if (key === "x" && idx >= 0) {
      e.preventDefault();
      const id = buttons[idx].dataset.id;
      if (id) toggleOne(id);
    }
  };

  /* ---- mutations -------------------------------------------------------- */
  const [bulk, setBulk] = useState<null | "approve" | "submit" | "mark_na" | "assign">(null);

  const undoable = can("reopen");
  const runUndo = (ids: string[], what: string) => {
    void bulkTransition(ids, "reopen", {
      reason: `Undo — ${what} reversed by the same user immediately after the action.`,
    }).then((res) => {
      qc.invalidateQueries({ queryKey: ["tracker"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      const ok = res.filter((r) => r.ok).length;
      if (ok === ids.length) toast.ok(`Reopened ${pluralize(ok, "obligation")}`);
      else toast.err(`Reopened ${ok} of ${ids.length}`, "The rest could not be reopened.");
    });
  };

  const bulkRun = useMutation({
    mutationFn: async (job: {
      ids: string[]; action: LifecycleAction; reason?: string; override?: boolean;
    }) => bulkTransition(job.ids, job.action, {
      ...(job.reason ? { reason: job.reason } : {}),
      ...(job.override ? { override_evidence: true } : {}),
    }),
    onSuccess: (outcomes, job) => reportBulk(outcomes, job.action),
    onError: (e) => toast.err("Bulk action failed", errMessage(e)),
  });

  const bulkAssignRun = useMutation({
    mutationFn: async (job: { ids: string[]; owner: string }) => bulkAssign(job.ids, job.owner),
    onSuccess: (outcomes) => reportBulk(outcomes, "assign"),
    onError: (e) => toast.err("Bulk assign failed", errMessage(e)),
  });

  function reportBulk(outcomes: BulkOutcome[], what: string) {
    const okIds = outcomes.filter((o) => o.ok).map((o) => o.id);
    const failed = outcomes.length - okIds.length;
    qc.invalidateQueries({ queryKey: ["tracker"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    setSelected(new Set());
    setBulk(null);

    const reversible = (what === "approve" || what === "mark_na") && undoable && okIds.length > 0;
    if (failed === 0) {
      toast.ok(
        `${pluralize(okIds.length, "obligation")} updated`,
        humanAction(what),
        reversible ? { label: "Undo", onClick: () => runUndo(okIds, humanAction(what)) } : undefined,
      );
    } else {
      const firstErr = outcomes.find((o) => !o.ok)?.error;
      toast.err(
        `${okIds.length} updated, ${failed} failed`,
        firstErr ? `First error: ${firstErr}` : "Some obligations could not be changed.",
      );
    }
    announce(`${okIds.length} updated, ${failed} failed`);
  }

  /* ---- eligibility (status only; the evidence gate is checked live) ----- */
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
    setParams({
      sort: k,
      dir: sortKey === k ? (sortDir === "asc" ? "desc" : "asc") : (k === "priority" ? "desc" : "asc"),
    });

  const filtersActive = !!(status || category || q.trim());
  const clearFilters = () => { setQInput(""); setParams({ status: null, category: null, q: null }); };

  /* ---- render ---------------------------------------------------------- */
  return (
    <div>
      {liveRegion}

      <div className="page-head">
        <div>
          <h1>Obligations</h1>
          <p className="lede">
            Every dated filing for this entity, ordered by what deserves attention first.
            Select rows to act on many at once.
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

        {all.isLoading && <SkeletonRows rows={10} cols={6} />}
        {all.isError && <div style={{ padding: 14 }}>
          <ErrorState error={all.error} onRetry={all.refetch}
            deniedWhat="the obligation tracker" deniedWho="members of this workspace" />
        </div>}

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
          <div className="tbl-wrap stack-sm-screen">
            <table className={`tbl stackable ${dense ? "dense" : ""}`}>
              <caption className="sr-only">
                Obligations, {VIEWS.find((v) => v.id === view)?.label}. {sorted.length} rows.
                Use J and K to move between rows, X to select, Enter to open.
              </caption>
              <thead>
                <tr>
                  <th className="tight" style={{ paddingLeft: 14 }}>
                    <Checkbox checked={allChecked} indeterminate={someChecked} onChange={toggleAll}
                      label={allChecked ? "Deselect all rows" : "Select all rows"} />
                  </th>
                  <SortableTh id="title" sort={{ key: sortKey, dir: sortDir }} onSort={onSort}>Obligation</SortableTh>
                  <SortableTh id="priority" sort={{ key: sortKey, dir: sortDir }} onSort={onSort} className="tight">
                    Priority
                  </SortableTh>
                  <SortableTh id="category" sort={{ key: sortKey, dir: sortDir }} onSort={onSort}>Category</SortableTh>
                  <SortableTh id="risk" sort={{ key: sortKey, dir: sortDir }} onSort={onSort} className="tight">Risk</SortableTh>
                  <th className="tight">Owner</th>
                  <SortableTh id="due" sort={{ key: sortKey, dir: sortDir }} onSort={onSort} className="tight">Due</SortableTh>
                  <SortableTh id="status" sort={{ key: sortKey, dir: sortDir }} onSort={onSort} className="tight">Status</SortableTh>
                </tr>
              </thead>
              <tbody ref={tableRef} onKeyDown={onTableKeyDown}>
                {renderRows({
                  rows: sorted, grouped, selected, toggleOne, ownerName, openId,
                  onOpen: (id) => setParams({ open: id }),
                })}
              </tbody>
            </table>
          </div>
        )}

        {all.data && sorted.length > 0 && (
          <div className="panel-foot between">
            <span className="row" style={{ gap: 10 }}>
              <ResultCount shown={sorted.length} total={rowsAll.length} />
              <span className="faint">
                <Definition tip={PRIORITY_EXPLAINER}>How priority is calculated</Definition>
              </span>
            </span>
            <span className="row-wrap" style={{ gap: 12, justifyContent: "flex-end" }}>
              <span className="faint">J / K move · X selects · Enter opens</span>
              <span>* date shifted to a working day</span>
            </span>
          </div>
        )}
      </div>

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
          <button className="btn sm" onClick={() => { setSelected(new Set()); announce("Selection cleared"); }}>
            Clear
          </button>
        </div>
      )}

      <BulkApproveDialog
        open={bulk === "approve"} onClose={() => setBulk(null)}
        rows={eligibility.approve.eligible} skipped={eligibility.approve.skipped}
        busy={bulkRun.isPending}
        onApprove={(ids, override, reason) =>
          bulkRun.mutate({ ids, action: "approve", override, reason })}
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

      <ObligationSheet
        instanceId={openId}
        onClose={() => setParams({ open: null })}
        siblingIds={visibleIds}
        onNavigate={(id) => setParams({ open: id })}
        contextLabel={VIEWS.find((v) => v.id === view)?.label}
      />
    </div>
  );
}

/* ================================================================ row body */

function renderRows({ rows, grouped, selected, toggleOne, ownerName, onOpen, openId }: {
  rows: Instance[]; grouped: boolean; selected: Set<string>;
  toggleOne: (id: string) => void; ownerName: (id: string | null) => string | null;
  onOpen: (id: string) => void; openId: string | null;
}) {
  const row = (i: Instance) => (
    <Row key={i.id} i={i} selected={selected.has(i.id)} onToggle={toggleOne}
      ownerName={ownerName} onOpen={onOpen} isOpen={openId === i.id} />
  );

  if (!grouped) return rows.map(row);

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
    for (const i of members) out.push(row(i));
  }
  return out;
}

function Row({ i, selected, onToggle, ownerName, onOpen, isOpen }: {
  i: Instance; selected: boolean; onToggle: (id: string) => void;
  ownerName: (id: string | null) => string | null; onOpen: (id: string) => void;
  isOpen: boolean;
}) {
  const rel = relativeDue(i.due_date);
  const owner = ownerName(i.owner_user_id);
  const urgency = urgencyOf(i.status, i.due_date);
  const p = priorityOf(i);

  return (
    <tr className="row-link" data-selected={selected} data-urgency={urgency}
      data-open={isOpen || undefined} onClick={() => onOpen(i.id)}>
      <td className="tight rail" data-col="select" onClick={(e) => e.stopPropagation()}>
        <Checkbox checked={selected} onChange={() => onToggle(i.id)}
          label={`Select ${i.title}, ${i.period_label}`} />
      </td>
      <td data-col="title">
        {/* A real button carries the accessible name and the focus ring, so
            assistive tech announces an activatable control rather than a cell. */}
        <button type="button" className="row-open" data-id={i.id}
          onClick={(e) => { e.stopPropagation(); onOpen(i.id); }}>
          <span className="truncate" style={{ fontWeight: 550, display: "block", maxWidth: 420 }}>
            {i.title}
          </span>
        </button>
        <div className="micro faint row" style={{ gap: 6 }}>
          <span>{i.period_label}</span>
          {i.form_reference && <><span aria-hidden="true">·</span><span className="mono">{i.form_reference}</span></>}
          {i.state && <><span aria-hidden="true">·</span><span>{i.state}</span></>}
        </div>
      </td>
      <td className="tight" data-col="priority"><PriorityBadge p={p} /></td>
      <td className="muted" data-col="category">
        <span className="truncate" style={{ maxWidth: 150, display: "block" }}>{i.category}</span>
      </td>
      <td className="tight" data-col="risk"><RiskMeter level={i.risk_level} compact /></td>
      <td className="tight" data-col="owner">
        {owner ? (
          <span className="row" style={{ gap: 6 }}>
            <Avatar label={owner} size={19} />
            <span className="truncate" style={{ maxWidth: 110 }}>{owner}</span>
          </span>
        ) : (
          <span className="micro" style={{ color: "var(--warn)" }}
            title="No owner — this will not appear in anyone's queue">Unassigned</span>
        )}
      </td>
      <td className="tight" data-col="due">
        <div className="num">{fmtDateShort(i.due_date)}{i.working_day_adjusted ? "*" : ""}</div>
        <div className="micro" style={{
          color: rel.tone === "crit" ? "var(--crit)" : rel.tone === "warn" ? "var(--warn)" : "var(--ink-3)",
          fontWeight: rel.tone === "crit" ? 600 : 400,
        }}>{rel.text}</div>
      </td>
      <td className="tight" data-col="status"><StatusBadge status={i.status} /></td>
    </tr>
  );
}

/* ============================================================== bulk parts */

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

/**
 * Bulk approve, pre-flighted against the *evidence gate*.
 *
 * Status eligibility is not enough: the server refuses to complete an obligation
 * whose primary evidence is missing. The previous dialog promised "5 will be
 * changed" and then all five failed. This asks each one first and splits the
 * batch into what will file cleanly and what would need an audited override —
 * two genuinely different decisions, so they get two separate paths.
 */
function BulkApproveDialog({ open, onClose, rows, skipped, busy, onApprove }: {
  open: boolean; onClose: () => void; rows: Instance[]; skipped: number; busy: boolean;
  onApprove: (ids: string[], override: boolean, reason?: string) => void;
}) {
  const [checks, setChecks] = useState<GateCheck[] | null>(null);
  const [checking, setChecking] = useState(false);
  const [tooMany, setTooMany] = useState(false);
  const [overrideMode, setOverrideMode] = useState(false);
  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (!open) return;
    setChecks(null); setOverrideMode(false); setReason(""); setTouched(false);
    if (rows.length > GATE_CHECK_LIMIT) { setTooMany(true); return; }
    setTooMany(false);
    setChecking(true);
    let cancelled = false;
    checkEvidenceGates(rows.map((r) => r.id))
      .then((res) => { if (!cancelled) setChecks(res); })
      .finally(() => { if (!cancelled) setChecking(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const byId = useMemo(() => new Map(rows.map((r) => [r.id, r])), [rows]);
  const ready = (checks ?? []).filter((c) => c.completeness?.eligible_for_completion);
  const needsOverride = (checks ?? []).filter(
    (c) => c.completeness && !c.completeness.eligible_for_completion);
  const unknown = (checks ?? []).filter((c) => !c.completeness);

  const reasonError = reason.trim().length < 8
    ? "Give enough detail for an auditor to understand the decision (min. 8 characters)."
    : null;

  const title = overrideMode
    ? `Approve ${pluralize(needsOverride.length, "obligation")} without primary evidence`
    : `Approve ${pluralize(rows.length, "obligation")}`;

  return (
    <Modal open={open} onClose={onClose} width={560} title={title}
      description={overrideMode
        ? "The evidence gate normally blocks these. Overriding is permitted but permanently recorded against each one."
        : "Each is checked against its evidence gate before anything is submitted."}
      footer={
        overrideMode ? (
          <>
            <button className="btn" onClick={() => setOverrideMode(false)} disabled={busy}>Back</button>
            <button className="btn danger-solid" disabled={busy || (touched && !!reasonError)}
              onClick={() => {
                setTouched(true);
                if (reasonError) return;
                onApprove(needsOverride.map((c) => c.id), true, reason.trim());
              }}>
              {busy && <Spinner onDark />}Override and approve {needsOverride.length}
            </button>
          </>
        ) : (
          <>
            <button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
            <button className="btn primary" disabled={busy || checking || ready.length === 0}
              onClick={() => onApprove(ready.map((c) => c.id), false)}>
              {busy && <Spinner onDark />}
              {ready.length === 0 ? "Nothing ready to file" : `Approve ${ready.length} ready`}
            </button>
          </>
        )
      }>
      {tooMany ? (
        <Note tone="warn">
          <b>{rows.length} rows selected.</b> Checking evidence for more than {GATE_CHECK_LIMIT} at
          once would take a while and hammer the server. Narrow the selection and try again.
        </Note>
      ) : checking ? (
        <InlineLoading label={`Checking evidence for ${pluralize(rows.length, "obligation")}…`} />
      ) : overrideMode ? (
        <div className="stack-sm">
          <Note tone="crit">
            <b>These {needsOverride.length} are missing primary evidence.</b> Approving them
            records an override against each, visible to auditors in the trail.
          </Note>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--ink-2)" }}>
            {needsOverride.slice(0, 6).map((c) => {
              const r = byId.get(c.id);
              const missing = c.completeness?.missing.map(([ev]) => ev).join(", ");
              return (
                <li key={c.id}>
                  <span className="truncate">{r?.title ?? c.id}</span>
                  {missing && <span className="faint"> — missing {missing}</span>}
                </li>
              );
            })}
            {needsOverride.length > 6 && (
              <li className="faint">and {needsOverride.length - 6} more</li>
            )}
          </ul>
          <Field label="Why are you approving without primary evidence?" required
            hint="The same reason is recorded against every obligation in this batch."
            error={touched ? reasonError : null}>
            {(p) => (
              <textarea className="input" rows={3} value={reason} autoFocus
                onChange={(e) => setReason(e.target.value)} onBlur={() => setTouched(true)}
                placeholder="e.g. Acknowledgements held in physical file; digitisation scheduled for this quarter." {...p} />
            )}
          </Field>
        </div>
      ) : (
        <div className="stack-sm">
          <Note tone={ready.length > 0 ? "good" : "warn"}>
            <b>{pluralize(ready.length, "obligation")} can be filed now</b> — primary evidence
            is on record.
            {skipped > 0 && <> {skipped} selected {skipped === 1 ? "row was" : "rows were"} not
              awaiting review and are excluded.</>}
          </Note>

          {needsOverride.length > 0 && (
            <Note tone="warn">
              <b>{pluralize(needsOverride.length, "obligation")} would be blocked</b> by the
              evidence gate. Filing them anyway requires a recorded override.
              <div style={{ marginTop: 7 }}>
                <button className="btn sm danger" onClick={() => setOverrideMode(true)}>
                  Review and override {needsOverride.length}
                </button>
              </div>
            </Note>
          )}

          {unknown.length > 0 && (
            <Note tone="crit">
              <b>Couldn’t check {pluralize(unknown.length, "obligation")}.</b> They are excluded
              from this batch rather than attempted blindly.
            </Note>
          )}

          {ready.length > 0 && (
            <div>
              <div className="eyebrow" style={{ marginBottom: 5 }}>Will be filed</div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--ink-2)" }}>
                {ready.slice(0, 5).map((c) => (
                  <li key={c.id} className="truncate">
                    {byId.get(c.id)?.title ?? c.id}
                    <span className="faint"> · {byId.get(c.id)?.period_label}</span>
                  </li>
                ))}
                {ready.length > 5 && <li className="faint">and {ready.length - 5} more</li>}
              </ul>
            </div>
          )}
        </div>
      )}
    </Modal>
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

function inferViewFromLegacyParams(params: URLSearchParams): ViewId {
  if (params.get("mine") === "1") return "mine";
  if (params.get("window") === "week") return "week";
  const s = params.get("status");
  if (s === "overdue") return "overdue";
  if (s === "ready_for_review") return "review";
  return "all";
}
