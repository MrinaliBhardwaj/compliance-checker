"use client";
// Authenticated app shell: route guard + role-aware nav + entity selector +
// notifications bell + user menu. Wrap every authenticated page in <Shell>.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { listNotifications, type Capability } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Loading } from "@/components/ui";

const NAV: { href: string; label: string; cap?: Capability; roles?: string[] }[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/obligations", label: "Obligations" },
  { href: "/legal-updates", label: "Legal updates" },
  { href: "/reports", label: "Reports", cap: "export_reports" },
  { href: "/audit", label: "Audit trail", cap: "view_audit" },
  { href: "/team", label: "Team", roles: ["compliance_admin", "head"] },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const { principal, loading, entityId, setEntityId, logout, can } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !principal) router.replace("/");
  }, [loading, principal, router]);

  const unread = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => listNotifications(true),
    enabled: !!principal,
    refetchInterval: 60_000,
  });

  if (loading) return <Loading label="Loading your workspace…" />;
  if (!principal) return null; // redirecting

  return (
    <div>
      <nav className="nav">
        <div className="nav-inner">
          <Link href="/dashboard" className="brand" style={{ color: "var(--ink)" }}>Regis</Link>
          {NAV.filter((n) => (!n.cap || can(n.cap)) && (!n.roles || n.roles.includes(principal.role)))
            .map((n) => (
              <Link key={n.href} href={n.href}
                className={`link ${pathname.startsWith(n.href) ? "active" : ""}`}>{n.label}</Link>
            ))}
          <span className="spacer" />
          {principal.entities.length > 1 && (
            <select className="input" style={{ width: "auto", padding: "5px 8px" }}
              value={entityId ?? ""} onChange={(e) => setEntityId(e.target.value)}>
              {principal.entities.map((en) => (
                <option key={en.id} value={en.id}>{en.legal_name}</option>
              ))}
            </select>
          )}
          <Link href="/notifications" className="link" title="Notifications">
            🔔 {unread.data?.length ? <b style={{ color: "var(--warn)" }}>{unread.data.length}</b> : null}
          </Link>
          <span className="muted" style={{ fontSize: 12 }}>
            {principal.email} · {ROLE_LABEL[principal.role]}
          </span>
          <button className="btn sm ghost" onClick={logout}>Log out</button>
        </div>
      </nav>
      <div className="container">{children}</div>
    </div>
  );
}

const ROLE_LABEL: Record<string, string> = {
  compliance_admin: "Admin", head: "Head/CFO", preparer: "Preparer",
};
