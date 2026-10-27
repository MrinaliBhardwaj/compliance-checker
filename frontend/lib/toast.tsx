"use client";
// Toasts for action feedback.
//
// Deliberate differences from the old version:
//  • Errors do NOT auto-dismiss. A failure message that disappears after 4s is
//    a message the user cannot act on or quote in a support ticket.
//  • Announced via aria-live so screen-reader users learn that an action landed.
//  • Supports an action slot, which is how undo is offered after bulk changes.
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { IconAlert, IconCheckCircle, IconInfo, IconX } from "@/components/icons";

export type ToastKind = "ok" | "err" | "info";

export interface ToastInput {
  title: string;
  description?: string;
  kind?: ToastKind;
  /** Label + handler for a single inline action, e.g. "Undo". */
  action?: { label: string; onClick: () => void };
  /** ms; 0 keeps it until dismissed. Errors default to 0. */
  duration?: number;
}

interface Toast extends ToastInput { id: number; kind: ToastKind; }

interface ToastApi {
  push: (t: ToastInput) => number;
  dismiss: (id: number) => void;
}

const Ctx = createContext<ToastApi>({ push: () => 0, dismiss: () => {} });

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const push = useCallback((t: ToastInput) => {
    const id = ++seq.current;
    const kind = t.kind ?? "info";
    const duration = t.duration ?? (kind === "err" ? 0 : t.action ? 8000 : 4500);
    setToasts((prev) => [...prev.slice(-3), { ...t, id, kind }]);
    if (duration > 0) setTimeout(() => dismiss(id), duration);
    return id;
  }, [dismiss]);

  const api = useMemo(() => ({ push, dismiss }), [push, dismiss]);

  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="toast-wrap" role="region" aria-label="Notifications">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}
            role={t.kind === "err" ? "alert" : "status"}
            aria-live={t.kind === "err" ? "assertive" : "polite"}>
            <span className="t-ico">
              {t.kind === "ok" ? <IconCheckCircle size={15} />
                : t.kind === "err" ? <IconAlert size={15} />
                : <IconInfo size={15} />}
            </span>
            <div className="t-body">
              <div className="t-title">{t.title}</div>
              {t.description && <div className="t-desc">{t.description}</div>}
            </div>
            {t.action && (
              <button className="btn sm"
                onClick={() => { t.action!.onClick(); dismiss(t.id); }}>
                {t.action.label}
              </button>
            )}
            <button className="btn icon ghost" onClick={() => dismiss(t.id)} aria-label="Dismiss">
              <IconX size={13} />
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

/**
 * `toast.ok(...)` / `toast.err(...)` / `toast.info(...)` read better at call
 * sites than a kind argument, and make it hard to accidentally file an error
 * as a success.
 */
export function useToast() {
  const { push, dismiss } = useContext(Ctx);
  return useMemo(() => ({
    ok: (title: string, description?: string, action?: ToastInput["action"]) =>
      push({ title, description, kind: "ok", action }),
    err: (title: string, description?: string) => push({ title, description, kind: "err" }),
    info: (title: string, description?: string) => push({ title, description, kind: "info" }),
    push, dismiss,
  }), [push, dismiss]);
}

/** Normalizes any thrown value into a toast-ready message. */
export function errMessage(e: unknown, fallback = "Something went wrong"): string {
  if (e instanceof Error && e.message) return e.message;
  if (typeof e === "string" && e) return e;
  return fallback;
}
