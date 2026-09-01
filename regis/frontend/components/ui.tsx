"use client";
// Shared UI primitives.
//
// Two rules drive this file:
//   1. Every overlay traps focus, closes on Escape, and restores focus on exit.
//      The old drawer *told* users "press Esc" without implementing it.
//   2. No native prompt()/confirm() anywhere. In an audited product the reason
//      string a user types becomes a permanent record — it deserves a labelled,
//      validated field, not an unstyled browser dialog.
import {
  useCallback, useEffect, useId, useLayoutEffect, useRef, useState,
  type ReactNode,
} from "react";
import {
  IconAlert, IconCheckCircle, IconChevronDown, IconCheck, IconInfo, IconLock,
  IconMinus, IconSearch, IconX, IconXCircle,
} from "@/components/icons";
import type { PriorityBand, Tone } from "@/lib/format";
import { PRIORITY_LABEL, STATUS_META, statusLabel, statusTone } from "@/lib/format";

/* ========================================================== overlay plumbing */

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),' +
  'textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

/**
 * Escape-to-close, focus trap, initial focus and focus restoration for any
 * overlay. Also locks background scroll so the page behind doesn't drift.
 */
function useOverlay(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  const restoreTo = useRef<HTMLElement | null>(null);

  useLayoutEffect(() => {
    if (!open) return;
    restoreTo.current = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Focus the first meaningful control, else the panel itself.
    const node = ref.current;
    const first = node?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? node)?.focus();
    return () => {
      document.body.style.overflow = prevOverflow;
      restoreTo.current?.focus?.();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); onClose(); return; }
      if (e.key !== "Tab") return;
      const node = ref.current;
      if (!node) return;
      const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE))
        .filter((el) => el.offsetParent !== null || el === document.activeElement);
      if (items.length === 0) { e.preventDefault(); return; }
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [open, onClose]);

  return ref;
}

/** Close-on-outside-click for popovers and menus. */
export function useDismissOnOutside<T extends HTMLElement>(
  open: boolean, onClose: () => void,
) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);
  return ref;
}

/* ================================================================== loading */

export function Spinner({ onDark = false }: { onDark?: boolean }) {
  return <span className={`spinner${onDark ? " on-dark" : ""}`} role="status" aria-label="Loading" />;
}

export function Skeleton({ w = "100%", h = 12, r }: { w?: number | string; h?: number; r?: number }) {
  return <span className="sk" aria-hidden="true"
    style={{ display: "block", width: w, height: h, borderRadius: r }} />;
}

/**
 * Table skeletons instead of a page spinner: navigation keeps the layout, so
 * nothing jumps when data lands and the user can already read the columns.
 */
export function SkeletonRows({ rows = 8, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div aria-hidden="true">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="row"
          style={{ padding: "9px 10px", borderBottom: "1px solid var(--rule)", gap: 20 }}>
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} h={11}
              w={c === 0 ? `${34 + ((r * 7) % 22)}%` : c === cols - 1 ? 68 : 82} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonMetrics() {
  return (
    <div className="metric-strip" aria-hidden="true">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="metric" style={{ cursor: "default" }}>
          <Skeleton w={72} h={10} />
          <div style={{ marginTop: 11 }}><Skeleton w={44} h={22} /></div>
          <div style={{ marginTop: 8 }}><Skeleton w={92} h={9} /></div>
        </div>
      ))}
    </div>
  );
}

export function InlineLoading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="row muted" style={{ padding: 18, fontSize: 12.5 }}>
      <Spinner /> <span>{label}</span>
    </div>
  );
}

/* =================================================================== states */

/**
 * Errors never auto-dismiss and never lose the technical detail — a compliance
 * officer filing a support ticket needs the exact server message.
 */
export function ErrorState({ error, onRetry, title = "Couldn’t load this", deniedWhat, deniedWho }:
  { error: unknown; onRetry?: () => void; title?: string;
    deniedWhat?: string; deniedWho?: string }) {
  const [showDetail, setShowDetail] = useState(false);
  const msg = error instanceof Error ? error.message : String(error);
  const status = (error as { status?: number })?.status;

  // A 403 is an answer, not a failure. Retrying it just makes the user wait for
  // the same refusal, so it renders as a permission state instead of red alarm.
  if (status === 403) {
    return <PermissionDenied what={deniedWhat ?? "this"} who={deniedWho ?? "users with a higher role"} />;
  }

  const human = status === 403 ? "You don’t have permission to view this."
    : status === 404 ? "That record no longer exists."
    : status === 0 ? "Couldn’t reach the server. Check your connection."
    : status && status >= 500 ? "The server had a problem. This is usually temporary."
    : msg;

  return (
    <div className="note note-crit" role="alert">
      <IconAlert className="note-ico" />
      <div className="note-body">
        <b>{title}</b>
        <div style={{ marginTop: 2 }}>{human}</div>
        <div className="row" style={{ marginTop: 8, gap: 6 }}>
          {onRetry && <button className="btn sm" onClick={onRetry}>Try again</button>}
          {human !== msg && (
            <button className="btn sm ghost" onClick={() => setShowDetail((v) => !v)}
              aria-expanded={showDetail}>
              {showDetail ? "Hide detail" : "Show detail"}
            </button>
          )}
        </div>
        {showDetail && (
          <pre className="mono" style={{
            marginTop: 8, whiteSpace: "pre-wrap", wordBreak: "break-word",
            background: "var(--surface)", padding: 8, borderRadius: "var(--r-xs)",
            border: "1px solid var(--rule)", color: "var(--ink-2)",
          }}>{status ? `HTTP ${status} — ` : ""}{msg}</pre>
        )}
      </div>
    </div>
  );
}

/** Empty states always name the next action — a dead end is a design failure. */
export function Empty({ icon, title, hint, action }: {
  icon?: ReactNode; title: string; hint?: string; action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-ico">{icon ?? <IconSearch size={16} />}</div>
      <h3>{title}</h3>
      {hint && <p>{hint}</p>}
      {action && <div className="empty-act">{action}</div>}
    </div>
  );
}

/**
 * Permission denial explains *who* can do it and offers a way forward, instead
 * of silently redirecting (which reads as a bug).
 */
export function PermissionDenied({ what, who, action }:
  { what: string; who: string; action?: ReactNode }) {
  return (
    <Empty
      icon={<IconLock size={16} />}
      title={`You don’t have access to ${what}`}
      hint={`This is limited to ${who}. Ask a compliance admin if you need it — your current role is shown in the sidebar.`}
      action={action}
    />
  );
}

/* =================================================================== badges */

export function Badge({ tone = "neutral", dot = false, children, title }:
  { tone?: Tone; dot?: boolean; children: ReactNode; title?: string }) {
  return (
    <span className={`badge t-${tone}`} title={title}>
      {dot && <span className="dot" />}{children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge tone={statusTone(status)} dot title={STATUS_META[status]?.help}>
      {statusLabel(status)}
    </Badge>
  );
}

/**
 * Risk as a 3-bar ramp + word. Colour alone never carries it — the bar count
 * and the label both encode level, so it survives colour-blindness and print.
 */
export function RiskMeter({ level, compact = false }: { level: string; compact?: boolean }) {
  const l = (level || "low").toLowerCase();
  return (
    <span className="risk" data-level={l} title={`${l} risk`}>
      <span className="bars" aria-hidden="true"><i /><i /><i /></span>
      {!compact && <span style={{ textTransform: "capitalize" }}>{l}</span>}
      <span className="sr-only">{l} risk</span>
    </span>
  );
}

export function MatchBadge({ match }: { match: string }) {
  const map: Record<string, { label: string; tone: Tone }> = {
    APPLICABLE: { label: "Affects you", tone: "crit" },
    NEEDS_REVIEW: { label: "May affect you", tone: "warn" },
    NOT_APPLICABLE: { label: "Not applicable", tone: "neutral" },
  };
  const m = map[match] ?? { label: match, tone: "neutral" as Tone };
  return <Badge tone={m.tone} dot>{m.label}</Badge>;
}

export function Avatar({ label, size = 22 }: { label: string; size?: number }) {
  const s = label.trim();
  const text = s.includes("@") ? s[0] : s.split(/\s+/).map((p) => p[0]).slice(0, 2).join("");
  return (
    <span aria-hidden="true" style={{
      width: size, height: size, borderRadius: "50%", flex: "none",
      background: "var(--surface-3)", color: "var(--ink-2)", display: "grid",
      placeItems: "center", fontSize: size * 0.42, fontWeight: 600,
      border: "1px solid var(--rule)", textTransform: "uppercase", letterSpacing: 0,
    }}>{text || "?"}</span>
  );
}

/* ================================================================= progress */

export function Meter({ pct, tone, label }: { pct: number; tone?: Tone; label?: string }) {
  const v = Math.max(0, Math.min(100, Math.round(pct)));
  const cls = tone === "good" ? "good" : tone === "warn" ? "warn" : tone === "crit" ? "crit" : "";
  return (
    <div className={`meter ${cls}`} role="progressbar" aria-valuenow={v} aria-valuemin={0}
      aria-valuemax={100} aria-label={label ?? `${v}% complete`}>
      <span style={{ width: `${v}%` }} />
    </div>
  );
}

/** Proportional status mix — one glance says where the portfolio sits. */
export function DistBar({ segments }: { segments: { key: string; n: number; tone: Tone; label: string }[] }) {
  const total = segments.reduce((s, x) => s + x.n, 0) || 1;
  const color: Record<Tone, string> = {
    crit: "var(--crit-solid)", warn: "var(--warn)", good: "var(--good)",
    info: "var(--info)", neutral: "var(--rule-2)",
  };
  return (
    <div className="distbar" role="img"
      aria-label={segments.map((s) => `${s.label}: ${s.n}`).join(", ")}>
      {segments.filter((s) => s.n > 0).map((s) => (
        <span key={s.key} title={`${s.label}: ${s.n}`}
          style={{ width: `${(s.n / total) * 100}%`, background: color[s.tone] }} />
      ))}
    </div>
  );
}

/* =================================================================== inputs */

export function Field({ label, required, hint, error, children, id: idProp }: {
  label: string; required?: boolean; hint?: string; error?: string | null;
  children: (props: { id: string; "aria-invalid"?: boolean; "aria-describedby"?: string }) => ReactNode;
  id?: string;
}) {
  const auto = useId();
  const id = idProp ?? auto;
  const describedBy = error ? `${id}-err` : hint ? `${id}-hint` : undefined;
  return (
    <div className="field">
      <label className="lbl" htmlFor={id}>
        {label}{required && <span className="req" aria-hidden="true">*</span>}
        {required && <span className="sr-only">(required)</span>}
      </label>
      {children({ id, "aria-invalid": error ? true : undefined, "aria-describedby": describedBy })}
      {hint && !error && <div className="hint" id={`${id}-hint`}>{hint}</div>}
      {error && (
        <div className="err" id={`${id}-err`} role="alert">
          <IconAlert size={12} />{error}
        </div>
      )}
    </div>
  );
}

export function Checkbox({ checked, onChange, label, indeterminate = false, disabled }: {
  checked: boolean; onChange: (v: boolean) => void; label: string;
  indeterminate?: boolean; disabled?: boolean;
}) {
  const state = indeterminate ? "mixed" : checked ? "true" : "false";
  return (
    <button type="button" className="check" data-on={state} disabled={disabled}
      role="checkbox" aria-checked={indeterminate ? "mixed" : checked} aria-label={label}
      onClick={(e) => { e.stopPropagation(); onChange(!checked); }}>
      {indeterminate ? <IconMinus size={11} /> : checked ? <IconCheck size={11} /> : null}
    </button>
  );
}

export function Segmented<T extends string>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; label: string;
  options: { value: T; label: string; count?: number }[];
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}>
          {o.label}
          {o.count != null && <span className="num" style={{ opacity: .6, marginLeft: 4 }}>{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

/* ================================================================ overlays  */

/** Right-hand detail sheet. Labelled, trapped, Escape-closable — for real. */
export function Sheet({ open, onClose, title, children, footer, tabs }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode;
  footer?: ReactNode; tabs?: ReactNode;
}) {
  const ref = useOverlay(open, onClose);
  const titleId = useId();
  if (!open) return null;
  return (
    <>
      <div className="scrim" onClick={onClose} aria-hidden="true" />
      <div className="sheet" ref={ref} role="dialog" aria-modal="true"
        aria-labelledby={titleId} tabIndex={-1}>
        <div className="sheet-head">
          <div className="between" style={{ alignItems: "flex-start" }}>
            <div id={titleId} style={{ minWidth: 0 }}>{title}</div>
            <button className="btn icon ghost" onClick={onClose} aria-label="Close panel">
              <IconX size={15} />
            </button>
          </div>
        </div>
        {tabs}
        <div className="sheet-body">{children}</div>
        {footer && <div className="sheet-foot">{footer}</div>}
      </div>
    </>
  );
}

export function Modal({ open, onClose, title, description, children, footer, width }: {
  open: boolean; onClose: () => void; title: string; description?: ReactNode;
  children?: ReactNode; footer?: ReactNode; width?: number;
}) {
  const ref = useOverlay(open, onClose);
  const titleId = useId();
  const descId = useId();
  if (!open) return null;
  return (
    <div className="modal-wrap">
      <div className="scrim" onClick={onClose} aria-hidden="true" />
      <div className="modal" ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined} tabIndex={-1}
        style={width ? { width: `min(${width}px, 100%)` } : undefined}>
        <div className="modal-head">
          <h2 id={titleId}>{title}</h2>
          {description && (
            <p id={descId} className="muted" style={{ marginTop: 5, fontSize: 12.5 }}>{description}</p>
          )}
        </div>
        {children && <div className="modal-body">{children}</div>}
        <div className="modal-foot">{footer}</div>
      </div>
    </div>
  );
}

/**
 * Confirm + optional reason capture. Replaces prompt()/confirm().
 * When `reasonRequired`, the primary action stays disabled until a usable
 * reason exists — the text lands in an immutable audit record, so "asdf" and
 * an empty string are both worth preventing.
 */
export function ConfirmDialog({
  open, onClose, onConfirm, title, description, confirmLabel = "Confirm",
  tone = "neutral", reasonLabel, reasonRequired = false, reasonHint, busy = false,
  consequences,
}: {
  open: boolean; onClose: () => void; onConfirm: (reason?: string) => void | Promise<void>;
  title: string; description?: ReactNode; confirmLabel?: string;
  tone?: "neutral" | "danger"; reasonLabel?: string; reasonRequired?: boolean;
  reasonHint?: string; busy?: boolean; consequences?: ReactNode;
}) {
  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);
  useEffect(() => { if (open) { setReason(""); setTouched(false); } }, [open]);

  const trimmed = reason.trim();
  const error = !reasonRequired ? null
    : trimmed.length === 0 ? "A reason is required — it is written to the audit trail."
    : trimmed.length < 8 ? "Give enough detail for an auditor to understand the decision (min. 8 characters)."
    : null;
  const blocked = !!error;

  return (
    <Modal open={open} onClose={onClose} title={title} description={description}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
          <button
            className={`btn ${tone === "danger" ? "danger-solid" : "primary"}`}
            disabled={busy || (touched ? blocked : false)}
            onClick={() => {
              setTouched(true);
              if (blocked) return;
              void onConfirm(reasonLabel ? trimmed : undefined);
            }}>
            {busy && <Spinner onDark />}{confirmLabel}
          </button>
        </>
      }>
      {consequences && <div style={{ marginBottom: reasonLabel ? 14 : 0 }}>{consequences}</div>}
      {reasonLabel && (
        <Field label={reasonLabel} required={reasonRequired}
          hint={reasonHint ?? "Recorded permanently in the audit trail."}
          error={touched ? error : null}>
          {(p) => (
            <textarea className="input" rows={3} value={reason} autoFocus
              onChange={(e) => setReason(e.target.value)} onBlur={() => setTouched(true)}
              placeholder="e.g. Entity did not undertake any FDI transactions in this period." {...p} />
          )}
        </Field>
      )}
    </Modal>
  );
}

/* ================================================================= popovers */

export function Popover({ open, onClose, align = "right", children, className = "" }: {
  open: boolean; onClose: () => void; align?: "left" | "right" | "up";
  children: ReactNode; className?: string;
}) {
  const ref = useDismissOnOutside<HTMLDivElement>(open, onClose);
  if (!open) return null;
  return (
    <div ref={ref} className={`popover ${align} ${className}`} role="menu">
      {children}
    </div>
  );
}

/**
 * Definition tooltip. Used for numbers a board might challenge — a health score
 * nobody can define is a number nobody should trust.
 */
export function Definition({ children, tip, align = "left" }:
  { children: ReactNode; tip: ReactNode; align?: "left" | "right" }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="pop-anchor" style={{ display: "inline-flex" }}>
      <button type="button" className="def" aria-describedby={open ? id : undefined}
        onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen((v) => !v); }}>
        {children}<IconInfo size={11} style={{ opacity: .55 }} />
      </button>
      {open && (
        <span role="tooltip" id={id} className="tip"
          style={{ top: "calc(100% + 6px)", [align]: 0 } as React.CSSProperties}>
          {tip}
        </span>
      )}
    </span>
  );
}

/* =================================================================== tables */

export type SortDir = "asc" | "desc";
export function SortableTh<K extends string>({ id, sort, onSort, children, className = "", align }: {
  id: K; sort: { key: K; dir: SortDir } | null; onSort: (k: K) => void;
  children: ReactNode; className?: string; align?: "right";
}) {
  const active = sort?.key === id;
  return (
    <th className={`sortable ${className}`} onClick={() => onSort(id)}
      aria-sort={active ? (sort!.dir === "asc" ? "ascending" : "descending") : undefined}
      style={align === "right" ? { textAlign: "right" } : undefined}>
      <span role="button" tabIndex={0} style={{ display: "inline-flex", alignItems: "center" }}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSort(id); } }}>
        {children}
        <span className="sort-ind" aria-hidden="true">
          {active ? (sort!.dir === "asc" ? "↑" : "↓") : "↕"}
        </span>
      </span>
    </th>
  );
}

/* ==================================================================== notes */

export function Note({ tone = "mute", icon, children }:
  { tone?: "crit" | "warn" | "good" | "info" | "mute"; icon?: ReactNode; children: ReactNode }) {
  const fallback = tone === "crit" ? <IconXCircle size={14} />
    : tone === "warn" ? <IconAlert size={14} />
    : tone === "good" ? <IconCheckCircle size={14} />
    : <IconInfo size={14} />;
  return (
    <div className={`note note-${tone}`} role={tone === "crit" ? "alert" : undefined}>
      <span className="note-ico">{icon ?? fallback}</span>
      <div className="note-body">{children}</div>
    </div>
  );
}

/** Collapsible section — the core of progressive disclosure in the sheet. */
export function Disclosure({ title, meta, defaultOpen = false, children }: {
  title: ReactNode; meta?: ReactNode; defaultOpen?: boolean; children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <div className="panel">
      <button type="button" className="panel-head" aria-expanded={open} aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        style={{ width: "100%", background: "transparent", border: 0, cursor: "pointer",
                 borderBottom: open ? "1px solid var(--rule)" : "0", textAlign: "left" }}>
        <span className="row" style={{ gap: 8 }}>
          <IconChevronDown size={13}
            style={{ transform: open ? "none" : "rotate(-90deg)", transition: "transform .14s",
                     color: "var(--ink-3)" }} />
          <h3>{title}</h3>
        </span>
        {meta}
      </button>
      {open && <div className="panel-body" id={id}>{children}</div>}
    </div>
  );
}

/* =============================================================== priority */

/**
 * Triage priority. Rendered as a band + numeric score so it sorts meaningfully
 * and so nobody has to trust a colour: the number and the reason are both there.
 */
export function PriorityBadge({ p, compact = false }:
  { p: { score: number; band: PriorityBand; why: string }; compact?: boolean }) {
  if (p.score === 0) return <span className="faint" aria-label="No priority — closed">—</span>;
  return (
    <span className="prio" data-band={p.band} title={`${PRIORITY_LABEL[p.band]} — ${p.why}`}>
      <span className="prio-dot" aria-hidden="true" />
      {!compact && <span className="prio-label">{PRIORITY_LABEL[p.band]}</span>}
      <span className="prio-score num" aria-hidden="true">{p.score.toFixed(1)}</span>
      <span className="sr-only">
        {PRIORITY_LABEL[p.band]} priority, score {p.score.toFixed(1)}. {p.why}
      </span>
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>;
}

/* ============================================================ announcements */

/**
 * Politely announces transient state that is otherwise only visual — selection
 * counts, bulk progress, filter results. Sighted users see the bulk bar appear;
 * without this, screen-reader users get nothing.
 */
export function useAnnounce() {
  const [message, setMessage] = useState("");
  const announce = useCallback((m: string) => {
    // Re-announce identical strings by clearing first.
    setMessage("");
    window.setTimeout(() => setMessage(m), 30);
  }, []);
  const node = (
    <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">{message}</div>
  );
  return { announce, node };
}

/* ================================================================= re-export */
export { fmtDate, fmtDateTime, fmtDateShort, relativeDue, relativeTime } from "@/lib/format";

/** Small helper so pages can render a "N of M" line consistently. */
export function ResultCount({ shown, total, noun = "obligation" }:
  { shown: number; total: number; noun?: string }) {
  return (
    <span className="muted micro num">
      {shown === total ? `${total} ${noun}${total === 1 ? "" : "s"}`
        : `${shown} of ${total} ${noun}${total === 1 ? "" : "s"}`}
    </span>
  );
}

export function useDebounced<T>(value: T, ms = 200): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Stable callback identity for handlers passed into effects. */
export function useEvent<A extends unknown[], R>(fn: (...a: A) => R) {
  const ref = useRef(fn);
  useLayoutEffect(() => { ref.current = fn; });
  return useCallback((...a: A) => ref.current(...a), []);
}
