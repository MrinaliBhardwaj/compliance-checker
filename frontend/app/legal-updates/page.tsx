"use client";
// Legal updates — curated regulatory changes, matched against this entity.
//
// Rework notes:
//  • Impact leads. "Affects 14 of your obligations" is the reason to read an
//    update, so it sits at the top of the item rather than in a chip below the
//    title.
//  • Triage state is explicit: unreviewed items are separated from reviewed
//    ones and counted, so a feed of 40 items has a visible finish line.
//  • Dismissing an update as not applicable is a judgement an inspector may
//    question, so it now captures a reason instead of firing on one click.
//  • Where the deterministic matcher couldn't decide, the missing profile
//    fields are named — that turns "may affect you" into something the user can
//    actually resolve.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { listLegalUpdates, reviewLegalUpdate, type LegalUpdate } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errMessage, useToast } from "@/lib/toast";
import { fmtDate, humanize, pluralize, relativeTime } from "@/lib/format";
import Shell from "@/components/Shell";
import {
  IconCheckCircle, IconExternal, IconGavel, IconSparkle,
} from "@/components/icons";
import {
  Badge, ConfirmDialog, Empty, ErrorState, MatchBadge, Note, Segmented, Skeleton,
} from "@/components/ui";

type Filter = "todo" | "affecting" | "all";

export default function LegalUpdatesPage() {
  return <Shell><Feed /></Shell>;
}

function Feed() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [filter, setFilter] = useState<Filter>("todo");
  const [dismissing, setDismissing] = useState<LegalUpdate | null>(null);

  const list = useQuery({ queryKey: ["legal-updates"], queryFn: listLegalUpdates });
  const rows = list.data ?? [];

  const review = useMutation({
    mutationFn: ({ id, status, reason }: { id: string; status: string; reason?: string }) =>
      reviewLegalUpdate(id, status, reason),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ["legal-updates"] });
      setDismissing(null);
      toast.ok(
        v.status === "applicable" ? "Marked as applicable" : "Marked not applicable",
        "Your decision is recorded in the audit trail.",
      );
    },
    onError: (e) => toast.err("Couldn’t record that", errMessage(e)),
  });

  const counts = useMemo(() => ({
    todo: rows.filter((u) => u.review_status === "new").length,
    affecting: rows.filter((u) => u.match === "APPLICABLE").length,
    all: rows.length,
  }), [rows]);

  const shown = useMemo(() => {
    if (filter === "todo") return rows.filter((u) => u.review_status === "new");
    if (filter === "affecting") return rows.filter((u) => u.match === "APPLICABLE");
    return rows;
    // Highest impact first — applicable, then needs-review, then by recency.
  }, [rows, filter]);

  const ordered = useMemo(() => {
    const rank: Record<string, number> = { APPLICABLE: 0, NEEDS_REVIEW: 1, NOT_APPLICABLE: 2 };
    return [...shown].sort((a, b) =>
      (rank[a.match] ?? 3) - (rank[b.match] ?? 3)
      || b.affected_obligations - a.affected_obligations
      || (b.published_date ?? "").localeCompare(a.published_date ?? ""));
  }, [shown]);

  const canReview = can("review_legal");

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Legal updates</h1>
          <p className="lede">
            Curated NBFC regulatory changes. Summaries are AI-assisted; the applicability
            match is deterministic — it reuses the same engine that built your calendar.
          </p>
        </div>
        <Segmented label="Filter updates" value={filter} onChange={setFilter}
          options={[
            { value: "todo", label: "Needs triage", count: counts.todo },
            { value: "affecting", label: "Affects you", count: counts.affecting },
            { value: "all", label: "All", count: counts.all },
          ]} />
      </div>

      {!canReview && (
        <div style={{ marginBottom: 16 }}>
          <Note tone="mute">
            You can read updates here. Recording whether one applies is done by a
            compliance admin or head.
          </Note>
        </div>
      )}

      {list.isLoading && (
        <div className="stack-sm">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="panel"><div className="panel-body">
              <Skeleton w={240} h={14} />
              <div style={{ marginTop: 10 }}><Skeleton w="90%" h={10} /></div>
              <div style={{ marginTop: 6 }}><Skeleton w="70%" h={10} /></div>
            </div></div>
          ))}
        </div>
      )}
      {list.isError && <ErrorState error={list.error} onRetry={list.refetch} />}

      {list.data && ordered.length === 0 && (
        filter === "todo" && rows.length > 0 ? (
          <Empty icon={<IconCheckCircle size={16} />} title="Everything triaged"
            hint="No updates are waiting on a decision."
            action={<button className="btn" onClick={() => setFilter("all")}>
              See all {rows.length}
            </button>} />
        ) : (
          <Empty icon={<IconGavel size={16} />} title="No updates yet"
            hint="Published regulatory changes appear here, already matched against your compliance profile." />
        )
      )}

      {list.data && ordered.length > 0 && (
        <div className="stack-sm">
          {ordered.map((u) => (
            <UpdateCard key={u.id} u={u} canReview={canReview}
              busy={review.isPending}
              onApplicable={() => review.mutate({ id: u.id, status: "applicable" })}
              onDismiss={() => setDismissing(u)} />
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!dismissing} onClose={() => setDismissing(null)} busy={review.isPending}
        title="Mark not applicable"
        description={dismissing ? `“${dismissing.title}” will be filed as not affecting this entity.` : undefined}
        confirmLabel="Mark not applicable" tone="danger"
        reasonLabel="Why doesn’t this apply?" reasonRequired
        reasonHint="Recorded in the audit trail. An inspector may ask you to justify dismissing a regulatory change."
        consequences={dismissing && dismissing.match === "APPLICABLE" ? (
          <Note tone="crit">
            <b>The matcher says this does affect you</b>
            {dismissing.affected_obligations > 0
              && <> — it touches {pluralize(dismissing.affected_obligations, "of your obligations", "of your obligations")}</>}.
            Dismissing it overrides a deterministic result.
          </Note>
        ) : undefined}
        onConfirm={(reason) => {
          if (dismissing) review.mutate({ id: dismissing.id, status: "not_applicable", reason });
        }}
      />
    </div>
  );
}

function UpdateCard({ u, canReview, busy, onApplicable, onDismiss }: {
  u: LegalUpdate; canReview: boolean; busy: boolean;
  onApplicable: () => void; onDismiss: () => void;
}) {
  const triaged = u.review_status !== "new";
  const high = u.match === "APPLICABLE";

  return (
    <article className="panel" style={high ? { borderColor: "var(--crit-line)" } : undefined}>
      <div className="panel-body">
        <div className="between" style={{ alignItems: "flex-start", gap: 14 }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="row-wrap" style={{ gap: 7, marginBottom: 6 }}>
              <MatchBadge match={u.match} />
              {u.affected_obligations > 0 && (
                <Badge tone={high ? "crit" : "warn"}>
                  Touches {u.affected_obligations} of your obligations
                </Badge>
              )}
              {triaged && (
                <Badge tone={u.review_status === "not_applicable" ? "neutral" : "good"} dot>
                  {humanize(u.review_status)}
                </Badge>
              )}
              {u.law_id && <span className="tag is-mono">{u.law_id}</span>}
            </div>

            <h2 style={{ fontSize: 14 }}>{u.title}</h2>

            <div className="micro faint" style={{ marginTop: 3 }}>
              {u.published_date
                ? <>Published {fmtDate(u.published_date)} · {relativeTime(u.published_date)}</>
                : "Publication date not recorded"}
            </div>

            {u.ai_summary && (
              <p style={{ fontSize: 12.5, marginTop: 10, lineHeight: 1.6, maxWidth: "80ch" }}>
                {u.ai_summary}
              </p>
            )}

            {u.ai_impact_note && (
              <div className="row" style={{ gap: 7, marginTop: 8, alignItems: "flex-start" }}>
                <IconSparkle size={13} style={{ color: "var(--accent)", flex: "none", marginTop: 2 }} />
                <div>
                  <span className="eyebrow">AI impact note</span>
                  <p className="micro muted" style={{ marginTop: 2, maxWidth: "76ch" }}>
                    {u.ai_impact_note}
                  </p>
                </div>
              </div>
            )}

            {u.match === "NEEDS_REVIEW" && u.match_missing.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <Note tone="warn">
                  <b>The matcher couldn’t decide.</b> It needs these profile fields to be
                  certain: {u.match_missing.map(humanize).join(", ")}. Fill them in on the
                  compliance profile and this resolves itself.
                </Note>
              </div>
            )}
          </div>

          {u.source_url && (
            <a className="btn sm" href={u.source_url} target="_blank" rel="noreferrer"
              style={{ flex: "none" }}>
              Source <IconExternal size={11} />
            </a>
          )}
        </div>
      </div>

      {canReview && (
        <div className="panel-foot row" style={{ gap: 8 }}>
          {triaged ? (
            <span className="micro">
              Already triaged as <b>{humanize(u.review_status)}</b>. Recording a different
              decision replaces it in the trail.
            </span>
          ) : (
            <span className="micro">Does this affect your entity?</span>
          )}
          <span className="spacer" />
          <button className="btn sm good" disabled={busy} onClick={onApplicable}>
            Applies to us
          </button>
          <button className="btn sm" disabled={busy} onClick={onDismiss}>
            Doesn’t apply
          </button>
        </div>
      )}
    </article>
  );
}
