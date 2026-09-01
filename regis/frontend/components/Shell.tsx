"use client";
// Authenticated app shell.
//
// Changed from the old top-nav strip:
//  • Sidebar with grouped sections, so the IA is visible rather than a flat row.
//  • Live counts on Obligations / Notifications: the number of things demanding
//    attention is nav-level information, not something to discover on a page.
//  • Entity switcher is a labelled menu, not a bare <select> wedged into a bar —
//    filing for the wrong legal entity is a serious error, so it stays explicit.
//  • Skip link, landmarks, Cmd-K, theme control.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { getDashboard, listNotifications, type Capability } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { ROLE_LABEL } from "@/lib/format";
import CommandPalette from "@/components/CommandPalette";
import {
  IconBell, IconBuilding, IconChart, IconChevronDown, IconFile, IconGavel,
  IconHome, IconList, IconLogout, IconMoon, IconSearch, IconShield, IconSun,
  IconUsers,
} from "@/components/icons";
import { Avatar, Popover, Spinner } from "@/components/ui";

type NavEntry = {
  href: string; label: string; icon: ReactNode;
  cap?: Capability; roles?: string[]; countKey?: "overdue" | "unread";
};

const NAV: { group: string; items: NavEntry[] }[] = [
  {
    group: "Compliance",
    items: [
      { href: "/dashboard", label: "Today", icon: <IconHome size={14} /> },
      { href: "/obligations", label: "Obligations", icon: <IconList size={14} />, countKey: "overdue" },
      { href: "/evidence", label: "Evidence", icon: <IconFile size={14} /> },
      { href: "/legal-updates", label: "Legal updates", icon: <IconGavel size={14} /> },
    ],
  },
  {
    group: "Assurance",
    items: [
      { href: "/reports", label: "Reports", icon: <IconChart size={14} />, cap: "export_reports" },
      { href: "/audit", label: "Audit trail", icon: <IconShield size={14} />, cap: "view_audit" },
    ],
  },
  {
    group: "Workspace",
    items: [
      { href: "/notifications", label: "Notifications", icon: <IconBell size={14} />, countKey: "unread" },
      { href: "/team", label: "Team", icon: <IconUsers size={14} />, roles: ["compliance_admin", "head"] },
    ],
  },
];

export default function Shell({ children }: { children: ReactNode }) {
  const { principal, loading, logout } = useAuth();
  const router = useRouter();
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    if (!loading && !principal) router.replace("/");
  }, [loading, principal, router]);

  // Cmd/Ctrl-K anywhere in the app.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (loading) {
    return (
      <div style={{ display: "grid", placeItems: "center", minHeight: "100dvh" }}>
        <div className="row muted" style={{ gap: 10 }}>
          <Spinner /> Loading your workspace…
        </div>
      </div>
    );
  }
  if (!principal) return null; // redirecting

  return (
    <>
      <a className="skip-link" href="#main">Skip to main content</a>
      <div className="app">
        <Sidebar onLogout={logout} />
        <div className="page">
          <TopBar onOpenPalette={() => setPaletteOpen(true)} />
          <main id="main" className="page-body" tabIndex={-1}>{children}</main>
        </div>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </>
  );
}

/* ================================================================= sidebar */

function Sidebar({ onLogout }: { onLogout: () => void }) {
  const { principal, can } = useAuth();
  const pathname = usePathname();

  const dash = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard, staleTime: 30_000 });
  const unread = useQuery({
    queryKey: ["notifications", "unread"], queryFn: () => listNotifications(true),
    refetchInterval: 60_000,
  });

  const counts = {
    overdue: dash.data?.tiles.overdue ?? 0,
    unread: unread.data?.length ?? 0,
  };

  return (
    <nav className="sidebar" aria-label="Primary">
      <div className="sidebar-head">
        <Link href="/dashboard" className="brand">
          <span className="brand-mark" aria-hidden="true">R</span>
          Regis
        </Link>
        <div className="faint micro" style={{ marginTop: 6, paddingLeft: 1 }}>
          {principal?.organization_name ?? "Workspace"}
        </div>
      </div>

      <div className="sidebar-scroll">
        {NAV.map((g) => {
          const items = g.items.filter((n) =>
            (!n.cap || can(n.cap)) && (!n.roles || n.roles.includes(principal!.role)));
          if (items.length === 0) return null;
          return (
            <div className="nav-group" key={g.group}>
              <span className="eyebrow">{g.group}</span>
              {items.map((n) => {
                const current = pathname === n.href || pathname.startsWith(`${n.href}/`);
                const count = n.countKey ? counts[n.countKey] : 0;
                return (
                  <Link key={n.href} href={n.href} className="nav-item"
                    aria-current={current ? "page" : undefined}>
                    <span className="ico">{n.icon}</span>
                    <span className="truncate">{n.label}</span>
                    {count > 0 && (
                      <span className={`count ${n.countKey === "overdue" ? "crit" : "warn"}`}>
                        {count > 99 ? "99+" : count}
                        <span className="sr-only">
                          {n.countKey === "overdue" ? " overdue" : " unread"}
                        </span>
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </div>

      <div className="sidebar-foot">
        <EntitySwitcher />
        <UserMenu onLogout={onLogout} />
      </div>
    </nav>
  );
}

/**
 * Entity switcher. Filing under the wrong legal entity is an expensive mistake,
 * so the active entity is always named in full — never collapsed to an initial.
 */
function EntitySwitcher() {
  const { principal, entityId, setEntityId } = useAuth();
  const [open, setOpen] = useState(false);
  const entities = principal?.entities ?? [];
  const activeName = entities.find((e) => e.id === entityId)?.legal_name
    ?? entities[0]?.legal_name ?? "—";

  if (entities.length <= 1) {
    return (
      <div className="row" style={{ padding: "6px 8px", gap: 8, color: "var(--ink-2)" }}>
        <IconBuilding size={14} style={{ flex: "none", opacity: .7 }} />
        <span className="truncate micro" title={activeName}>{activeName}</span>
      </div>
    );
  }

  return (
    <div className="pop-anchor" style={{ marginBottom: 4 }}>
      <button className="btn ghost" style={{ width: "100%", justifyContent: "flex-start", gap: 8 }}
        onClick={() => setOpen((v) => !v)} aria-haspopup="menu" aria-expanded={open}>
        <IconBuilding size={14} style={{ flex: "none", opacity: .7 }} />
        <span className="truncate" style={{ flex: 1, textAlign: "left" }}>{activeName}</span>
        <IconChevronDown size={12} />
      </button>
      <Popover open={open} onClose={() => setOpen(false)} align="up"
        className="" >
        <div className="eyebrow" style={{ padding: "9px 10px 4px" }}>Legal entity</div>
        <div style={{ padding: 4 }}>
          {entities.map((e) => (
            <button key={e.id} className="menu-item" role="menuitemradio"
              aria-checked={e.id === entityId}
              onClick={() => { setEntityId(e.id); setOpen(false); }}>
              <span style={{ width: 14, flex: "none", color: "var(--accent)" }}>
                {e.id === entityId ? "✓" : ""}
              </span>
              <span className="truncate">{e.legal_name}</span>
            </button>
          ))}
        </div>
        <div className="micro faint" style={{ padding: "6px 10px 9px", borderTop: "1px solid var(--rule)" }}>
          Obligations, evidence and reports are scoped to the selected entity.
        </div>
      </Popover>
    </div>
  );
}

function UserMenu({ onLogout }: { onLogout: () => void }) {
  const { principal } = useAuth();
  const { pref, setPref } = useTheme();
  const [open, setOpen] = useState(false);
  if (!principal) return null;
  const name = principal.email ?? "You";

  return (
    <div className="pop-anchor">
      <button className="btn ghost" style={{ width: "100%", justifyContent: "flex-start", gap: 8, padding: "6px 8px" }}
        onClick={() => setOpen((v) => !v)} aria-haspopup="menu" aria-expanded={open}>
        <Avatar label={name} size={20} />
        <span style={{ flex: 1, minWidth: 0, textAlign: "left" }}>
          <span className="truncate" style={{ display: "block", fontSize: 12 }}>{name}</span>
          <span className="faint" style={{ fontSize: 10.5 }}>{ROLE_LABEL[principal.role]}</span>
        </span>
        <IconChevronDown size={12} />
      </button>
      <Popover open={open} onClose={() => setOpen(false)} align="up">
        <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--rule)" }}>
          <div className="truncate" style={{ fontWeight: 600 }}>{name}</div>
          <div className="faint micro">{ROLE_LABEL[principal.role]}</div>
        </div>
        <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--rule)" }}>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Appearance</div>
          <div className="segmented" role="group" aria-label="Theme">
            {(["light", "dark", "system"] as const).map((t) => (
              <button key={t} aria-pressed={pref === t} onClick={() => setPref(t)}
                style={{ textTransform: "capitalize" }}>
                {t === "light" ? <IconSun size={12} /> : t === "dark" ? <IconMoon size={12} /> : null}
                {t}
              </button>
            ))}
          </div>
        </div>
        <div style={{ padding: 4 }}>
          <button className="menu-item danger" onClick={onLogout} role="menuitem">
            <IconLogout size={14} /> Log out
          </button>
        </div>
      </Popover>
    </div>
  );
}

/* ================================================================== topbar */

function TopBar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const { principal } = useAuth();
  const unread = useQuery({
    queryKey: ["notifications", "unread"], queryFn: () => listNotifications(true),
    refetchInterval: 60_000,
  });
  const n = unread.data?.length ?? 0;

  return (
    <div className="topbar">
      <button className="search-trigger" onClick={onOpenPalette}
        aria-label="Search obligations and commands">
        <IconSearch size={14} />
        <span className="spacer" style={{ textAlign: "left" }}>Search obligations…</span>
        <span className="kbd">⌘K</span>
      </button>
      <span className="spacer" />
      {principal?.role === "preparer" && (
        <span className="badge t-neutral" title="You see only obligations assigned to you.">
          Scoped to your assignments
        </span>
      )}
      <Link href="/notifications" className="btn ghost icon" aria-label={
        n > 0 ? `Notifications, ${n} unread` : "Notifications"
      } style={{ position: "relative" }}>
        <IconBell size={15} />
        {n > 0 && (
          <span aria-hidden="true" style={{
            position: "absolute", top: 3, right: 3, width: 6, height: 6, borderRadius: "50%",
            background: "var(--crit-solid)", border: "1.5px solid var(--paper)",
          }} />
        )}
      </Link>
    </div>
  );
}
