"use client";
// Legal Updates feed (PRD §8.4): AI-summarized, deterministically applicability-
// matched. Impact indicators (match badge + affected obligation count), review
// actions (admin/head only — preparers view, can't act).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listLegalUpdates, reviewLegalUpdate, type LegalUpdate } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/lib/toast";
import Shell from "@/components/Shell";
import { Empty, ErrorState, Loading, MatchBadge, fmtDate } from "@/components/ui";

export default function LegalUpdatesPage() {
  return <Shell><Feed /></Shell>;
}

function Feed() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const list = useQuery({ queryKey: ["legal-updates"], queryFn: listLegalUpdates });

  const review = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => reviewLegalUpdate(id, status),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["legal-updates"] }); toast("Recorded", "ok"); },
    onError: (e) => toast(e instanceof Error ? e.message : "Failed", "err"),
  });

  return (
    <div className="stack">
      <h1>Legal updates</h1>
      <p className="muted">Curated NBFC regulatory changes, summarized and matched to your profile.</p>

      {list.isLoading && <Loading />}
      {list.isError && <ErrorState error={list.error} onRetry={list.refetch} />}
      {list.data && (list.data.length === 0
        ? <Empty title="No updates yet" hint="Published regulatory changes will appear here." />
        : list.data.map((u: LegalUpdate) => (
          <div key={u.id} className="card stack">
            <div className="between">
              <h3 style={{ margin: 0 }}>{u.title}</h3>
              <MatchBadge match={u.match} />
            </div>
            <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
              {u.affected_obligations > 0 &&
                <span className="chip">Affects {u.affected_obligations} of your obligations</span>}
              {u.published_date && <span className="muted" style={{ fontSize: 12 }}>{fmtDate(u.published_date)}</span>}
              <span className="muted" style={{ fontSize: 12 }}>Status: {u.review_status}</span>
            </div>
            {u.ai_summary && <p style={{ margin: 0 }}>{u.ai_summary}</p>}
            {u.ai_impact_note && <p className="muted" style={{ margin: 0 }}>Impact: {u.ai_impact_note}</p>}
            <div className="row" style={{ gap: 8 }}>
              {can("review_legal") ? (
                <>
                  <button className="btn ok" disabled={review.isPending}
                    onClick={() => review.mutate({ id: u.id, status: "applicable" })}>Mark applicable</button>
                  <button className="btn ghost" disabled={review.isPending}
                    onClick={() => review.mutate({ id: u.id, status: "not_applicable" })}>Not applicable</button>
                </>
              ) : <span className="muted" style={{ fontSize: 12 }}>View only — an admin or head reviews updates.</span>}
              {u.source_url && <a href={u.source_url} target="_blank" rel="noreferrer">Source ↗</a>}
            </div>
          </div>
        )))}
    </div>
  );
}
