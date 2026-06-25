"use client";
// Notifications inbox: reminders, escalations, review requests, assignments.
// Mark individual / all read. Type + kind drive the icon and tone.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listNotifications, markNotificationRead, type NotificationItem } from "@/lib/api";
import { useToast } from "@/lib/toast";
import Shell from "@/components/Shell";
import { Empty, ErrorState, Loading, fmtDate } from "@/components/ui";

export default function NotificationsPage() {
  return <Shell><Inbox /></Shell>;
}

function kindOf(n: NotificationItem): { icon: string; label: string; tone: string } {
  const kind = String(n.payload?.kind ?? "");
  if (n.type === "escalation") return { icon: "⚠", label: "Escalation", tone: "var(--risk)" };
  if (kind === "review_requested") return { icon: "📝", label: "Review requested", tone: "var(--warn)" };
  if (kind === "rejected") return { icon: "↩", label: "Sent back", tone: "var(--warn)" };
  if (n.type === "assignment") return { icon: "👤", label: "Assignment", tone: "var(--info)" };
  return { icon: "🔔", label: "Reminder", tone: "var(--muted)" };
}

function Inbox() {
  const qc = useQueryClient();
  const toast = useToast();
  const list = useQuery({ queryKey: ["notifications", "all"], queryFn: () => listNotifications(false) });

  const read = useMutation({
    mutationFn: markNotificationRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (e) => toast(e instanceof Error ? e.message : "Failed", "err"),
  });

  const markAll = async () => {
    const unread = (list.data ?? []).filter((n) => !n.read_at);
    await Promise.all(unread.map((n) => markNotificationRead(n.id)));
    qc.invalidateQueries({ queryKey: ["notifications"] });
    toast(`Marked ${unread.length} read`, "ok");
  };

  return (
    <div className="stack">
      <div className="between">
        <h1>Notifications</h1>
        <button className="btn" onClick={markAll}
          disabled={!list.data?.some((n) => !n.read_at)}>Mark all read</button>
      </div>

      {list.isLoading && <Loading />}
      {list.isError && <ErrorState error={list.error} onRetry={list.refetch} />}
      {list.data && (list.data.length === 0
        ? <Empty title="No notifications yet" hint="Reminders and escalations will appear here." />
        : (
          <div className="stack" style={{ gap: 8 }}>
            {list.data.map((n) => {
              const k = kindOf(n);
              return (
                <div key={n.id} className="card between"
                  style={{ borderLeft: `3px solid ${k.tone}`, opacity: n.read_at ? 0.6 : 1 }}>
                  <div>
                    <div className="row" style={{ gap: 8 }}>
                      <span>{k.icon}</span>
                      <b>{k.label}</b>
                      <span className="chip">{n.channel}</span>
                      {!n.read_at && <span className="badge in_progress"><span className="dot" />new</span>}
                    </div>
                    <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                      {String(n.payload?.instance_id ? `Obligation ${String(n.payload.instance_id).slice(0, 8)}…` : "")}
                      {" · "}{fmtDate(n.created_at)}
                    </div>
                  </div>
                  {!n.read_at && (
                    <button className="btn sm ghost" disabled={read.isPending}
                      onClick={() => read.mutate(n.id)}>Mark read</button>
                  )}
                </div>
              );
            })}
          </div>
        ))}
    </div>
  );
}
