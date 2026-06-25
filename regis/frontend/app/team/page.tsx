"use client";
// Team / user management: invite teammates, assign roles, manage pending invites,
// and remove members with obligation reassignment. Admin writes; head views.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  changeMemberRole, inviteMember, listMembers, removeMember,
  type Member, type Role,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/lib/toast";
import Shell from "@/components/Shell";
import { Empty, ErrorState, Loading } from "@/components/ui";

const ROLE_LABEL: Record<Role, string> = {
  compliance_admin: "Admin", head: "Head/CFO", preparer: "Preparer",
};

export default function TeamPage() {
  return <Shell><Team /></Shell>;
}

function Team() {
  const { role: myRole, principal } = useAuth();
  const isAdmin = myRole === "compliance_admin";
  const qc = useQueryClient();
  const toast = useToast();
  const members = useQuery({ queryKey: ["members"], queryFn: listMembers });

  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("preparer");
  const [lastInvite, setLastInvite] = useState<string | null>(null);

  const invite = useMutation({
    mutationFn: () => inviteMember(email, role, name || undefined),
    onSuccess: (r) => {
      toast(`Invited ${r.email} as ${ROLE_LABEL[r.role]}`, "ok");
      setLastInvite(`${window.location.origin}${r.invite_url}`);
      setEmail(""); setName("");
      qc.invalidateQueries({ queryKey: ["members"] });
    },
    onError: (e) => toast(e instanceof Error ? e.message : "Invite failed", "err"),
  });

  const setMemberRole = useMutation({
    mutationFn: ({ id, r }: { id: string; r: Role }) => changeMemberRole(id, r),
    onSuccess: () => { toast("Role updated", "ok"); qc.invalidateQueries({ queryKey: ["members"] }); },
    onError: (e) => toast(e instanceof Error ? e.message : "Failed", "err"),
  });

  const active = (members.data ?? []).filter((m) => m.status === "active");

  const remove = useMutation({
    mutationFn: ({ id, reassign }: { id: string; reassign?: string }) => removeMember(id, reassign),
    onSuccess: (r) => {
      toast(`Removed · ${r.reassigned_instances} obligation(s) reassigned`, "ok");
      qc.invalidateQueries({ queryKey: ["members"] });
    },
    onError: (e) => toast(e instanceof Error ? e.message : "Failed", "err"),
  });

  const doRemove = (m: Member) => {
    const others = active.filter((x) => x.membership_id !== m.membership_id);
    const target = others.length
      ? prompt(`Reassign ${m.email}'s obligations to which member? Enter email:\n` +
               others.map((o) => `• ${o.email}`).join("\n"))
      : null;
    let reassignId: string | undefined;
    if (target) {
      const found = others.find((o) => o.email.toLowerCase() === target.trim().toLowerCase());
      if (!found) { toast("No matching active member", "err"); return; }
      reassignId = found.user_id;
    }
    if (!confirm(`Remove ${m.email}? Their obligations will be ${reassignId ? "reassigned" : "unassigned"}.`)) return;
    remove.mutate({ id: m.membership_id, reassign: reassignId });
  };

  return (
    <div className="stack">
      <h1>Team</h1>
      <p className="muted">
        {isAdmin ? "Invite teammates and assign roles. Removing a member reassigns their obligations."
          : "Your team and their roles. Only an admin can invite or change roles."}
      </p>

      {isAdmin && (
        <div className="card stack">
          <h3 style={{ margin: 0 }}>Invite a teammate</h3>
          <div className="row" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
            <label className="field" style={{ flex: 2, minWidth: 200 }}><span>Work email</span>
              <input className="input" value={email} onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com" /></label>
            <label className="field" style={{ flex: 2, minWidth: 160 }}><span>Full name (optional)</span>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label className="field" style={{ flex: 1, minWidth: 140 }}><span>Role</span>
              <select className="input" value={role} onChange={(e) => setRole(e.target.value as Role)}>
                <option value="preparer">Preparer</option>
                <option value="head">Head/CFO</option>
                <option value="compliance_admin">Admin</option>
              </select></label>
            <button className="btn primary" disabled={!email || invite.isPending}
              onClick={() => invite.mutate()}>Send invite</button>
          </div>
          {lastInvite && (
            <div className="banner ok" style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>Invite link: {lastInvite}</span>
              <button className="btn sm ghost" onClick={() => { navigator.clipboard?.writeText(lastInvite); toast("Copied", "ok"); }}>
                Copy</button>
            </div>
          )}
        </div>
      )}

      {members.isLoading && <Loading />}
      {members.isError && <ErrorState error={members.error} onRetry={members.refetch} />}
      {members.data && (
        <div className="card" style={{ padding: 0 }}>
          {members.data.length === 0 ? <Empty title="No members yet" /> : (
            <table className="table">
              <thead><tr><th>Member</th><th>Role</th><th>Status</th>{isAdmin && <th></th>}</tr></thead>
              <tbody>
                {members.data.map((m) => {
                  const isSelf = m.user_id === principal?.user_id;
                  return (
                    <tr key={m.membership_id}>
                      <td>
                        <div>{m.full_name || m.email}</div>
                        {m.full_name && <div className="muted" style={{ fontSize: 12 }}>{m.email}</div>}
                      </td>
                      <td>
                        {isAdmin && m.status !== "removed" ? (
                          <select className="input" style={{ width: "auto", padding: "4px 8px" }}
                            value={m.role} disabled={setMemberRole.isPending}
                            onChange={(e) => setMemberRole.mutate({ id: m.membership_id, r: e.target.value as Role })}>
                            <option value="preparer">Preparer</option>
                            <option value="head">Head/CFO</option>
                            <option value="compliance_admin">Admin</option>
                          </select>
                        ) : <span>{ROLE_LABEL[m.role]}</span>}
                      </td>
                      <td>
                        <span className={`badge ${m.status === "active" ? "completed"
                          : m.status === "invited" ? "ready_for_review" : "not_applicable"}`}>
                          <span className="dot" />{m.status}
                        </span>
                      </td>
                      {isAdmin && (
                        <td style={{ textAlign: "right" }}>
                          {m.status !== "removed" && !isSelf && (
                            <button className="btn sm danger" onClick={() => doRemove(m)}>Remove</button>
                          )}
                          {isSelf && <span className="muted" style={{ fontSize: 12 }}>you</span>}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
