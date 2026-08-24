import { api } from "./api";

/* "Hire Proxy Counsel" marketplace. Same axios-wrapper shape as
   leadsApi.js/reviewsApi.js/practiceApi.js. */

export async function createHearingRequest(payload) {
  const { data } = await api.post("/hearing-requests", payload);
  return data;
}

export async function listHearingRequests() {
  const { data } = await api.get("/hearing-requests");
  return data;
}

export async function getHearingRequest(hearingId) {
  const { data } = await api.get(`/hearing-requests/${hearingId}`);
  return data;
}

export async function acceptHearingRequest(hearingId) {
  const { data } = await api.put(`/hearing-requests/${hearingId}/accept`);
  return data;
}

export async function declineHearingRequest(hearingId) {
  const { data } = await api.put(`/hearing-requests/${hearingId}/decline`);
  return data;
}

// Targeted requests only (target_advocate_id set) — a global, terminal
// reject. Broadcast requests use declineHearingRequest (personal) instead.
export async function rejectHearingRequest(hearingId) {
  const { data } = await api.put(`/hearing-requests/${hearingId}/reject`);
  return data;
}

export async function cancelHearingRequest(hearingId) {
  const { data } = await api.put(`/hearing-requests/${hearingId}/cancel`);
  return data;
}

// Distinct from cancelHearingRequest — closes the negotiation with the
// current targeted counsel only; the underlying request is not cancelled
// (the frontend routes the requester back to counsel selection afterward).
export async function endNegotiation(hearingId) {
  const { data } = await api.put(`/hearing-requests/${hearingId}/end-negotiation`);
  return data;
}

// BlaBlaCar-style flow (founder direction): the case brief is submitted
// here, separately from creation, once payment is confirmed — the backend
// (hearings.submit_case_details) refuses this call otherwise.
export async function submitHearingCaseDetails(hearingId, payload) {
  const { data } = await api.put(`/hearing-requests/${hearingId}/case-details`, payload);
  return data;
}

export async function markHearingConducted(hearingId) {
  const { data } = await api.put(`/hearing-requests/${hearingId}/mark-conducted`);
  return data;
}

export async function createHearingPaymentOrder(hearingId) {
  const { data } = await api.post(`/hearing-requests/${hearingId}/payment/create-order`);
  return data;
}

export async function verifyHearingPayment(hearingId, payload) {
  const { data } = await api.post(`/hearing-requests/${hearingId}/payment/verify`, payload);
  return data;
}

export async function getHearingEscrow(hearingId) {
  const { data } = await api.get(`/hearing-requests/${hearingId}/escrow`);
  return data;
}

// Fallback for NegotiationModule.jsx when it didn't arrive via router state
// (refresh, direct/shared link) — same card shape advocateRecommendationsApi's
// getAvailableAdvocates returns, for the one advocate targeted on this hearing.
export async function getHearingCounselProfile(hearingId) {
  const { data } = await api.get(`/hearing-requests/${hearingId}/counsel-profile`);
  return data;
}

export async function rateHearingRequest(hearingId, rating, review) {
  const { data } = await api.post(`/hearing-requests/${hearingId}/rate`, { rating, review });
  return data;
}

export async function addHearingNote(hearingId, note) {
  const { data } = await api.post(`/hearing-requests/${hearingId}/notes`, { note });
  return data;
}

export async function listHearingMessages(hearingId) {
  const { data } = await api.get(`/hearing-requests/${hearingId}/messages`);
  return data;
}

export async function postHearingMessage(hearingId, text) {
  const { data } = await api.post(`/hearing-requests/${hearingId}/messages`, { text });
  return data;
}

export async function listHearingDocuments(hearingId) {
  const { data } = await api.get(`/hearing-requests/${hearingId}/documents`);
  return data;
}

export async function uploadHearingDocument(hearingId, kind, file) {
  const form = new FormData();
  form.append("kind", kind);
  form.append("file", file);
  const { data } = await api.post(`/hearing-requests/${hearingId}/documents`, form);
  return data;
}

export async function getHearingDocumentUrl(hearingId, docId, { inline = false } = {}) {
  const { data } = await api.get(`/hearing-requests/${hearingId}/documents/${docId}/download-url`, { params: inline ? { inline: true } : undefined });
  return data;
}

// Escrow Module: the Hiring Advocate's one-click "Verify Hearing" — verify
// and release happen server-side in a single call (hearings.verify_and_
// release_payout), unlike the admin pair below which stay deliberately
// separate. Requester-only; backend enforces this too.
export async function verifyAndReleaseHearingPayout(hearingId) {
  const { data } = await api.put(`/hearing-requests/${hearingId}/verify-and-release`);
  return data;
}

// Same endpoint the admin dispute queue below uses (reject-verification) —
// this is now also reachable by the requester ("Raise Dispute" on the
// Negotiation page), routing into the same, unchanged admin dispute queue.
export async function raiseHearingDispute(hearingId, remark) {
  const { data } = await api.put(`/hearing-requests/${hearingId}/reject-verification`, { remark });
  return data;
}

/* Admin verification queue — Verify and Release Payout are always two
   separate calls, never combined, per the founder's ask. */
export async function adminListHearingRequests(status) {
  const { data } = await api.get("/admin/hearing-requests", { params: { status } });
  return data;
}

export async function adminVerifyHearingOrderSheet(hearingId) {
  const { data } = await api.put(`/hearing-requests/${hearingId}/verify`);
  return data;
}

export async function adminRejectHearingVerification(hearingId, remark) {
  const { data } = await api.put(`/hearing-requests/${hearingId}/reject-verification`, { remark });
  return data;
}

export async function adminResolveHearingDispute(hearingId, action, remark) {
  const { data } = await api.put(`/hearing-requests/${hearingId}/resolve-dispute`, { action, remark });
  return data;
}

export async function adminReleaseHearingPayout(hearingId) {
  const { data } = await api.put(`/hearing-requests/${hearingId}/release-payout`);
  return data;
}
