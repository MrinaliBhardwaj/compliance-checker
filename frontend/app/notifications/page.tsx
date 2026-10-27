"use client";
// Notification inbox — reminders, escalations, review requests, assignments.
//
// Rework notes:
//  • Notifications are now actionable. Every one that references an obligation
//    links straight into it; previously the payload's instance_id was rendered
//    as a truncated UUID, which is information the user cannot use.
//  • Unread is a filter, not just an opacity change, and "mark all read" reports
//    partial failure instead of assuming success.
//  • Escalations are separated visually — an escalation and a routine reminder
//    are not the same class of event.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { listNotifications, markNotificationRead, type NotificationItem } from "@/lib/api";
import { errMessage, useToast } from "@/lib/toast";
import { fmtDateTime, pluralize, relativeTime } from "@/lib/format";
import Shell from "@/components/Shell";
import {
  IconAlert, IconArrowRight, IconBell, IconCheck, IconCheckCircle, IconInbox,
  IconUndo, IconUser,
} from "@/components/icons";
import {
  Badge, Empty, ErrorState, Segmented, Skeleton, Spinner,
} from "@/components/ui";
import type { Tone } from "@/lib/format";

export default function NotificationsPage() {
  return <Shell><Inbox /></Shell>;
}

interface Kind { icon: React.ReactNode; label: string; tone: Tone; blurb: string; }

function kindOf(n: NotificationItem): Kind {
  const kind = String(n.payload?.kind ?? "");
  if (n.type === "escalation") {
    return {
      icon: <IconAlert size={14} />, label: "Escalation", tone: "crit",
      blurb: "An overdue obligation has escalated. It needs attention now.",
    };
  }
  if (kind === "review_requested") {
    return {
      icon: <IconCheckCircle size={14} />, label: "Review requested", tone: "warn",
      blurb: "A preparer submitted a filing and is waiting on your approval.",
    };
  }
  if (kind === "rejected") {
    return {
      icon: <IconUndo size={14} />, label: "Sent back", tone: "warn",
      blurb: "A checker returned this filing with changes requested.",
    };
  }
  if (n.type === "assignment") {
    return {
      icon: <IconUser size={14} />, label: "Assignment", tone: "info",
      blurb: "An obligation was assigned to you.",
    };
  }
  return {
    icon: <IconBell size={14} />, label: "Reminder", tone: "neutral",
    blurb: "A due date is approaching.",
  };
}

type Filter = "unread" | "all";

function Inbox() {
  const qc = useQueryClient();
  const toast = useToast();
  const [filter, setFilter] = useState<Filter>("unread");
  const [markingAll, setMarkingAll] = useState(false);

  const list = useQuery({
    queryKey: ["notifications", "all"], queryFn: () => listNotifications(false),
  });

  const rows = list.data ?? [];
  const unread = useMemo(() => rows.filter((n) => !n.read_at), [rows]);
  const shown = filter === "unread" ? unread : rows;

  const read = useMutation({
    mutationFn: markNotificationRead,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
    onError: (e) => toast.err("Couldn’t mark as read", errMessage(e)),
  });

  const markAll = async () => {
    if (unread.length === 0) return;
    setMarkingAll(true);
    const results = await Promise.allSettled(unread.map((n) => markNotificationRead(n.id)));
    const failed = results.filter((r) => r.status === "rejected").length;
    qc.invalidateQueries({ queryKey: ["notifications"] });
    setMarkingAll(false);
    if (failed === 0) toast.ok(`${pluralize(unread.length, "notification")} marked read`);
    else toast.err(`${unread.length - failed} marked read, ${failed} failed`,
      "Try again — the ones that failed are still unread.");
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Notifications</h1>
          <p className="lede">
            Reminders, escalations, review requests and assignments — risk-weighted, so
            the loudest thing here is genuinely the most urgent.
          </p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <Segmented label="Filter notifications" value={filter} onChange={setFilter}
            options={[
              { value: "unread", label: "Unread", count: unread.length },
              { value: "all", label: "All", count: rows.length },
            ]} />
          <button className="btn" onClick={markAll} disabled={unread.length === 0 || markingAll}>
            {markingAll ? <Spinner /> : <IconCheck size={13} />} Mark all read
          </button>
        </div>
      </div>

      {list.isLoading && (
        <div className="stack-sm">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="panel"><div className="panel-body">
              <Skeleton w={180} h={12} />
              <div style={{ marginTop: 8 }}><Skeleton w="60%" h={10} /></div>
            </div></div>
          ))}
        </div>
      )}
      {list.isError && <ErrorState error={list.error} onRetry={list.refetch} />}

      {list.data && shown.length === 0 && (
        filter === "unread" && rows.length > 0 ? (
          <Empty icon={<IconCheckCircle size={16} />} title="Inbox zero"
            hint="Nothing unread. Everything that needed your attention has been seen."
            action={<button className="btn" onClick={() => setFilter("all")}>
              See all {rows.length}
            </button>} />
        ) : (
          <Empty icon={<IconInbox size={16} />} title="No notifications yet"
            hint="Reminders fire ahead of due dates, and escalations fire when something goes overdue. They’ll appear here." />
        )
      )}

      {list.data && shown.length > 0 && (
        <div className="stack-sm">
          {shown.map((n) => {
            const k = kindOf(n);
            const isUnread = !n.read_at;
            const instanceId = n.payload?.instance_id ? String(n.payload.instance_id) : null;
            const title = typeof n.payload?.title === "string" ? n.payload.title : null;
            const color = k.tone === "crit" ? "var(--crit-solid)"
              : k.tone === "warn" ? "var(--warn)"
              : k.tone === "info" ? "var(--info)" : "var(--rule-2)";

            return (
              <article key={n.id} className="panel"
                style={{ borderLeft: `2px solid ${color}`, opacity: isUnread ? 1 : .72 }}>
                <div className="panel-body">
                  <div className="between" style={{ alignItems: "flex-start", gap: 12 }}>
                    <div style={{ minWidth: 0 }}>
                      <div className="row-wrap" style={{ gap: 7 }}>
                        <span style={{ color, display: "flex" }}>{k.icon}</span>
                        <b style={{ fontSize: 12.5 }}>{k.label}</b>
                        {isUnread && <Badge tone="info" dot>New</Badge>}
                        <span className="tag">{n.channel}</span>
                      </div>

                      <p style={{ fontSize: 12.5, marginTop: 5 }}>
                        {title ?? k.blurb}
                      </p>

                      <div className="micro faint" style={{ marginTop: 4 }}>
                        <time dateTime={n.created_at} title={fmtDateTime(n.created_at)}>
                          {relativeTime(n.created_at)}
                        </time>
                        {n.sent_at && <> · sent {relativeTime(n.sent_at)}</>}
                      </div>
                    </div>

                    <div className="row" style={{ gap: 6, flex: "none" }}>
                      {instanceId && (
                        <Link className="btn sm" href={`/obligations?open=${instanceId}`}>
                          Open obligation <IconArrowRight size={11} />
                        </Link>
                      )}
                      {isUnread && (
                        <button className="btn sm ghost" disabled={read.isPending}
                          onClick={() => read.mutate(n.id)}>Mark read</button>
                      )}
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
