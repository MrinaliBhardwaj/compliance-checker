"use client";
// Shared UI primitives — production-grade building blocks used across pages.
import { useEffect, type ReactNode } from "react";

export function Spinner() {
  return <span className="spinner" aria-label="loading" />;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="row" style={{ color: "var(--muted)", padding: 24 }}>
      <Spinner /> <span>{label}</span>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="banner err" role="alert">
      Couldn’t load this. {msg}
      {onRetry && (
        <button className="btn sm ghost" style={{ marginLeft: 10 }} onClick={onRetry}>Retry</button>
      )}
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty">
      <div style={{ fontWeight: 600, color: "var(--ink)" }}>{title}</div>
      {hint && <div style={{ marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending", in_progress: "In progress", ready_for_review: "Ready for review",
  completed: "Completed", overdue: "Overdue", not_applicable: "N/A",
};
export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge ${status}`}>
      <span className="dot" />{STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function RiskBadge({ level }: { level: string }) {
  return <span className={`badge risk-${level}`}>{level} risk</span>;
}

export function MatchBadge({ match }: { match: string }) {
  const label: Record<string, string> = {
    APPLICABLE: "Affects you", NEEDS_REVIEW: "May affect you", NOT_APPLICABLE: "Not applicable",
  };
  return <span className={`badge match-${match}`}>{label[match] ?? match}</span>;
}

export function Progress({ pct }: { pct: number }) {
  return (
    <div className="progress" aria-label={`${pct}% complete`}>
      <span style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  );
}

export function Drawer({ open, onClose, children }:
  { open: boolean; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true">
        <div className="between" style={{ marginBottom: 12 }}>
          <span className="muted" style={{ fontSize: 12 }}>Press Esc or click outside to close</span>
          <button className="btn sm ghost" aria-label="Close" onClick={onClose}>✕</button>
        </div>
        {children}
      </aside>
    </>
  );
}

export function fmtDate(d: string | null): string {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return d;
  }
}
