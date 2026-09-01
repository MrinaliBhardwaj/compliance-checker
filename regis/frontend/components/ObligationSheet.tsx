"use client";
// Obligation detail sheet — the daily loop for one filing.
//
// Rework notes:
//  • Progressive disclosure: Overview / Evidence / Activity tabs, plus collapsed
//    sections for the reference material. The old drawer rendered everything at
//    once, so the action you needed was always below the fold.
//  • A single "next action" footer. Maker-Checker has an order; the UI now says
//    what that order is instead of offering five equal-weight buttons.
//  • Every consequential action routes through a labelled dialog with a
//    validated reason. Those strings become permanent audit records.
//  • The evidence gate is explained before it blocks you, not after.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import {
  assignInstance, classifyDocument, entityAudit, getInstance, linkDocument, listAssignable,
  transitionInstance, uploadDocumentProgress,
  type AuditEvent, type InstanceDetail, type LifecycleAction, type LinkResult, type Member,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errMessage, useToast } from "@/lib/toast";
import {
  fmtDate, fmtDateTime, humanize, relativeDue, relativeTime, ROLE_SHORT,
} from "@/lib/format";
import {
  IconAlert, IconCheck, IconCheckCircle, IconClock, IconFile, IconPaperclip,
  IconPlay, IconShield, IconUpload, IconUser, IconBan, IconUndo, IconXCircle,
} from "@/components/icons";
import {
  Avatar, Badge, ConfirmDialog, Disclosure, Empty, ErrorState, Field, InlineLoading,
  Meter, Note, RiskMeter, Sheet, Skeleton, Spinner, StatusBadge,
} from "@/components/ui";

const DOC_TYPES = [
  "FILING_ACK", "PAYMENT_CHALLAN", "STATUTORY_CERTIFICATE", "BOARD_SECRETARIAL",
  "POLICY_DOC", "REGISTER_MIS_LOG", "COMPUTATION_RECON", "AUDITED_REPORT",
  "LICENSE_REGISTRATION", "RETURN_STATEMENT_FILE", "INTERNAL_NOTE", "OTHER",
];

type Tab = "overview" | "evidence" | "activity";

export default function ObligationSheet({ instanceId, onClose }:
  { instanceId: string | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("overview");

  const detail = useQuery({
    queryKey: ["instance", instanceId],
    queryFn: () => getInstance(instanceId as string),
    enabled: !!instanceId,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["instance", instanceId] });
    qc.invalidateQueries({ queryKey: ["tracker"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    qc.invalidateQueries({ queryKey: ["instance-audit", instanceId] });
  };

  const d = detail.data;

  return (
    <Sheet
      open={!!instanceId}
      onClose={onClose}
      title={d ? <SheetTitle d={d} /> : <Skeleton w={260} h={16} />}
      tabs={d ? (
        <div className="tabs" role="tablist" aria-label="Obligation detail sections">
          {([
            ["overview", "Overview", null],
            ["evidence", "Evidence", d.linked_documents.length],
            ["activity", "Activity", null],
          ] as [Tab, string, number | null][]).map(([id, label, count]) => (
            <button key={id} role="tab" aria-selected={tab === id}
              onClick={() => setTab(id)}>
              {label}
              {count != null && count > 0 && <span className="tag num">{count}</span>}
            </button>
          ))}
        </div>
      ) : undefined}
      footer={d ? <ActionFooter d={d} onChanged={refresh} /> : undefined}
    >
      {detail.isLoading && (
        <div className="stack">
          <Skeleton h={54} r={8} /><Skeleton h={90} r={8} /><Skeleton h={140} r={8} />
        </div>
      )}
      {detail.isError && <ErrorState error={detail.error} onRetry={detail.refetch} />}
      {d && tab === "overview" && <Overview d={d} onChanged={refresh} />}
      {d && tab === "evidence" && <EvidenceTab d={d} onChanged={refresh} />}
      {d && tab === "activity" && <ActivityTab instanceId={d.id} />}
    </Sheet>
  );
}

/* ================================================================== header */

function SheetTitle({ d }: { d: InstanceDetail }) {
  const rel = relativeDue(d.due_date);
  return (
    <div style={{ minWidth: 0 }}>
      <div className="row-wrap" style={{ gap: 6, marginBottom: 5 }}>
        <StatusBadge status={d.status} />
        <RiskMeter level={d.risk_level} />
        {d.verification_status !== "VERIFIED" && (
          <Badge tone="warn" title="Rests on a DRAFT_UNVERIFIED library entry.">Provisional</Badge>
        )}
      </div>
      <h2 style={{ fontSize: 15.5 }}>{d.title}</h2>
      <div className="micro muted" style={{ marginTop: 3 }}>
        {d.period_label} · {d.category}
        {d.form_reference ? <> · <span className="mono">{d.form_reference}</span></> : null}
        {d.state ? ` · ${d.state}` : ""}
        {" · "}
        <span style={{ color: rel.tone === "crit" ? "var(--crit)" : rel.tone === "warn" ? "var(--warn)" : undefined,
                       fontWeight: rel.tone === "neutral" ? 400 : 600 }}>
          {rel.text}
        </span>
      </div>
    </div>
  );
}

/* ================================================================ overview */

function Overview({ d, onChanged }: { d: InstanceDetail; onChanged: () => void }) {
  const { can } = useAuth();
  const rel = relativeDue(d.due_date);

  return (
    <div className="stack">
      {d.status === "overdue" && (
        <Note tone="crit">
          <b>Past its statutory due date.</b> {d.penalty_note
            ? <> Exposure on record: {d.penalty_note}</>
            : " File as soon as possible and record the reason for the delay."}
        </Note>
      )}
      {d.verification_status !== "VERIFIED" && (
        <Note tone="warn">
          <b>Provisional obligation.</b> This rests on a <span className="mono">DRAFT_UNVERIFIED</span> library
          entry awaiting content-team verification. Treat the due date and evidence
          requirements as indicative until it is verified.
        </Note>
      )}

      <OwnerRow d={d} canAssign={can("assign")} onChanged={onChanged} />

      <div className="panel">
        <div className="panel-body">
          <dl className="kv">
            <dt>Due date</dt>
            <dd>
              {fmtDate(d.due_date)}{" "}
              <span className="micro" style={{
                color: rel.tone === "crit" ? "var(--crit)" : rel.tone === "warn" ? "var(--warn)" : "var(--ink-3)",
              }}>({rel.text})</span>
              {d.working_day_adjusted && (
                <div className="micro faint" style={{ marginTop: 2 }}>
                  Shifted from the statutory date to the next working day.
                </div>
              )}
            </dd>
            <dt>Frequency</dt><dd>{humanize(d.frequency)}</dd>
            <dt>Law</dt><dd className="mono">{d.law_id}</dd>
            {d.applicability_confidence != null && (
              <>
                <dt>Applicability</dt>
                <dd>
                  {Math.round(d.applicability_confidence * 100)}% confidence
                  <span className="micro faint"> · deterministic engine</span>
                </dd>
              </>
            )}
          </dl>
        </div>
      </div>

      <CompletenessPanel d={d} />

      {d.description && (
        <Disclosure title="What this obligation requires" defaultOpen={false}>
          <p className="muted" style={{ fontSize: 12.5, lineHeight: 1.6 }}>{d.description}</p>
        </Disclosure>
      )}

      {d.rationale && (
        <Disclosure title="Why this applies to you"
          meta={<span className="micro faint">Applicability rationale</span>}>
          <p style={{ fontSize: 12.5, lineHeight: 1.6 }}>{d.rationale}</p>
        </Disclosure>
      )}

      {d.penalty_note && (
        <Note tone="mute" icon={<IconAlert size={14} />}>
          <span className="eyebrow" style={{ display: "block", marginBottom: 2 }}>Penalty exposure</span>
          {d.penalty_note}
        </Note>
      )}
    </div>
  );
}

function OwnerRow({ d, canAssign, onChanged }:
  { d: InstanceDetail; canAssign: boolean; onChanged: () => void }) {
  const toast = useToast();
  const { principal } = useAuth();
  const members = useQuery({ queryKey: ["assignable"], queryFn: listAssignable, enabled: canAssign });
  const [busy, setBusy] = useState(false);

  const current: Member | undefined = members.data?.find((m) => m.user_id === d.owner_user_id);
  const isMine = d.owner_user_id && d.owner_user_id === principal?.user_id;
  const ownerLabel = current ? (current.full_name || current.email)
    : isMine ? "You"
    : d.owner_user_id ? "Assigned" : null;

  const assign = async (userId: string) => {
    if (!userId) return;
    setBusy(true);
    try {
      await assignInstance(d.id, userId);
      const who = members.data?.find((m) => m.user_id === userId);
      toast.ok("Owner updated", `Now owned by ${who?.full_name || who?.email || "the selected member"}.`);
      onChanged();
    } catch (e) {
      toast.err("Couldn’t reassign", errMessage(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="panel">
      <div className="panel-body row" style={{ justifyContent: "space-between", gap: 12 }}>
        <div className="row" style={{ gap: 9, minWidth: 0 }}>
          {ownerLabel ? <Avatar label={ownerLabel} size={26} /> : (
            <span aria-hidden="true" style={{
              width: 26, height: 26, borderRadius: "50%", border: "1px dashed var(--rule-2)",
              display: "grid", placeItems: "center", color: "var(--ink-3)", flex: "none",
            }}><IconUser size={13} /></span>
          )}
          <div style={{ minWidth: 0 }}>
            <div className="eyebrow">Owner</div>
            <div className="truncate" style={{ fontWeight: ownerLabel ? 550 : 400 }}>
              {ownerLabel ?? <span className="muted">Unassigned</span>}
              {current && <span className="faint micro"> · {ROLE_SHORT[current.role]}</span>}
            </div>
          </div>
        </div>
        {canAssign && (
          <label style={{ flex: "none" }}>
            <span className="sr-only">Assign owner</span>
            <select className="input" style={{ width: "auto", minWidth: 150 }} disabled={busy}
              value={d.owner_user_id ?? ""} onChange={(e) => assign(e.target.value)}>
              <option value="">{d.owner_user_id ? "Reassign to…" : "Assign to…"}</option>
              {(members.data ?? []).map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {(m.full_name || m.email)} · {ROLE_SHORT[m.role]}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {!ownerLabel && canAssign && (
        <div className="panel-foot">
          Unowned obligations don’t appear in anyone’s queue and don’t trigger reminders.
        </div>
      )}
    </div>
  );
}

function CompletenessPanel({ d }: { d: InstanceDetail }) {
  const c = d.completeness;
  const tone = c.pct >= 100 ? "good" : c.pct > 0 ? "warn" : "crit";
  return (
    <div className="panel">
      <div className="panel-head">
        <h3>Evidence completeness</h3>
        <span className="num" style={{ fontWeight: 600, fontSize: 14 }}>{c.pct}%</span>
      </div>
      <div className="panel-body stack-sm">
        <Meter pct={c.pct} tone={tone} label={`Evidence ${c.pct}% complete`} />
        <div className="row micro" style={{ gap: 6, color: c.primary_present ? "var(--good)" : "var(--warn)" }}>
          {c.primary_present ? <IconCheckCircle size={13} /> : <IconAlert size={13} />}
          <span>
            {c.primary_present
              ? "Primary evidence on file — this can be approved."
              : "Primary evidence missing — required before this can be marked filed."}
          </span>
        </div>
        {c.required.length > 0 && (
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Required evidence</div>
            <div className="stack-sm">
              {c.required.map(([ev, type]) => {
                const covered = c.covered.some(([, t]) => t === type);
                return (
                  <div key={ev} className="row micro" style={{ gap: 7 }}>
                    <span style={{ color: covered ? "var(--good)" : "var(--ink-3)", flex: "none" }}>
                      {covered ? <IconCheck size={12} /> : <IconXCircle size={12} />}
                    </span>
                    <span style={{ color: covered ? "var(--ink)" : "var(--ink-2)" }}>{ev}</span>
                    <span className="tag is-mono">{type}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ================================================================ evidence */

function EvidenceTab({ d, onChanged }: { d: InstanceDetail; onChanged: () => void }) {
  const { can, entityId } = useAuth();
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [pct, setPct] = useState<number | null>(null);
  const [drag, setDrag] = useState(false);
  const [pendingDoc, setPendingDoc] = useState<{ id: string; name: string } | null>(null);
  const [docType, setDocType] = useState("FILING_ACK");
  const [period, setPeriod] = useState(d.period_label);
  const [linkResult, setLinkResult] = useState<LinkResult | null>(null);
  const canUpload = can("upload_evidence");

  const doLink = async (docId: string, override = false) => {
    try {
      const res = await linkDocument(docId, d.id, override);
      setLinkResult(res);
      if (res.blocked) {
        toast.err("Evidence not linked", explainBlock(res.reason));
      } else {
        toast.ok("Evidence linked", "Completeness has been recalculated.");
        setPendingDoc(null);
        onChanged();
      }
    } catch (e) {
      toast.err("Couldn’t link the document", errMessage(e));
    }
  };

  const doUpload = async (file: File) => {
    if (!entityId) { toast.err("No entity selected", "Pick a legal entity in the sidebar first."); return; }
    setPct(0); setLinkResult(null);
    try {
      const res = await uploadDocumentProgress(entityId, file, setPct);
      if (!res.document) {
        toast.err("Duplicate document",
          `This file is already in the repository (${res.duplicate?.verdict ?? "exact match"}). Link the existing copy instead of re-uploading.`);
        return;
      }
      if (res.document.processing_status !== "done") {
        setPendingDoc({ id: res.document.id, name: file.name });
        toast.info("Uploaded — needs classification",
          "Automatic classification was unavailable. Confirm the document type below.");
      } else {
        toast.ok("Uploaded and classified", "Linking it to this obligation…");
        await doLink(res.document.id);
      }
    } catch (e) {
      toast.err("Upload failed", errMessage(e));
    } finally { setPct(null); }
  };

  const doClassifyAndLink = async () => {
    if (!pendingDoc) return;
    try {
      await classifyDocument(pendingDoc.id, docType,
        { period, document_date: new Date().toISOString().slice(0, 10) });
      await doLink(pendingDoc.id);
    } catch (e) {
      toast.err("Couldn’t classify the document", errMessage(e));
    }
  };

  return (
    <div className="stack">
      <div className="panel">
        <div className="panel-head">
          <h3>Linked documents</h3>
          <span className="micro muted num">{d.linked_documents.length} attached</span>
        </div>
        {d.linked_documents.length === 0 ? (
          <Empty icon={<IconPaperclip size={16} />} title="No evidence attached yet"
            hint={canUpload
              ? "Attach the filing acknowledgement, challan or certificate that proves this obligation was met."
              : "Evidence will appear here once a preparer attaches it."} />
        ) : (
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr><th>Document</th><th>Type</th><th className="tight">State</th></tr>
              </thead>
              <tbody>
                {d.linked_documents.map((doc) => (
                  <tr key={doc.id}>
                    <td>
                      <span className="row" style={{ gap: 7 }}>
                        <IconFile size={13} style={{ color: "var(--ink-3)", flex: "none" }} />
                        <span className="truncate">{doc.file_name ?? "Untitled document"}</span>
                      </span>
                    </td>
                    <td>
                      {doc.ai_doc_type
                        ? <span className="tag is-mono">{doc.ai_doc_type}</span>
                        : <span className="faint micro">Unclassified</span>}
                    </td>
                    <td className="tight">
                      <Badge tone={doc.processing_status === "done" ? "good" : "warn"} dot>
                        {humanize(doc.processing_status)}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {!canUpload ? (
        <Note tone="mute">Your role can view evidence but not attach it.</Note>
      ) : (
        <>
          <button type="button" className={`dropzone ${drag ? "drag" : ""}`}
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault(); setDrag(false);
              const f = e.dataTransfer.files?.[0]; if (f) void doUpload(f);
            }}>
            {pct === null ? (
              <span className="stack-sm" style={{ display: "block" }}>
                <IconUpload size={17} style={{ color: "var(--ink-3)" }} />
                <span style={{ display: "block", fontWeight: 550, color: "var(--ink)" }}>
                  Drop a file, or click to browse
                </span>
                <span className="micro faint" style={{ display: "block" }}>
                  PDF, image, XLSX or DOCX · up to 25 MB · scanned for duplicates on upload
                </span>
              </span>
            ) : (
              <span className="stack-sm" style={{ display: "block" }}>
                <span className="row" style={{ justifyContent: "center", gap: 8 }}>
                  <Spinner /> <span>Uploading… {pct}%</span>
                </span>
                <Meter pct={pct} label={`Upload ${pct}% complete`} />
              </span>
            )}
            <input ref={fileRef} type="file" hidden
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void doUpload(f); }} />
          </button>

          {pendingDoc && (
            <div className="panel">
              <div className="panel-head">
                <h3>Confirm document type</h3>
                <span className="micro faint truncate">{pendingDoc.name}</span>
              </div>
              <div className="panel-body stack-sm">
                <Note tone="info">
                  Automatic classification wasn’t available for this file. Confirm what it is —
                  the type determines which evidence requirement it satisfies.
                </Note>
                <div className="row" style={{ gap: 10, alignItems: "flex-end" }}>
                  <div style={{ flex: 1 }}>
                    <Field label="Document type" required>
                      {(p) => (
                        <select className="input" value={docType}
                          onChange={(e) => setDocType(e.target.value)} {...p}>
                          {DOC_TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
                        </select>
                      )}
                    </Field>
                  </div>
                  <div style={{ flex: 1 }}>
                    <Field label="Period" hint="Must match the obligation period.">
                      {(p) => (
                        <input className="input" value={period}
                          onChange={(e) => setPeriod(e.target.value)} {...p} />
                      )}
                    </Field>
                  </div>
                </div>
                <div className="row" style={{ gap: 8 }}>
                  <button className="btn primary" onClick={doClassifyAndLink}>
                    Classify and link
                  </button>
                  <button className="btn ghost" onClick={() => setPendingDoc(null)}>Cancel</button>
                </div>
              </div>
            </div>
          )}

          {linkResult && (
            <div className="panel">
              <div className="panel-head">
                <h3>Validation checks</h3>
                {linkResult.blocked
                  ? <Badge tone="crit" dot>Blocked</Badge>
                  : <Badge tone="good" dot>Passed</Badge>}
              </div>
              <div className="panel-body stack-sm">
                {linkResult.checks.map((c) => (
                  <div key={c.name} className="row" style={{ gap: 8, alignItems: "flex-start" }}>
                    <span style={{
                      flex: "none", marginTop: 1,
                      color: c.result === "pass" ? "var(--good)"
                        : c.result === "warn" ? "var(--warn)" : "var(--crit)",
                    }}>
                      {c.result === "pass" ? <IconCheckCircle size={13} /> : <IconAlert size={13} />}
                    </span>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 550, fontSize: 12 }}>{humanize(c.name)}</div>
                      <div className="micro muted">{c.detail}</div>
                    </div>
                  </div>
                ))}
                {linkResult.blocked && linkResult.reason === "entity_match_fail" && pendingDoc && (
                  <>
                    <Note tone="warn">
                      The entity named in this document doesn’t match the entity this obligation
                      belongs to. Overriding is allowed but is recorded in the audit trail.
                    </Note>
                    <button className="btn danger" onClick={() => doLink(pendingDoc.id, true)}>
                      Link anyway and record an override
                    </button>
                  </>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function explainBlock(reason?: string): string {
  switch (reason) {
    case "entity_match_fail":
      return "The entity on the document doesn’t match this obligation’s entity.";
    case "period_mismatch":
      return "The document’s period doesn’t match this obligation’s period.";
    default:
      return reason ? humanize(reason) : "A validation check failed.";
  }
}

/* ================================================================ activity */

function ActivityTab({ instanceId }: { instanceId: string }) {
  const { can } = useAuth();
  const history = useQuery({
    queryKey: ["instance-audit", instanceId],
    queryFn: () => entityAudit("obligation_instance", instanceId),
    enabled: can("view_audit"),
  });

  if (!can("view_audit")) {
    return (
      <Empty icon={<IconShield size={16} />} title="Activity is restricted"
        hint="The immutable history for an obligation is visible to compliance admins and heads." />
    );
  }
  if (history.isLoading) return <InlineLoading label="Loading history…" />;
  if (history.isError) return <ErrorState error={history.error} onRetry={history.refetch} />;
  if (!history.data?.length) {
    return <Empty icon={<IconClock size={16} />} title="No recorded activity yet"
      hint="Assignments, status changes and evidence links appear here as they happen." />;
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>History</h3>
        <span className="micro faint">Append-only · immutable</span>
      </div>
      <div className="panel-body">
        <div className="timeline">
          {history.data.map((e) => {
            const { text, tone } = describe(e);
            return (
              <div key={e.id} className="tl-item" data-tone={tone}>
                <div style={{ fontSize: 12.5 }}>{text}</div>
                <div className="micro faint" style={{ marginTop: 1 }}>
                  {e.actor_name} · <time dateTime={e.created_at} title={fmtDateTime(e.created_at)}>
                    {relativeTime(e.created_at)}
                  </time>
                </div>
                {typeof e.meta?.reason === "string" && e.meta.reason && (
                  <div className="micro" style={{
                    marginTop: 5, padding: "6px 9px", borderLeft: "2px solid var(--rule-2)",
                    background: "var(--surface-2)", color: "var(--ink-2)", borderRadius: "0 var(--r-xs) var(--r-xs) 0",
                  }}>“{String(e.meta.reason)}”</div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function describe(e: AuditEvent): { text: string; tone: "crit" | "good" | "warn" | "neutral" } {
  const m = e.meta || {};
  if (e.action === "instance_status_change" && m.from && m.to) {
    const to = String(m.to);
    const tone = to === "completed" ? "good" : to === "overdue" ? "crit"
      : to === "ready_for_review" ? "warn" : "neutral";
    const base = `${humanize(String(m.from))} → ${humanize(to)}`;
    return { text: m.override_evidence ? `${base} · evidence gate overridden` : base, tone };
  }
  if (e.action.endsWith("_blocked")) return { text: e.action_label, tone: "crit" };
  return { text: e.action_label, tone: "neutral" };
}

/* ================================================================== footer */

/**
 * The footer states the single next step in the Maker-Checker chain and puts
 * everything else behind secondary weight. Which step is "next" depends on both
 * status and role, so the same obligation reads differently to a preparer and
 * to a checker — which is the point.
 */
function ActionFooter({ d, onChanged }: { d: InstanceDetail; onChanged: () => void }) {
  const { can, role } = useAuth();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [dialog, setDialog] = useState<null | "reject" | "mark_na" | "override" | "reopen">(null);

  const act = async (action: LifecycleAction,
                     body: { override_evidence?: boolean; reason?: string } = {},
                     success?: string) => {
    setBusy(action);
    try {
      await transitionInstance(d.id, action, body);
      toast.ok(success ?? "Updated");
      setDialog(null);
      onChanged();
    } catch (e) {
      toast.err("Couldn’t complete that action", errMessage(e));
    } finally { setBusy(null); }
  };

  const s = d.status;
  const open = s !== "completed" && s !== "not_applicable";
  const gateBlocked = !d.completeness.eligible_for_completion;

  const approve = () => {
    if (gateBlocked) { setDialog("override"); return; }
    void act("approve", {}, "Approved and filed");
  };

  return (
    <>
      <div style={{ width: "100%" }}>
        {s === "ready_for_review" && !can("approve") && (
          <div className="micro muted row" style={{ gap: 6, marginBottom: 8 }}>
            <IconClock size={12} /> Submitted — waiting on a compliance admin or head to approve.
          </div>
        )}
        {gateBlocked && s === "ready_for_review" && can("approve") && (
          <div className="micro row" style={{ gap: 6, marginBottom: 8, color: "var(--warn)" }}>
            <IconAlert size={12} /> Primary evidence is missing — approving requires a recorded override.
          </div>
        )}

        <div className="row-wrap" style={{ gap: 8 }}>
          {/* Primary next action */}
          {s === "ready_for_review" && can("approve") ? (
            <button className="btn primary" disabled={busy !== null} onClick={approve}>
              {busy === "approve" ? <Spinner onDark /> : <IconCheck size={13} />}
              Approve and file
            </button>
          ) : (s === "in_progress" || s === "pending" || s === "overdue") && can("submit") ? (
            <button className="btn primary" disabled={busy !== null} onClick={() => act("submit", {}, "Submitted for review")}>
              {busy === "submit" ? <Spinner onDark /> : <IconCheck size={13} />}
              Submit for review
            </button>
          ) : null}

          {/* Secondary */}
          {(s === "pending" || s === "overdue") && (
            <button className="btn" disabled={busy !== null} onClick={() => act("start", {}, "Marked in progress")}>
              <IconPlay size={12} /> Start work
            </button>
          )}
          {s === "ready_for_review" && can("approve") && (
            <button className="btn danger" disabled={busy !== null} onClick={() => setDialog("reject")}>
              <IconUndo size={13} /> Send back
            </button>
          )}
          {can("mark_na") && open && (
            <button className="btn ghost" disabled={busy !== null} onClick={() => setDialog("mark_na")}>
              <IconBan size={13} /> Mark not applicable
            </button>
          )}
          {can("reopen") && !open && (
            <button className="btn" disabled={busy !== null} onClick={() => setDialog("reopen")}>
              <IconUndo size={13} /> Reopen
            </button>
          )}

          {role === "preparer" && open && (
            <span className="micro faint" style={{ marginLeft: "auto" }}>
              You can start, attach evidence and submit.
            </span>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={dialog === "reject"} onClose={() => setDialog(null)} busy={busy === "reject"}
        title="Send back for changes"
        description="The preparer will be notified and the obligation returns to in-progress."
        confirmLabel="Send back" tone="danger"
        reasonLabel="What needs to change?" reasonRequired
        reasonHint="The preparer sees this verbatim, and it is written to the audit trail."
        onConfirm={(reason) => act("reject", { reason }, "Sent back to the preparer")}
      />

      <ConfirmDialog
        open={dialog === "mark_na"} onClose={() => setDialog(null)} busy={busy === "mark_na"}
        title="Mark not applicable"
        description="This removes the obligation from active queues. It stays on the record with your reason attached."
        confirmLabel="Mark not applicable" tone="danger"
        reasonLabel="Why does this not apply?" reasonRequired
        reasonHint="An auditor may ask you to justify this. Be specific."
        consequences={
          <Note tone="warn">
            <b>{d.title}</b> for {d.period_label} will no longer appear as an open obligation
            or count towards your compliance health.
          </Note>
        }
        onConfirm={(reason) => act("mark_na", { reason }, "Marked not applicable")}
      />

      <ConfirmDialog
        open={dialog === "override"} onClose={() => setDialog(null)} busy={busy === "approve"}
        title="Approve without primary evidence"
        description="The evidence gate normally blocks this. Overriding is permitted but permanently recorded."
        confirmLabel="Override and approve" tone="danger"
        reasonLabel="Why are you approving without primary evidence?" reasonRequired
        reasonHint="This override and your reason are visible to auditors in the trail."
        consequences={
          <Note tone="crit">
            <b>Evidence completeness is {d.completeness.pct}%.</b> Missing:{" "}
            {d.completeness.missing.map(([ev]) => ev).join(", ") || "primary evidence"}.
          </Note>
        }
        onConfirm={(reason) => act("approve", { override_evidence: true, reason }, "Approved with a recorded override")}
      />

      <ConfirmDialog
        open={dialog === "reopen"} onClose={() => setDialog(null)} busy={busy === "reopen"}
        title="Reopen this obligation"
        description="It returns to the active queue and counts towards compliance health again."
        confirmLabel="Reopen"
        reasonLabel="Reason for reopening" reasonRequired
        onConfirm={(reason) => act("reopen", { reason }, "Reopened")}
      />
    </>
  );
}
