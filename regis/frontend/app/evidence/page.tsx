"use client";
// Evidence repository.
//
// New screen. The backend has always exposed GET /documents, but the only way
// to reach a document was to already know which obligation it was linked to and
// open that obligation's drawer. There was no answer to "what evidence do we
// hold?" — a question every RBI inspection starts with.
//
// It also surfaces two things nothing else did: documents that were uploaded
// but never classified (so they satisfy no requirement), and certificates that
// are expiring.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import { listDocuments, uploadDocumentProgress, type DocumentRow } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errMessage, useToast } from "@/lib/toast";
import { daysFromToday, fmtDate, humanize, pluralize, relativeDue } from "@/lib/format";
import Shell from "@/components/Shell";
import {
  IconAlert, IconFile, IconSearch, IconUpload, IconX,
} from "@/components/icons";
import {
  Badge, Empty, ErrorState, Meter, Note, ResultCount, SkeletonRows,
  SortableTh, Spinner, useDebounced, type SortDir,
} from "@/components/ui";

export default function EvidencePage() {
  return <Shell><Evidence /></Shell>;
}

type SortKey = "name" | "type" | "status" | "expiry";

function Evidence() {
  const { can, entityId } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);

  const [qInput, setQInput] = useState("");
  const q = useDebounced(qInput, 180);
  const [type, setType] = useState("");
  const [state, setState] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [pct, setPct] = useState<number | null>(null);
  const [drag, setDrag] = useState(false);

  const docs = useQuery({ queryKey: ["documents"], queryFn: listDocuments });
  const rows = docs.data ?? [];
  const canUpload = can("upload_evidence");

  const types = useMemo(
    () => Array.from(new Set(rows.map((d) => d.ai_doc_type).filter(Boolean) as string[])).sort(),
    [rows]);

  const unclassified = useMemo(
    () => rows.filter((d) => !d.ai_doc_type || d.processing_status !== "done").length, [rows]);
  const expiringSoon = useMemo(
    () => rows.filter((d) => {
      const n = daysFromToday(d.expiry_date);
      return n !== null && n >= 0 && n <= 60;
    }), [rows]);
  const expired = useMemo(
    () => rows.filter((d) => {
      const n = daysFromToday(d.expiry_date);
      return n !== null && n < 0;
    }), [rows]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter((d) => {
      if (type && d.ai_doc_type !== type) return false;
      if (state === "unclassified" && d.ai_doc_type && d.processing_status === "done") return false;
      if (state === "expiring" && !expiringSoon.includes(d)) return false;
      if (state === "expired" && !expired.includes(d)) return false;
      if (needle && !(
        (d.file_name ?? "").toLowerCase().includes(needle)
        || (d.ai_doc_type ?? "").toLowerCase().includes(needle)
      )) return false;
      return true;
    });
  }, [rows, q, type, state, expiringSoon, expired]);

  const sorted = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    const cmp: Record<SortKey, (a: DocumentRow, b: DocumentRow) => number> = {
      name: (a, b) => (a.file_name ?? "").localeCompare(b.file_name ?? ""),
      type: (a, b) => (a.ai_doc_type ?? "zzz").localeCompare(b.ai_doc_type ?? "zzz"),
      status: (a, b) => a.processing_status.localeCompare(b.processing_status),
      expiry: (a, b) => (a.expiry_date ?? "9999").localeCompare(b.expiry_date ?? "9999"),
    };
    return [...filtered].sort((a, b) => cmp[sortKey](a, b) * dir);
  }, [filtered, sortKey, sortDir]);

  const onSort = (k: SortKey) => {
    if (k === sortKey) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortKey(k); setSortDir("asc"); }
  };

  const upload = async (file: File) => {
    if (!entityId) { toast.err("No entity selected", "Pick a legal entity in the sidebar first."); return; }
    setPct(0);
    try {
      const res = await uploadDocumentProgress(entityId, file, setPct);
      if (!res.document) {
        toast.err("Duplicate document",
          `Already in the repository (${res.duplicate?.verdict ?? "exact match"}). Link the existing copy instead.`);
        return;
      }
      qc.invalidateQueries({ queryKey: ["documents"] });
      toast.ok("Document added",
        res.document.processing_status === "done"
          ? "Classified automatically. Link it to an obligation from that obligation's Evidence tab."
          : "Needs classification before it can satisfy an evidence requirement.");
    } catch (e) {
      toast.err("Upload failed", errMessage(e));
    } finally { setPct(null); }
  };

  const filtersActive = !!(q.trim() || type || state);
  const clear = () => { setQInput(""); setType(""); setState(""); };

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Evidence</h1>
          <p className="lede">
            Every document held for this entity. Documents satisfy an obligation only
            once they are classified and linked from that obligation.
          </p>
        </div>
        {canUpload && (
          <button className="btn primary" onClick={() => fileRef.current?.click()} disabled={pct !== null}>
            {pct !== null ? <Spinner onDark /> : <IconUpload size={13} />}
            {pct !== null ? `Uploading ${pct}%` : "Upload document"}
          </button>
        )}
        <input ref={fileRef} type="file" hidden
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} />
      </div>

      {(expired.length > 0 || unclassified > 0) && (
        <div className="stack-sm" style={{ marginBottom: 16 }}>
          {expired.length > 0 && (
            <Note tone="crit">
              <b>{pluralize(expired.length, "document has", "documents have")} passed their expiry date.</b>{" "}
              Expired certificates and licences don’t satisfy an evidence requirement.{" "}
              <button className="btn sm" style={{ marginLeft: 4 }}
                onClick={() => { setState("expired"); }}>Show them</button>
            </Note>
          )}
          {unclassified > 0 && (
            <Note tone="warn">
              <b>{pluralize(unclassified, "document is", "documents are")} unclassified.</b>{" "}
              Until a document has a type it counts towards no obligation’s completeness.{" "}
              <button className="btn sm" style={{ marginLeft: 4 }}
                onClick={() => { setState("unclassified"); }}>Show them</button>
            </Note>
          )}
        </div>
      )}

      {pct !== null && (
        <div className="panel" style={{ marginBottom: 16 }}>
          <div className="panel-body stack-sm">
            <div className="row micro" style={{ gap: 8 }}><Spinner /> Uploading… {pct}%</div>
            <Meter pct={pct} label={`Upload ${pct}% complete`} />
          </div>
        </div>
      )}

      <div className="panel">
        <div className="toolbar">
          <span style={{ position: "relative", flex: 1, minWidth: 200, maxWidth: 320, display: "flex" }}>
            <IconSearch size={13} style={{
              position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)",
              color: "var(--ink-3)", pointerEvents: "none",
            }} />
            <input className="input" style={{ paddingLeft: 27 }} value={qInput}
              onChange={(e) => setQInput(e.target.value)}
              placeholder="Search file names and types…" aria-label="Search evidence" />
            {qInput && (
              <button className="btn icon ghost" aria-label="Clear search"
                style={{ position: "absolute", right: 2, top: "50%", transform: "translateY(-50%)" }}
                onClick={() => setQInput("")}><IconX size={12} /></button>
            )}
          </span>

          <label><span className="sr-only">Filter by document type</span>
            <select className="input" style={{ width: "auto", maxWidth: 220 }} value={type}
              onChange={(e) => setType(e.target.value)}>
              <option value="">All document types</option>
              {types.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
            </select>
          </label>

          <label><span className="sr-only">Filter by state</span>
            <select className="input" style={{ width: "auto" }} value={state}
              onChange={(e) => setState(e.target.value)}>
              <option value="">Any state</option>
              <option value="unclassified">Unclassified</option>
              <option value="expiring">Expiring in 60 days</option>
              <option value="expired">Expired</option>
            </select>
          </label>

          <span className="spacer" />
          <ResultCount shown={sorted.length} total={rows.length} noun="document" />
        </div>

        {filtersActive && (
          <div className="filter-summary">
            <span>Filtered:</span>
            {q.trim() && <span className="tag">“{q.trim()}”</span>}
            {type && <span className="tag">{humanize(type)}</span>}
            {state && <span className="tag">{humanize(state)}</span>}
            <button className="btn sm ghost" onClick={clear}>Clear all</button>
          </div>
        )}

        {docs.isLoading && <SkeletonRows rows={8} cols={4} />}
        {docs.isError && <div style={{ padding: 14 }}>
          <ErrorState error={docs.error} onRetry={docs.refetch} />
        </div>}

        {docs.data && sorted.length === 0 && (
          filtersActive ? (
            <Empty icon={<IconSearch size={16} />} title="No documents match"
              hint="Try a different type or clear the filters."
              action={<button className="btn" onClick={clear}>Clear filters</button>} />
          ) : (
            <Empty icon={<IconFile size={16} />} title="No evidence uploaded yet"
              hint="Filing acknowledgements, challans, certificates and board minutes live here. Upload them once — link them to as many obligations as they satisfy."
              action={canUpload
                ? <button className="btn primary" onClick={() => fileRef.current?.click()}>
                    <IconUpload size={13} /> Upload the first document
                  </button>
                : <span className="micro faint">Your role can view evidence but not upload it.</span>} />
          )
        )}

        {docs.data && sorted.length > 0 && (
          <div className="tbl-wrap">
            <table className="tbl">
              <caption className="sr-only">Evidence documents</caption>
              <thead>
                <tr>
                  <SortableTh id="name" sort={{ key: sortKey, dir: sortDir }} onSort={onSort}>Document</SortableTh>
                  <SortableTh id="type" sort={{ key: sortKey, dir: sortDir }} onSort={onSort}>Type</SortableTh>
                  <SortableTh id="status" sort={{ key: sortKey, dir: sortDir }} onSort={onSort} className="tight">Processing</SortableTh>
                  <SortableTh id="expiry" sort={{ key: sortKey, dir: sortDir }} onSort={onSort} className="tight">Expiry</SortableTh>
                </tr>
              </thead>
              <tbody>
                {sorted.map((d) => {
                  const days = daysFromToday(d.expiry_date);
                  const isExpired = days !== null && days < 0;
                  const isSoon = days !== null && days >= 0 && days <= 60;
                  const classified = !!d.ai_doc_type && d.processing_status === "done";
                  return (
                    <tr key={d.id} data-urgency={isExpired ? "overdue" : isSoon ? "soon" : undefined}>
                      <td className="rail">
                        <span className="row" style={{ gap: 8 }}>
                          <IconFile size={14} style={{ color: "var(--ink-3)", flex: "none" }} />
                          <span style={{ minWidth: 0 }}>
                            <span className="truncate" style={{ display: "block", maxWidth: 380, fontWeight: 550 }}>
                              {d.file_name ?? "Untitled document"}
                            </span>
                            {d.mime_type && <span className="micro faint">{d.mime_type}</span>}
                          </span>
                        </span>
                      </td>
                      <td>
                        {d.ai_doc_type
                          ? <span className="tag is-mono">{d.ai_doc_type}</span>
                          : <span className="row micro" style={{ gap: 5, color: "var(--warn)" }}>
                              <IconAlert size={12} /> Unclassified
                            </span>}
                      </td>
                      <td className="tight">
                        <Badge tone={classified ? "good" : d.processing_status === "failed" ? "crit" : "warn"} dot>
                          {humanize(d.processing_status)}
                        </Badge>
                      </td>
                      <td className="tight">
                        {d.expiry_date ? (
                          <>
                            <div className="num">{fmtDate(d.expiry_date)}</div>
                            <div className="micro" style={{
                              color: isExpired ? "var(--crit)" : isSoon ? "var(--warn)" : "var(--ink-3)",
                              fontWeight: isExpired ? 600 : 400,
                            }}>
                              {isExpired ? `Expired ${Math.abs(days!)} days ago` : relativeDue(d.expiry_date).text}
                            </div>
                          </>
                        ) : <span className="faint">—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {docs.data && rows.length > 0 && (
          <div className="panel-foot">
            Uploads are de-duplicated on content hash, so the same file can’t enter the
            repository twice. Link a document to an obligation from that obligation’s Evidence tab.
          </div>
        )}
      </div>

      {canUpload && docs.data && rows.length > 0 && (
        <button type="button" className={`dropzone ${drag ? "drag" : ""}`} style={{ marginTop: 16 }}
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault(); setDrag(false);
            const f = e.dataTransfer.files?.[0]; if (f) void upload(f);
          }}>
          Drop a file here to add it to the repository · PDF, image, XLSX or DOCX · up to 25 MB
        </button>
      )}
    </div>
  );
}
