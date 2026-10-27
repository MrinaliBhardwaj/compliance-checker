"use client";
// Team and roles.
//
// Rework notes:
//  • Member removal no longer runs on prompt() + confirm(). Removing someone
//    reassigns their live obligations — that is a real decision with a real
//    blast radius, so it gets a dialog that names the successor explicitly and
//    says what happens if you don't pick one.
//  • Role changes are confirmed rather than firing on the change event. A
//    mis-click in a <select> silently granting approval rights is exactly the
//    kind of error a maker-checker product should prevent.
//  • The role matrix is shown, not assumed. "What can a Head actually do?" was
//    unanswerable inside the product.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  changeMemberRole, inviteMember, listMembers, removeMember, type Member, type Role,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errMessage, useToast } from "@/lib/toast";
import { ROLE_LABEL } from "@/lib/format";
import Shell from "@/components/Shell";
import { IconCheck, IconUsers, IconX } from "@/components/icons";
import {
  Avatar, Badge, ConfirmDialog, Disclosure, Empty, ErrorState, Field, Modal, Note,
  PermissionDenied, SkeletonRows, Spinner,
} from "@/components/ui";

const ROLES: Role[] = ["preparer", "head", "compliance_admin"];

const ROLE_BLURB: Record<Role, string> = {
  preparer: "Works on obligations assigned to them: starts work, attaches evidence, submits for review. Sees only their own assignments.",
  head: "Oversight and approval. Reviews submissions, exports reports, reads the audit trail — but doesn’t generate calendars or manage the team.",
  compliance_admin: "Full control: generates the calendar, assigns owners, approves, marks N/A, reopens, and manages the team.",
};

const CAPABILITIES: { label: string; roles: Role[] }[] = [
  { label: "Generate the compliance calendar", roles: ["compliance_admin"] },
  { label: "Assign obligation owners", roles: ["compliance_admin"] },
  { label: "Submit for review", roles: ["compliance_admin", "preparer"] },
  { label: "Approve / send back", roles: ["compliance_admin", "head"] },
  { label: "Mark not applicable · Reopen", roles: ["compliance_admin"] },
  { label: "Upload evidence", roles: ["compliance_admin", "head", "preparer"] },
  { label: "Export reports", roles: ["compliance_admin", "head"] },
  { label: "View the audit trail", roles: ["compliance_admin", "head"] },
  { label: "Invite and manage the team", roles: ["compliance_admin"] },
];

export default function TeamPage() {
  return <Shell><Team /></Shell>;
}

function Team() {
  const { role: myRole, principal, can } = useAuth();
  const isAdmin = myRole === "compliance_admin";
  const qc = useQueryClient();
  const toast = useToast();

  const members = useQuery({
    queryKey: ["members"], queryFn: listMembers,
    enabled: myRole === "compliance_admin" || myRole === "head",
  });

  const [inviteOpen, setInviteOpen] = useState(false);
  const [lastInvite, setLastInvite] = useState<{ email: string; url: string } | null>(null);
  const [roleChange, setRoleChange] = useState<{ m: Member; to: Role } | null>(null);
  const [removing, setRemoving] = useState<Member | null>(null);

  const all = members.data ?? [];
  const active = all.filter((m) => m.status === "active");
  const invited = all.filter((m) => m.status === "invited");

  const invite = useMutation({
    mutationFn: (b: { email: string; role: Role; name?: string }) =>
      inviteMember(b.email, b.role, b.name),
    onSuccess: (r) => {
      setLastInvite({ email: r.email, url: `${window.location.origin}${r.invite_url}` });
      setInviteOpen(false);
      toast.ok(`Invited ${r.email}`, `They’ll join as ${ROLE_LABEL[r.role]}.`);
      qc.invalidateQueries({ queryKey: ["members"] });
    },
    onError: (e) => toast.err("Couldn’t send the invite", errMessage(e)),
  });

  const setRole = useMutation({
    mutationFn: ({ id, r }: { id: string; r: Role }) => changeMemberRole(id, r),
    onSuccess: (_d, v) => {
      toast.ok("Role updated", `Now ${ROLE_LABEL[v.r]}.`);
      setRoleChange(null);
      qc.invalidateQueries({ queryKey: ["members"] });
      qc.invalidateQueries({ queryKey: ["assignable"] });
    },
    onError: (e) => toast.err("Couldn’t change the role", errMessage(e)),
  });

  const remove = useMutation({
    mutationFn: ({ id, reassign }: { id: string; reassign?: string }) => removeMember(id, reassign),
    onSuccess: (r) => {
      toast.ok("Member removed",
        r.reassigned_instances
          ? `${r.reassigned_instances} obligation(s) reassigned.`
          : "They had no assigned obligations.");
      setRemoving(null);
      qc.invalidateQueries({ queryKey: ["members"] });
      qc.invalidateQueries({ queryKey: ["tracker"] });
      qc.invalidateQueries({ queryKey: ["assignable"] });
    },
    onError: (e) => toast.err("Couldn’t remove the member", errMessage(e)),
  });

  if (myRole !== "compliance_admin" && myRole !== "head") {
    return (
      <div>
        <div className="page-head"><h1>Team</h1></div>
        <PermissionDenied what="team management" who="compliance admins and heads"
          action={<a className="btn" href="/dashboard">Back to Today</a>} />
      </div>
    );
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Team</h1>
          <p className="lede">
            {isAdmin
              ? "Roles decide who can prepare, who can approve, and who can change the calendar. Removing a member reassigns their live obligations."
              : "Your team and their roles. Only a compliance admin can invite people or change roles."}
          </p>
        </div>
        {isAdmin && (
          <button className="btn primary" onClick={() => setInviteOpen(true)}>
            Invite teammate
          </button>
        )}
      </div>

      {lastInvite && (
        <div style={{ marginBottom: 16 }}>
          <Note tone="good">
            <div className="between" style={{ gap: 10, alignItems: "flex-start" }}>
              <div style={{ minWidth: 0 }}>
                <b>Invite ready for {lastInvite.email}.</b>
                <div className="micro" style={{ marginTop: 3, opacity: .9 }}>
                  Send them this link — it can be used once, and they must set a password to accept.
                </div>
                <div className="mono truncate" style={{ marginTop: 5, opacity: .85 }}>{lastInvite.url}</div>
              </div>
              <span className="row" style={{ gap: 6, flex: "none" }}>
                <button className="btn sm" onClick={() => {
                  navigator.clipboard?.writeText(lastInvite.url);
                  toast.ok("Link copied");
                }}>Copy link</button>
                <button className="btn sm ghost" aria-label="Dismiss"
                  onClick={() => setLastInvite(null)}><IconX size={12} /></button>
              </span>
            </div>
          </Note>
        </div>
      )}

      <div className="stack">
        <MemberTable
          title="Active members" rows={active} isAdmin={isAdmin}
          myUserId={principal?.user_id}
          loading={members.isLoading} error={members.error} onRetry={members.refetch}
          onRoleChange={(m, to) => setRoleChange({ m, to })}
          onRemove={setRemoving}
          emptyHint="Invite the people who prepare and approve your filings."
        />

        {invited.length > 0 && (
          <MemberTable
            title="Pending invites" rows={invited} isAdmin={isAdmin}
            myUserId={principal?.user_id}
            loading={false} error={null} onRetry={() => {}}
            onRoleChange={(m, to) => setRoleChange({ m, to })}
            onRemove={setRemoving}
            emptyHint=""
            note="These people have been invited but haven't accepted yet. They can't sign in until they set a password."
          />
        )}

        <Disclosure title="What each role can do"
          meta={<span className="micro faint">Role matrix</span>}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Capability</th>
                  {ROLES.map((r) => <th key={r} className="tight" style={{ textAlign: "center" }}>
                    {ROLE_LABEL[r]}
                  </th>)}
                </tr>
              </thead>
              <tbody>
                {CAPABILITIES.map((c) => (
                  <tr key={c.label}>
                    <td>{c.label}</td>
                    {ROLES.map((r) => (
                      <td key={r} className="tight" style={{ textAlign: "center" }}>
                        {c.roles.includes(r)
                          ? <IconCheck size={13} style={{ color: "var(--good)" }} />
                          : <span className="faint">—</span>}
                        <span className="sr-only">
                          {c.roles.includes(r) ? "allowed" : "not allowed"}
                        </span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Disclosure>
      </div>

      <InviteDialog open={inviteOpen} onClose={() => setInviteOpen(false)}
        busy={invite.isPending} onSubmit={(v) => invite.mutate(v)} />

      <ConfirmDialog
        open={!!roleChange} onClose={() => setRoleChange(null)} busy={setRole.isPending}
        title="Change role"
        description={roleChange
          ? `${roleChange.m.full_name || roleChange.m.email} will become ${ROLE_LABEL[roleChange.to]}.`
          : undefined}
        confirmLabel="Change role"
        tone={roleChange?.to === "compliance_admin" ? "danger" : "neutral"}
        consequences={roleChange && (
          <Note tone={roleChange.to === "compliance_admin" ? "warn" : "info"}>
            {ROLE_BLURB[roleChange.to]}
            {roleChange.to === "compliance_admin" && (
              <div style={{ marginTop: 6 }}>
                <b>Admins can generate calendars and override evidence gates.</b> Grant this
                only to someone accountable for the filings.
              </div>
            )}
          </Note>
        )}
        onConfirm={() => {
          if (roleChange) setRole.mutate({ id: roleChange.m.membership_id, r: roleChange.to });
        }}
      />

      <RemoveDialog member={removing} candidates={active.filter((m) => m.membership_id !== removing?.membership_id)}
        busy={remove.isPending} onClose={() => setRemoving(null)}
        onConfirm={(reassign) => removing && remove.mutate({ id: removing.membership_id, reassign })} />
    </div>
  );
}

/* ================================================================== table */

function MemberTable({
  title, rows, isAdmin, myUserId, loading, error, onRetry, onRoleChange, onRemove,
  emptyHint, note,
}: {
  title: string; rows: Member[]; isAdmin: boolean; myUserId?: string;
  loading: boolean; error: unknown; onRetry: () => void;
  onRoleChange: (m: Member, to: Role) => void; onRemove: (m: Member) => void;
  emptyHint: string; note?: string;
}) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h3>{title}</h3>
        <span className="micro muted num">{rows.length}</span>
      </div>
      {note && <div className="filter-summary">{note}</div>}

      {loading && <SkeletonRows rows={4} cols={4} />}
      {!!error && <div style={{ padding: 14 }}><ErrorState error={error} onRetry={onRetry} /></div>}

      {!loading && !error && rows.length === 0 && (
        <Empty icon={<IconUsers size={16} />} title="No members here" hint={emptyHint} />
      )}

      {!loading && rows.length > 0 && (
        <div className="tbl-wrap">
          <table className="tbl">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr>
                <th>Member</th>
                <th className="tight">Role</th>
                <th className="tight">Status</th>
                {isAdmin && <th className="tight"><span className="sr-only">Actions</span></th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => {
                const isSelf = m.user_id === myUserId;
                const label = m.full_name || m.email;
                return (
                  <tr key={m.membership_id}>
                    <td>
                      <span className="row" style={{ gap: 9 }}>
                        <Avatar label={label} size={26} />
                        <span style={{ minWidth: 0 }}>
                          <span className="row" style={{ gap: 6 }}>
                            <span className="truncate" style={{ fontWeight: 550 }}>{label}</span>
                            {isSelf && <span className="tag">You</span>}
                          </span>
                          {m.full_name && <span className="micro faint truncate">{m.email}</span>}
                        </span>
                      </span>
                    </td>
                    <td className="tight">
                      {isAdmin && m.status !== "removed" && !isSelf ? (
                        <label>
                          <span className="sr-only">Role for {label}</span>
                          <select className="input" style={{ width: "auto" }} value={m.role}
                            onChange={(e) => {
                              const to = e.target.value as Role;
                              if (to !== m.role) onRoleChange(m, to);
                            }}>
                            {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                          </select>
                        </label>
                      ) : (
                        <span title={ROLE_BLURB[m.role]}>{ROLE_LABEL[m.role]}</span>
                      )}
                    </td>
                    <td className="tight">
                      <Badge dot tone={m.status === "active" ? "good"
                        : m.status === "invited" ? "warn" : "neutral"}>
                        {m.status === "invited" ? "Invite pending" : m.status}
                      </Badge>
                    </td>
                    {isAdmin && (
                      <td className="tight" style={{ textAlign: "right" }}>
                        {m.status !== "removed" && !isSelf ? (
                          <button className="btn sm danger" onClick={() => onRemove(m)}>Remove</button>
                        ) : isSelf ? (
                          <span className="micro faint">Can’t change your own role</span>
                        ) : null}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ================================================================ dialogs */

function InviteDialog({ open, onClose, busy, onSubmit }: {
  open: boolean; onClose: () => void; busy: boolean;
  onSubmit: (v: { email: string; role: Role; name?: string }) => void;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("preparer");
  const [touched, setTouched] = useState(false);

  const emailError = !email.trim() ? "Enter their work email."
    : !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) ? "That doesn’t look like a valid email address."
    : null;

  return (
    <Modal open={open} onClose={onClose} title="Invite a teammate"
      description="They’ll get a single-use link and must set a password to join."
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn primary" disabled={busy}
            onClick={() => {
              setTouched(true);
              if (!emailError) onSubmit({ email: email.trim(), role, name: name.trim() || undefined });
            }}>
            {busy && <Spinner onDark />}Send invite
          </button>
        </>
      }>
      <div className="stack-sm">
        <Field label="Work email" required error={touched ? emailError : null}>
          {(p) => <input className="input" type="email" value={email} autoFocus
            onChange={(e) => setEmail(e.target.value)} onBlur={() => setTouched(true)} {...p} />}
        </Field>
        <Field label="Full name" hint="Optional — makes the team list and audit trail readable.">
          {(p) => <input className="input" value={name} onChange={(e) => setName(e.target.value)} {...p} />}
        </Field>
        <Field label="Role" required>
          {(p) => (
            <select className="input" value={role} onChange={(e) => setRole(e.target.value as Role)} {...p}>
              {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </select>
          )}
        </Field>
        <Note tone="info">{ROLE_BLURB[role]}</Note>
      </div>
    </Modal>
  );
}

/**
 * Removal is revocation *and* a reassignment decision. Leaving obligations
 * unowned silently is the dangerous default, so it has to be chosen explicitly.
 */
function RemoveDialog({ member, candidates, busy, onClose, onConfirm }: {
  member: Member | null; candidates: Member[]; busy: boolean;
  onClose: () => void; onConfirm: (reassignTo?: string) => void;
}) {
  const [target, setTarget] = useState("");
  const [ackUnassigned, setAckUnassigned] = useState(false);

  const label = member ? (member.full_name || member.email) : "";
  const needsAck = !target && !ackUnassigned;

  return (
    <Modal open={!!member} onClose={onClose} title={`Remove ${label}?`}
      description="Their access is revoked immediately and any existing invite link stops working."
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn danger-solid" disabled={busy || needsAck}
            onClick={() => onConfirm(target || undefined)}>
            {busy && <Spinner onDark />}Remove member
          </button>
        </>
      }>
      <div className="stack-sm">
        <Field label="Reassign their obligations to"
          hint="Anything they currently own moves to this person.">
          {(p) => (
            <select className="input" value={target}
              onChange={(e) => { setTarget(e.target.value); setAckUnassigned(false); }} {...p}>
              <option value="">Leave unassigned</option>
              {candidates.map((c) => (
                <option key={c.user_id} value={c.user_id}>
                  {(c.full_name || c.email)} · {ROLE_LABEL[c.role]}
                </option>
              ))}
            </select>
          )}
        </Field>

        {!target && (
          <Note tone="warn">
            <b>Unowned obligations don’t appear in anyone’s queue and don’t trigger reminders.</b>
            {" "}They will sit unworked until someone is assigned.
            <label className="row" style={{ gap: 8, marginTop: 8, alignItems: "flex-start" }}>
              <span style={{ marginTop: 1 }}>
                <input type="checkbox" checked={ackUnassigned}
                  onChange={(e) => setAckUnassigned(e.target.checked)} />
              </span>
              <span className="micro">I understand and want to leave them unassigned.</span>
            </label>
          </Note>
        )}
        {candidates.length === 0 && (
          <Note tone="crit">
            There is no other active member to reassign to. Invite someone first if these
            obligations need an owner.
          </Note>
        )}
      </div>
    </Modal>
  );
}
