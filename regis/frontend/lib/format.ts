// Formatting + urgency semantics.
//
// The single most expensive thing the old UI asked of users was arithmetic:
// every due date was absolute, so "is this urgent?" meant comparing to today in
// your head, 367 times. Everything here exists to answer that question for them.

export type Status =
  | "pending" | "in_progress" | "ready_for_review" | "completed" | "overdue" | "not_applicable";

export type Tone = "crit" | "warn" | "good" | "info" | "neutral";

/** Local midnight — deadlines are calendar days, never instants. */
export function today(): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

export function parseDay(iso: string | null): Date | null {
  if (!iso) return null;
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

/** Signed whole days from today. Negative = in the past. */
export function daysFromToday(iso: string | null): number | null {
  const d = parseDay(iso);
  if (!d) return null;
  return Math.round((d.getTime() - today().getTime()) / 86_400_000);
}

export function fmtDate(iso: string | null): string {
  const d = parseDay(iso);
  if (!d) return "—";
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export function fmtDateShort(iso: string | null): string {
  const d = parseDay(iso);
  if (!d) return "—";
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleDateString("en-IN",
    sameYear ? { day: "2-digit", month: "short" } : { day: "2-digit", month: "short", year: "2-digit" });
}

export function fmtDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("en-IN", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

/** "12 days late" / "due today" / "in 3 days" — the phrase does the arithmetic. */
export function relativeDue(iso: string | null): { text: string; tone: Tone } {
  const n = daysFromToday(iso);
  if (n === null) return { text: "No due date", tone: "neutral" };
  if (n < 0) {
    const d = Math.abs(n);
    return { text: d === 1 ? "1 day late" : `${d} days late`, tone: "crit" };
  }
  if (n === 0) return { text: "Due today", tone: "crit" };
  if (n === 1) return { text: "Due tomorrow", tone: "warn" };
  if (n <= 7) return { text: `in ${n} days`, tone: "warn" };
  if (n <= 30) return { text: `in ${n} days`, tone: "neutral" };
  const months = Math.round(n / 30);
  return { text: months <= 1 ? "in ~1 month" : `in ~${months} months`, tone: "neutral" };
}

export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const secs = Math.round((Date.now() - then) / 1000);
  if (secs < 60) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return fmtDateShort(iso);
}

/** Row-level urgency: drives the 2px left rail on tracker rows. */
export type Urgency = "overdue" | "soon" | "review" | "none";
export function urgencyOf(status: string, due: string | null): Urgency {
  if (status === "overdue") return "overdue";
  if (status === "ready_for_review") return "review";
  if (status === "completed" || status === "not_applicable") return "none";
  const n = daysFromToday(due);
  if (n !== null && n <= 7) return "soon";
  return "none";
}

export const STATUS_META: Record<string, { label: string; tone: Tone; help: string }> = {
  pending: { label: "Not started", tone: "neutral", help: "No one has begun work on this filing." },
  in_progress: { label: "In progress", tone: "info", help: "A preparer is working on it." },
  ready_for_review: { label: "In review", tone: "warn", help: "Submitted by the maker, waiting on a checker to approve." },
  completed: { label: "Filed", tone: "good", help: "Approved and closed, with evidence on record." },
  overdue: { label: "Overdue", tone: "crit", help: "The statutory due date has passed and the filing is still open." },
  not_applicable: { label: "Not applicable", tone: "neutral", help: "Marked N/A with a recorded reason." },
};

export const statusLabel = (s: string) => STATUS_META[s]?.label ?? s.replace(/_/g, " ");
export const statusTone = (s: string): Tone => STATUS_META[s]?.tone ?? "neutral";

export const ROLE_LABEL: Record<string, string> = {
  compliance_admin: "Compliance admin",
  head: "Head / CFO",
  preparer: "Preparer",
};
export const ROLE_SHORT: Record<string, string> = {
  compliance_admin: "Admin", head: "Head", preparer: "Preparer",
};

/** Human label for the SCREAMING_SNAKE enums the backend speaks. */
export function humanize(v: string): string {
  return v.toLowerCase().replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function initials(nameOrEmail: string): string {
  const s = nameOrEmail.trim();
  if (!s) return "?";
  if (s.includes("@")) return s[0].toUpperCase();
  const parts = s.split(/\s+/);
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

export function pluralize(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
