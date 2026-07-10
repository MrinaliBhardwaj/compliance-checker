"use client";
// Obligation detail drawer: the daily loop in one place — details, completeness,
// evidence (upload → classify → link), and the role-aware Maker-Checker actions.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import {
  assignInstance, classifyDocument, entityAudit, getInstance, linkDocument, listAssignable,
  transitionInstance, uploadDocumentProgress,
  type AuditEvent, type InstanceDetail, type LifecycleAction, type LinkResult, type Member,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/lib/toast";
import {
  Drawer, Empty, ErrorState, Loading, Progress, RiskBadge, StatusBadge, fmtDate,
} from "@/components/ui";

const DOC_TYPES = [
  "FILING_ACK", "PAYMENT_CHALLAN", "STATUTORY_CERTIFICATE", "BOARD_SECRETARIAL",
  "POLICY_DOC", "REGISTER_MIS_LOG", "COMPUTATION_RECON", "AUDITED_REPORT",
  "LICENSE_REGISTRATION", "RETURN_STATEMENT_FILE", "INTERNAL_NOTE", "OTHER",
];

export default function ObligationDrawer({ instanceId, onClose }:
  { instanceId: string | null; onClose: () => void }) {
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: ["instance", instanceId],
    queryFn: () => getInstance(instanceId as string),
    enabled: !!instanceId,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["instance", instanceId] });
    qc.invalidateQueries({ queryKey: ["queue"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    qc.invalidateQueries({ queryKey: ["tracker"] });
  };

  return (
    <Drawer open={!!instanceId} onClose={onClose}>
      {detail.isLoading && <Loading />}
      {detail.isError && <ErrorState error={detail.error} onRetry={detail.refetch} />}
      {detail.data && <Body d={detail.data} onChanged={refresh} />}
    </Drawer>
  );
}

function Body({ d, onChanged }: { d: InstanceDetail; onChanged: () => void }) {
  const { can, entityId, role } = useAuth();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);

  const act = async (action: LifecycleAction, body: { override_evidence?: boolean; reason?: string } = {}) => {
    setBusy(action);
    try {
      await transitionInstance(d.id, action, body);
      toast(`Marked ${action.replace("_", " ")}`, "ok");
      onChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Action failed", "err");
    } finally {
      setBusy(null);
    }
  };

  const reject = () => {
    const reason = prompt("Reason for sending back for changes?") ?? undefined;
    if (reason !== undefined) void act("reject", { reason });
  };
  const markNa = () => {
    const reason = prompt("Reason for marking not applicable?") ?? undefined;
    if (reason) void act("mark_na", { reason });
  };
  const approve = (override = false) => {
    if (!override && !d.completeness.eligible_for_completion) {
      if (!confirm("Primary evidence isn't present. Approve with override (audited)?")) return;
      return act("approve", { override_evidence: true, reason: "approved without primary evidence" });
    }
    return act("approve", { override_evidence: override });
  };

  const s = d.status;
  return (
    <div className="stack">
      <div>
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          <StatusBadge status={s} /><RiskBadge level={d.risk_level} />
          {d.state && <span className="chip">{d.state}</span>}
        </div>
        <h2 style={{ margin: "8px 0 2px" }}>{d.title}</h2>
        <div className="muted">{d.period_label} · {d.category} · {d.form_reference ?? "—"}</div>
      </div>

      {d.verification_status !== "VERIFIED" && (
        <div className="banner prov">
          Provisional — this obligation rests on a DRAFT_UNVERIFIED library entry pending
          content-team verification.
        </div>
      )}

      <div className="kv">
        <span className="k">Due date</span><span>{fmtDate(d.due_date)}{d.working_day_adjusted ? "  (shifted to a working day)" : ""}</span>
        <span className="k">Frequency</span><span>{d.frequency}</span>
        <span className="k">Confidence</span><span>{d.applicability_confidence ?? "—"}</span>
      </div>
      {d.description && <p className="muted" style={{ margin: 0 }}>{d.description}</p>}
      {d.rationale && <div className="card" style={{ fontSize: 13 }}><b>Why this applies:</b> {d.rationale}</div>}
      {d.penalty_note && <div className="muted" style={{ fontSize: 12 }}>⚠ {d.penalty_note}</div>}

      <OwnerPanel d={d} canAssign={can("assign")} onChanged={onChanged} />

      <Completeness d={d} />

      <EvidencePanel d={d} entityId={entityId} canUpload={can("upload_evidence")} onChanged={onChanged} />

      {/* Maker-Checker actions, role + state aware */}
      <div className="card stack">
        <h3 style={{ margin: 0 }}>Workflow</h3>
        <div className="row" style={{ flexWrap: "wrap" }}>
          {(s === "pending" || s === "overdue" || s === "in_progress") && (
            <button className="btn" disabled={busy === "start"} onClick={() => act("start")}>Start work</button>
          )}
          {(s === "in_progress" || s === "pending" || s === "overdue") && can("submit") && (
            <button className="btn primary" disabled={busy === "submit"} onClick={() => act("submit")}>
              Submit for review
            </button>
          )}
          {s === "ready_for_review" && can("approve") && (
            <>
              <button className="btn ok" disabled={busy === "approve"} onClick={() => approve(false)}>Approve</button>
              <button className="btn danger" disabled={busy === "reject"} onClick={reject}>Send back</button>
            </>
          )}
          {can("mark_na") && s !== "completed" && s !== "not_applicable" && (
            <button className="btn ghost" disabled={busy === "mark_na"} onClick={markNa}>Mark N/A</button>
          )}
          {can("reopen") && (s === "completed" || s === "not_applicable") && (
            <button className="btn ghost" disabled={busy === "reopen"} onClick={() => act("reopen")}>Reopen</button>
          )}
        </div>
        {s === "ready_for_review" && !can("approve") && (
          <div className="muted" style={{ fontSize: 12 }}>Submitted — awaiting approval by an admin or head.</div>
        )}
        {role === "preparer" && <div className="muted" style={{ fontSize: 12 }}>You can start, attach evidence, and submit for review.</div>}
      </div>

      {can("view_audit") && <HistoryPanel instanceId={d.id} />}
    </div>
  );
}

function HistoryPanel({ instanceId }: { instanceId: string }) {
  // Immutable timeline for this obligation — the audit trail, scoped to one item.
  const history = useQuery({
    queryKey: ["instance-audit", instanceId],
    queryFn: () => entityAudit("obligation_instance", instanceId),
  });

  const when = (iso: string) => {
    try {
      return new Date(iso).toLocaleString("en-IN", {
        day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
      });
    } catch { return iso; }
  };
  const line = (e: AuditEvent): string => {
    const m = e.meta || {};
    if (e.action === "instance_status_change" && m.from && m.to) {
      return `${m.from} → ${m.to}${m.override_evidence ? " · evidence override" : ""}`;
    }
    return e.action_label;
  };

  return (
    <div className="card stack">
      <h3 style={{ margin: 0 }}>History</h3>
      {history.isLoading && <Loading />}
      {history.isError && <ErrorState error={history.error} onRetry={history.refetch} />}
      {history.data && (history.data.length === 0
        ? <div className="muted" style={{ fontSize: 12 }}>No recorded activity yet.</div>
        : <div className="stack" style={{ gap: 6 }}>
            {history.data.map((e) => (
              <div key={e.id} className="row" style={{ gap: 10, alignItems: "baseline" }}>
                <span className="muted" style={{ fontSize: 12, whiteSpace: "nowrap", minWidth: 96 }}>
                  {when(e.created_at)}
                </span>
                <span style={{ fontSize: 13 }}>
                  <b>{line(e)}</b>
                  <span className="muted"> · {e.actor_name}</span>
                </span>
              </div>
            ))}
          </div>)}
    </div>
  );
}

function OwnerPanel({ d, canAssign, onChanged }:
  { d: InstanceDetail; canAssign: boolean; onChanged: () => void }) {
  const toast = useToast();
  const members = useQuery({ queryKey: ["assignable"], queryFn: listAssignable, enabled: canAssign });
  const [busy, setBusy] = useState(false);

  const current: Member | undefined = members.data?.find((m) => m.user_id === d.owner_user_id);
  const ownerLabel = current ? (current.full_name || current.email)
    : d.owner_user_id ? "Assigned" : "Unassigned";

  const assign = async (userId: string) => {
    if (!userId) return;
    setBusy(true);
    try {
      await assignInstance(d.id, userId);
      toast("Owner updated", "ok");
      onChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Assign failed", "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card row" style={{ justifyContent: "space-between" }}>
      <div>
        <div className="muted" style={{ fontSize: 12 }}>Owner</div>
        <div>{ownerLabel}</div>
      </div>
      {canAssign && (
        <select className="input" style={{ width: "auto" }} disabled={busy}
          value={d.owner_user_id ?? ""} onChange={(e) => assign(e.target.value)}>
          <option value="">{d.owner_user_id ? "Reassign…" : "Assign to…"}</option>
          {(members.data ?? []).map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {(m.full_name || m.email)} · {m.role === "compliance_admin" ? "Admin" : m.role === "head" ? "Head" : "Preparer"}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

function Completeness({ d }: { d: InstanceDetail }) {
  const c = d.completeness;
  return (
    <div className="card stack">
      <div className="between"><h3 style={{ margin: 0 }}>Evidence completeness</h3>
        <span className="muted">{c.pct}%</span></div>
      <Progress pct={c.pct} />
      <div className="muted" style={{ fontSize: 12 }}>
        {c.primary_present ? "Primary evidence present — eligible for completion."
          : "Primary evidence missing — required before completion."}
      </div>
      {c.required.length > 0 && (
        <div className="pill-row">
          {c.required.map(([ev, type]) => {
            const covered = c.covered.some(([, t]) => t === type);
            return <span key={ev} className="chip" style={{ borderColor: covered ? "var(--ok)" : "var(--line)",
              color: covered ? "var(--ok)" : "var(--muted)" }}>{covered ? "✓" : "○"} {ev}</span>;
          })}
        </div>
      )}
    </div>
  );
}

function EvidencePanel({ d, entityId, canUpload, onChanged }:
  { d: InstanceDetail; entityId: string | null; canUpload: boolean; onChanged: () => void }) {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [pct, setPct] = useState<number | null>(null);
  const [drag, setDrag] = useState(false);
  const [pendingDoc, setPendingDoc] = useState<{ id: string; needsClassify: boolean } | null>(null);
  const [docType, setDocType] = useState("FILING_ACK");
  const [period, setPeriod] = useState(d.period_label);
  const [linkResult, setLinkResult] = useState<LinkResult | null>(null);

  const doUpload = async (file: File) => {
    if (!entityId) { toast("No entity selected", "err"); return; }
    setPct(0); setLinkResult(null);
    try {
      const res = await uploadDocumentProgress(entityId, file, setPct);
      if (!res.document) {
        toast(`Duplicate: ${res.duplicate?.verdict ?? "exists"} — link the existing document instead`, "err");
        setPct(null);
        return;
      }
      const needsClassify = res.document.processing_status !== "done";
      setPendingDoc({ id: res.document.id, needsClassify });
      toast(needsClassify ? "Uploaded — classify it to link" : "Uploaded & auto-classified", "ok");
      if (!needsClassify) await doLink(res.document.id);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Upload failed", "err");
    } finally {
      setPct(null);
    }
  };

  const doClassifyAndLink = async () => {
    if (!pendingDoc) return;
    try {
      await classifyDocument(pendingDoc.id, docType, { period, document_date: new Date().toISOString().slice(0, 10) });
      await doLink(pendingDoc.id);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Classify failed", "err");
    }
  };

  const doLink = async (docId: string, override = false) => {
    try {
      const res = await linkDocument(docId, d.id, override);
      setLinkResult(res);
      if (res.blocked) {
        toast(`Link blocked: ${res.reason}`, "err");
      } else {
        toast("Evidence linked", "ok");
        setPendingDoc(null);
        onChanged();
      }
    } catch (e) {
      // 409 entity-mismatch surfaces here
      toast(e instanceof Error ? e.message : "Link failed", "err");
    }
  };

  return (
    <div className="card stack">
      <h3 style={{ margin: 0 }}>Evidence</h3>
      {d.linked_documents.length > 0 ? (
        <table className="table">
          <tbody>
            {d.linked_documents.map((doc) => (
              <tr key={doc.id}>
                <td>{doc.file_name}</td>
                <td><span className="chip">{doc.ai_doc_type ?? "unclassified"}</span></td>
                <td className="muted">{doc.processing_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <Empty title="No evidence linked yet" />}

      {canUpload && (
        <>
          <div className={`dropzone ${drag ? "drag" : ""}`}
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) void doUpload(f); }}>
            {pct === null ? "Drag a file here or click to upload (PDF, image, XLSX/DOCX)"
              : <div className="stack"><span>Uploading… {pct}%</span><Progress pct={pct} /></div>}
            <input ref={fileRef} type="file" hidden
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void doUpload(f); }} />
          </div>

          {pendingDoc?.needsClassify && (
            <div className="card stack" style={{ background: "var(--panel-2)" }}>
              <div className="muted" style={{ fontSize: 12 }}>
                AI classification unavailable — classify manually, then link.
              </div>
              <div className="row">
                <label className="field" style={{ flex: 1 }}><span>Document type</span>
                  <select className="input" value={docType} onChange={(e) => setDocType(e.target.value)}>
                    {DOC_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </label>
                <label className="field" style={{ flex: 1 }}><span>Period</span>
                  <input className="input" value={period} onChange={(e) => setPeriod(e.target.value)} />
                </label>
              </div>
              <button className="btn primary" onClick={doClassifyAndLink}>Classify & link to this obligation</button>
            </div>
          )}

          {linkResult && (
            <div className="stack">
              <div className="pill-row">
                {linkResult.checks.map((c) => (
                  <span key={c.name} className="chip" title={c.detail}
                    style={{ color: c.result === "pass" ? "var(--ok)" : c.result === "warn" ? "var(--warn)" : "var(--risk)" }}>
                    {c.name}: {c.result}
                  </span>
                ))}
              </div>
              {linkResult.blocked && linkResult.reason === "entity_match_fail" && (
                <button className="btn danger" onClick={() => pendingDoc && doLink(pendingDoc.id, true)}>
                  Override & link anyway (audited)
                </button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
