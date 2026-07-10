// Typed client for the Regis backend. Calls are proxied via /api -> FastAPI.
// Token in localStorage for the V1 web app (httpOnly cookie is a hardening item).
// All AI surfaces are read-only/assistive by contract.

const TOKEN_KEY = "regis_token";

export function setToken(t: string) {
  if (typeof window !== "undefined") localStorage.setItem(TOKEN_KEY, t);
}
export function getToken(): string | null {
  return typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;
}
export function clearToken() {
  if (typeof window !== "undefined") localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`/api${path}`, { ...opts, headers: { ...headers, ...(opts.headers || {}) } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ---- auth ----
export interface AuthResponse {
  access_token: string; organization_id: string; entity_id: string; role: Role;
}
export type Role = "compliance_admin" | "head" | "preparer";
export interface Principal {
  user_id: string; email: string | null; organization_id: string; role: Role;
  organization_name: string | null;
  entities: { id: string; legal_name: string }[];
}
export const signup = (b: {
  email: string; password: string; organization_name: string; entity_legal_name: string;
}) => req<AuthResponse>("/auth/signup", { method: "POST", body: JSON.stringify(b) });
export const login = (b: { email: string; password: string }) =>
  req<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify(b) });
export const me = () => req<Principal>("/auth/me");
export const acceptInvite = (token: string, password?: string, full_name?: string) =>
  req<AuthResponse>("/auth/accept-invite", { method: "POST", body: JSON.stringify({ token, password, full_name }) });

// ---- team ----
export interface Member {
  membership_id: string; user_id: string; email: string; full_name: string | null;
  role: Role; status: "invited" | "active" | "removed";
}
export interface InviteResult extends Member { invite_token: string; invite_url: string; }
export const inviteMember = (email: string, role: Role, full_name?: string) =>
  req<InviteResult>("/team/invite", { method: "POST", body: JSON.stringify({ email, role, full_name }) });
export const listMembers = () => req<Member[]>("/team/members");
export const listAssignable = () => req<Member[]>("/team/assignable");
export const changeMemberRole = (membership_id: string, role: Role) =>
  req<Member>(`/team/members/${membership_id}/role`, { method: "PATCH", body: JSON.stringify({ role }) });
export const removeMember = (membership_id: string, reassign_to?: string) =>
  req<{ status: string; reassigned_instances: number }>(
    `/team/members/${membership_id}/remove`, { method: "POST", body: JSON.stringify({ reassign_to }) });

// ---- role permissions (mirror PRD §10 role matrix) ----
export type Capability =
  | "generate_calendar" | "assign" | "approve" | "submit" | "mark_na" | "reopen"
  | "upload_evidence" | "export_reports" | "review_legal" | "publish_legal" | "view_audit";

const MATRIX: Record<Capability, Role[]> = {
  generate_calendar: ["compliance_admin"],
  assign: ["compliance_admin"],
  approve: ["compliance_admin", "head"],
  submit: ["compliance_admin", "preparer"],
  mark_na: ["compliance_admin"],
  reopen: ["compliance_admin"],
  upload_evidence: ["compliance_admin", "head", "preparer"],
  export_reports: ["compliance_admin", "head"],
  review_legal: ["compliance_admin", "head"],
  publish_legal: ["compliance_admin"],
  view_audit: ["compliance_admin", "head"],
};
export const can = (role: Role | undefined, cap: Capability) =>
  !!role && MATRIX[cap].includes(role);

// ---- onboarding ----
export const profilePreview = (raw_input: Record<string, unknown>) =>
  req<ProfilePreview>("/onboarding/profile/preview", { method: "POST", body: JSON.stringify({ raw_input }) });
export const generateCalendar = (entity_id: string, raw_input: Record<string, unknown>) =>
  req<GenerateResult>("/onboarding/calendar/generate", { method: "POST", body: JSON.stringify({ entity_id, raw_input }) });

// ---- obligations / dashboard ----
export const getDashboard = () => req<Dashboard>("/obligations/dashboard");
export const getInstances = (f: { status?: string; category?: string; q?: string } = {}) => {
  const qs = new URLSearchParams();
  if (f.status) qs.set("status", f.status);
  if (f.category) qs.set("category", f.category);
  if (f.q) qs.set("q", f.q);
  const s = qs.toString();
  return req<Instance[]>(`/obligations/instances${s ? `?${s}` : ""}`);
};
export const getInstance = (id: string) => req<InstanceDetail>(`/obligations/instances/${id}`);

// ---- obligation lifecycle (Maker-Checker) ----
export type LifecycleAction = "start" | "submit" | "approve" | "reject" | "mark_na" | "reopen";
export const transitionInstance = (
  id: string, action: LifecycleAction, body: { override_evidence?: boolean; reason?: string } = {},
) => req<{ id: string; status: string; completed_at: string | null }>(
  `/obligations/instances/${id}/${action}`, { method: "POST", body: JSON.stringify(body) });
export const assignInstance = (id: string, owner_user_id: string) =>
  req<{ id: string; owner_user_id: string }>(`/obligations/instances/${id}/assign`,
    { method: "POST", body: JSON.stringify({ owner_user_id }) });

// ---- evidence ----
export interface UploadResult {
  document: DocumentRow | null;
  duplicate: { verdict: string; of?: string; action: string } | null;
}
export async function uploadDocument(entity_id: string, file: File): Promise<UploadResult> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("entity_id", entity_id);
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`/api/documents/upload`, { method: "POST", headers, body: fd });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.json();
}
// XHR variant so the UI can show real upload progress.
export function uploadDocumentProgress(
  entity_id: string, file: File, onProgress: (pct: number) => void,
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("entity_id", entity_id);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/documents/upload");
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
      else reject(new ApiError(xhr.status, xhr.statusText || "Upload failed"));
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));
    xhr.send(fd);
  });
}

export const classifyDocument = (id: string, doc_type: string, extracted: Record<string, unknown>) =>
  req<DocumentRow>(`/documents/${id}/classify`, { method: "POST", body: JSON.stringify({ doc_type, extracted }) });
export const linkDocument = (id: string, instance_id: string, override = false) =>
  req<LinkResult>(`/documents/${id}/link`, { method: "POST", body: JSON.stringify({ instance_id, override }) });
export const listDocuments = () => req<DocumentRow[]>("/documents");

// ---- notifications ----
export const listNotifications = (unread_only = false) =>
  req<NotificationItem[]>(`/notifications${unread_only ? "?unread_only=true" : ""}`);
export const markNotificationRead = (id: string) =>
  req(`/notifications/${id}/read`, { method: "POST" });

// ---- legal updates ----
export const listLegalUpdates = () => req<LegalUpdate[]>("/legal-updates");
export const reviewLegalUpdate = (id: string, status: string, reason?: string) =>
  req(`/legal-updates/${id}/review`, { method: "POST", body: JSON.stringify({ status, reason }) });

// ---- reports ----
export const getReport = () => req<Report>("/reports/compliance");
export async function downloadReport(kind: "html" | "pdf"): Promise<Blob> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`/api/reports/compliance.${kind}`, { headers });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.blob();
}

// ---- copilot ----
export const askCopilot = (query: string) =>
  req<CopilotTurn>("/copilot/ask", { method: "POST", body: JSON.stringify({ query }) });

// ---- audit trail ----
export interface AuditEvent {
  id: string; action: string; action_label: string;
  entity_type: string | null; entity_id: string | null;
  actor_user_id: string | null; actor_name: string; actor_email: string | null;
  target_label: string | null; meta: Record<string, unknown>; created_at: string;
}
export interface AuditPage {
  events: AuditEvent[]; limit: number; offset: number; has_more: boolean;
}
export interface AuditCatalog {
  labels: Record<string, string>; groups: Record<string, string[]>;
}
export const getAuditCatalog = () => req<AuditCatalog>("/audit/actions");
export const listAudit = (f: {
  action?: string; entity_type?: string; q?: string;
  since?: string; until?: string; limit?: number; offset?: number;
} = {}) => {
  const qs = new URLSearchParams();
  if (f.action) qs.set("action", f.action);
  if (f.entity_type) qs.set("entity_type", f.entity_type);
  if (f.q) qs.set("q", f.q);
  if (f.since) qs.set("since", f.since);
  if (f.until) qs.set("until", f.until);
  if (f.limit != null) qs.set("limit", String(f.limit));
  if (f.offset != null) qs.set("offset", String(f.offset));
  const s = qs.toString();
  return req<AuditPage>(`/audit${s ? `?${s}` : ""}`);
};
export const entityAudit = (entity_type: string, entity_id: string) =>
  req<AuditEvent[]>(`/audit/entity/${entity_type}/${entity_id}`);

// ---- types ----
export type Status =
  | "pending" | "in_progress" | "ready_for_review" | "completed" | "overdue" | "not_applicable";

export interface Instance {
  id: string; period_label: string; due_date: string | null; status: Status;
  working_day_adjusted: boolean; owner_user_id: string | null;
  title: string; category: string; risk_level: string;
  form_reference: string | null; template_id: string; state: string | null;
}
export interface Completeness {
  required: [string, string][]; covered: [string, string][]; missing: [string, string][];
  pct: number; primary_present: boolean; eligible_for_completion: boolean;
}
export interface LinkedDoc {
  id: string; file_name: string | null; ai_doc_type: string | null; processing_status: string;
}
export interface InstanceDetail extends Instance {
  description: string | null; penalty_note: string | null; frequency: string;
  law_id: string; verification_status: string; applicability_confidence: number | null;
  rationale: string | null; completeness: Completeness; linked_documents: LinkedDoc[];
}
export interface DocumentRow {
  id: string; file_name: string | null; mime_type: string | null; ai_doc_type: string | null;
  ai_extracted: Record<string, unknown>; processing_status: string; expiry_date: string | null;
}
export interface LinkResult {
  blocked: boolean; reason?: string;
  checks: { name: string; result: string; detail: string }[];
  completeness?: Completeness;
}
export interface ProfilePreview {
  profile: Record<string, unknown>;
  provenance: Record<string, { source: string; confidence: number; note: string }>;
  issues: { field: string; severity: string; detail: string }[];
  review_fields: string[]; derived_to_confirm: string[];
  gap_questions: { field: string; question: string; yield: number; hard: boolean }[];
  completeness: { known: number; total: number; pct: number };
}
export interface GenerateResult {
  company_obligations: number; instances: number; event_listeners: number;
  diff: { added: string[]; removed: string[]; unchanged: string[] }; generation_run_id: string;
}
export interface Dashboard {
  health_score: number;
  tiles: { overdue: number; due_this_week: number; awaiting_review: number; completed: number };
  by_status: Record<string, number>; total_instances: number;
}
export interface CopilotTurn {
  intent: string; escalated: boolean; escalation_reason: string | null;
  answer_facts: Record<string, unknown>; citations: string[]; confidence: number;
  grounding: { grounded: boolean; unknown_citations: string[]; citation_count: number };
  scope_note: string | null; provisional: boolean;
}
export interface NotificationItem {
  id: string; type: string; channel: string; payload: Record<string, unknown>;
  sent_at: string | null; read_at: string | null; created_at: string;
}
export interface LegalUpdate {
  id: string; title: string; law_id: string | null; source_url: string | null;
  published_date: string | null; ai_summary: string | null; ai_impact_note: string | null;
  match: "APPLICABLE" | "NEEDS_REVIEW" | "NOT_APPLICABLE"; match_missing: string[];
  review_status: "new" | "reviewed" | "applicable" | "not_applicable";
  affected_obligations: number;
}
export interface Report {
  organization: string; entity: string; as_of: string; library_version: string;
  provisional: boolean; health_score: number;
  totals: { instances: number; by_status: Record<string, number> };
  tiles: { overdue: number; due_this_week: number; awaiting_review: number; completed: number };
  narrative: string; by_category: Record<string, Record<string, number>>;
  sections: Record<string, { period_label: string; title: string; due_date: string | null;
    form_reference: string | null; risk_level: string; status: string; evidence_count?: number }[]>;
}
