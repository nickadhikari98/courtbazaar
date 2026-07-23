import { api } from "./api";

/* RoleForm's `roleKey` prop (from UtilityBar's role definitions) doesn't
   always match the backend's role_applied_for slug — only "proxyCounsel"
   differs (camelCase vs. snake_case). */
const ROLE_KEY_MAP = { proxyCounsel: "proxy_counsel" };
export function toBackendRole(roleKey) {
  return ROLE_KEY_MAP[roleKey] || roleKey;
}

/* Public "Join as..." lead endpoints. These are anonymous (no login) — the
   returned draft_token proves ownership of an in-progress application and is
   passed explicitly in each call's body/query, never through the shared
   `api` instance's Authorization header (which is reserved for logged-in
   user sessions and would collide with it). */

export async function createLeadDraft(roleAppliedFor, formData, currentStep) {
  const { data } = await api.post("/leads/draft", {
    role_applied_for: roleAppliedFor,
    form_data: formData,
    current_step: currentStep,
  });
  return data; // { lead_id, draft_token }
}

export async function updateLeadDraft(leadId, draftToken, formData, currentStep) {
  const { data } = await api.put(`/leads/${leadId}/draft`, {
    draft_token: draftToken,
    form_data: formData,
    current_step: currentStep,
  });
  return data;
}

export async function uploadLeadDocument(leadId, draftToken, fieldKey, file) {
  const form = new FormData();
  form.append("draft_token", draftToken);
  form.append("field_key", fieldKey);
  form.append("file", file);
  const { data } = await api.post(`/leads/${leadId}/documents`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data; // { doc_id, original_filename, size, content_type, ... }
}

export async function removeLeadDocument(leadId, draftToken, docId) {
  const { data } = await api.delete(`/leads/${leadId}/documents/${docId}`, {
    params: { draft_token: draftToken },
  });
  return data;
}

export async function submitLead(leadId, draftToken) {
  const { data } = await api.post(`/leads/${leadId}/submit`, { draft_token: draftToken });
  return data;
}

/* Admin */

export async function adminListLeads({ status, role, q } = {}) {
  const { data } = await api.get("/admin/leads", { params: { status, role, q } });
  return data;
}

export async function adminGetLead(leadId) {
  const { data } = await api.get(`/admin/leads/${leadId}`);
  return data;
}

export async function adminChangeLeadStatus(leadId, status, remark) {
  const { data } = await api.put(`/admin/leads/${leadId}/status`, { status, remark });
  return data;
}

export async function adminAddLeadNote(leadId, note) {
  const { data } = await api.post(`/admin/leads/${leadId}/notes`, { note });
  return data;
}

export async function adminDeleteLead(leadId) {
  const { data } = await api.delete(`/admin/leads/${leadId}`);
  return data;
}

export async function adminResendWelcomeEmail(leadId) {
  const { data } = await api.post(`/admin/leads/${leadId}/resend-welcome-email`);
  return data;
}

export async function adminReactivateUser(userId) {
  const { data } = await api.put(`/admin/users/${userId}/reactivate`);
  return data;
}

export async function adminGetLeadDocumentUrl(leadId, docId) {
  const { data } = await api.get(`/admin/leads/${leadId}/documents/${docId}/download-url`);
  return data; // { url, filename }
}

export async function adminGetLeadStats() {
  const { data } = await api.get("/admin/leads/stats");
  return data;
}
