"use client";
// Command palette (Cmd/Ctrl-K).
//
// The old app had no global search at all: finding one obligation among 367
// meant navigating to the tracker and typing into a title filter. This searches
// obligations and navigates anywhere, from any screen, without touching the mouse.
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { getInstances, type Capability, type Instance } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { relativeDue, statusLabel } from "@/lib/format";
import {
  IconBell, IconChart, IconFile, IconGavel, IconHome, IconList, IconMoon,
  IconSearch, IconShield, IconSun, IconUsers,
} from "@/components/icons";
import { StatusBadge } from "@/components/ui";

interface Cmd {
  id: string;
  label: string;
  hint?: string;
  section: string;
  icon: React.ReactNode;
  cap?: Capability;
  roles?: string[];
  run: () => void;
}

export default function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const { principal, can } = useAuth();
  const { resolved, setPref } = useTheme();
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Only fetch the corpus while the palette is actually open.
  const instances = useQuery({
    queryKey: ["tracker"], queryFn: () => getInstances({}), enabled: open,
    staleTime: 30_000,
  });

  useEffect(() => { if (open) { setQ(""); setActive(0); } }, [open]);
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => inputRef.current?.focus(), 10);
    return () => clearTimeout(t);
  }, [open]);

  const go = (href: string) => { router.push(href); onClose(); };

  const commands: Cmd[] = useMemo(() => ([
    { id: "n-today", section: "Go to", label: "Today", hint: "Overview and priority queue",
      icon: <IconHome size={14} />, run: () => go("/dashboard") },
    { id: "n-obl", section: "Go to", label: "Obligations", hint: "Full compliance calendar",
      icon: <IconList size={14} />, run: () => go("/obligations") },
    { id: "n-ev", section: "Go to", label: "Evidence", hint: "Document repository",
      icon: <IconFile size={14} />, run: () => go("/evidence") },
    { id: "n-legal", section: "Go to", label: "Legal updates",
      icon: <IconGavel size={14} />, run: () => go("/legal-updates") },
    { id: "n-rep", section: "Go to", label: "Reports", cap: "export_reports",
      icon: <IconChart size={14} />, run: () => go("/reports") },
    { id: "n-audit", section: "Go to", label: "Audit trail", cap: "view_audit",
      icon: <IconShield size={14} />, run: () => go("/audit") },
    { id: "n-team", section: "Go to", label: "Team", roles: ["compliance_admin", "head"],
      icon: <IconUsers size={14} />, run: () => go("/team") },
    { id: "n-notif", section: "Go to", label: "Notifications",
      icon: <IconBell size={14} />, run: () => go("/notifications") },

    { id: "f-overdue", section: "Filter obligations", label: "Show overdue",
      hint: "Past their statutory due date", icon: <IconList size={14} />,
      run: () => go("/obligations?status=overdue") },
    { id: "f-review", section: "Filter obligations", label: "Show awaiting review",
      hint: "Submitted, waiting on a checker", icon: <IconList size={14} />,
      run: () => go("/obligations?status=ready_for_review") },
    { id: "f-week", section: "Filter obligations", label: "Show due in the next 7 days",
      icon: <IconList size={14} />, run: () => go("/obligations?window=week") },
    { id: "f-mine", section: "Filter obligations", label: "Show only my obligations",
      icon: <IconList size={14} />, run: () => go("/obligations?mine=1") },

    { id: "t-theme", section: "Preferences",
      label: resolved === "dark" ? "Switch to light theme" : "Switch to dark theme",
      icon: resolved === "dark" ? <IconSun size={14} /> : <IconMoon size={14} />,
      run: () => { setPref(resolved === "dark" ? "light" : "dark"); onClose(); } },
  ] as Cmd[]).filter((c) => (!c.cap || can(c.cap)) && (!c.roles || c.roles.includes(principal?.role ?? ""))),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [principal?.role, resolved]);

  const needle = q.trim().toLowerCase();

  const matchedCommands = useMemo(
    () => commands.filter((c) =>
      !needle || c.label.toLowerCase().includes(needle) || c.hint?.toLowerCase().includes(needle)),
    [commands, needle]);

  const matchedInstances: Instance[] = useMemo(() => {
    if (needle.length < 2) return [];
    return (instances.data ?? []).filter((i) =>
      i.title.toLowerCase().includes(needle)
      || (i.form_reference ?? "").toLowerCase().includes(needle)
      || i.category.toLowerCase().includes(needle)
      || i.period_label.toLowerCase().includes(needle),
    ).slice(0, 7);
  }, [instances.data, needle]);

  type Row = { key: string; kind: "cmd"; cmd: Cmd } | { key: string; kind: "inst"; inst: Instance };
  const rows: Row[] = useMemo(() => [
    ...matchedCommands.map((c) => ({ key: c.id, kind: "cmd" as const, cmd: c })),
    ...matchedInstances.map((i) => ({ key: i.id, kind: "inst" as const, inst: i })),
  ], [matchedCommands, matchedInstances]);

  useEffect(() => { setActive(0); }, [needle]);

  const runRow = (r: Row) => {
    if (r.kind === "cmd") r.cmd.run();
    else go(`/obligations?open=${r.inst.id}`);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, rows.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); if (rows[active]) runRow(rows[active]); }
    else if (e.key === "Escape") { e.preventDefault(); onClose(); }
  };

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>('[data-active="true"]')
      ?.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!open) return null;

  let lastSection = "";
  return (
    <div className="modal-wrap" style={{ alignItems: "start" }}>
      <div className="scrim" onClick={onClose} aria-hidden="true" />
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette">
        <div className="row" style={{ padding: "0 14px", borderBottom: "1px solid var(--rule)" }}>
          <IconSearch size={15} style={{ color: "var(--ink-3)", flex: "none" }} />
          <input ref={inputRef} className="palette-input" style={{ borderBottom: 0, padding: "13px 2px" }}
            placeholder="Search obligations, or jump to a page…" value={q}
            onChange={(e) => setQ(e.target.value)} onKeyDown={onKeyDown}
            role="combobox" aria-expanded aria-controls="palette-list" aria-autocomplete="list" />
          <span className="kbd">Esc</span>
        </div>

        <div className="palette-list" id="palette-list" role="listbox" ref={listRef}>
          {rows.length === 0 && (
            <div className="muted" style={{ padding: "22px 12px", textAlign: "center", fontSize: 12.5 }}>
              {instances.isLoading ? "Searching…" : `No matches for “${q}”`}
            </div>
          )}
          {rows.map((r, i) => {
            const section = r.kind === "cmd" ? r.cmd.section : "Obligations";
            const header = section !== lastSection ? section : null;
            lastSection = section;
            return (
              <div key={r.key}>
                {header && <div className="palette-sec eyebrow">{header}</div>}
                <button className="palette-item" role="option" aria-selected={i === active}
                  data-active={i === active} onMouseEnter={() => setActive(i)}
                  onClick={() => runRow(r)}>
                  {r.kind === "cmd" ? (
                    <>
                      <span className="ico">{r.cmd.icon}</span>
                      <span style={{ minWidth: 0, flex: 1 }}>
                        <span>{r.cmd.label}</span>
                        {r.cmd.hint && <span className="faint micro" style={{ marginLeft: 8 }}>{r.cmd.hint}</span>}
                      </span>
                    </>
                  ) : (
                    <>
                      <span className="ico"><IconList size={14} /></span>
                      <span style={{ minWidth: 0, flex: 1 }}>
                        <span className="truncate" style={{ display: "block" }}>{r.inst.title}</span>
                        <span className="faint micro">
                          {r.inst.period_label}
                          {r.inst.form_reference ? ` · ${r.inst.form_reference}` : ""}
                          {" · "}{relativeDue(r.inst.due_date).text}
                        </span>
                      </span>
                      <span aria-label={statusLabel(r.inst.status)}>
                        <StatusBadge status={r.inst.status} />
                      </span>
                    </>
                  )}
                </button>
              </div>
            );
          })}
        </div>

        <div className="row" style={{
          padding: "7px 12px", borderTop: "1px solid var(--rule)", gap: 12,
          background: "var(--surface-2)", color: "var(--ink-3)", fontSize: 11,
        }}>
          <span className="row" style={{ gap: 4 }}><span className="kbd">↑</span><span className="kbd">↓</span> navigate</span>
          <span className="row" style={{ gap: 4 }}><span className="kbd">↵</span> open</span>
          <span className="spacer" />
          <span>{rows.length} result{rows.length === 1 ? "" : "s"}</span>
        </div>
      </div>
    </div>
  );
}
