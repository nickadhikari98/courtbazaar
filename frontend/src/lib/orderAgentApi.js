import { api } from "./api";

/* Order Management Agent — read-only admin summary/triage layer over
   hearing_requests. Both routes are admin-only on the backend (server.py);
   this file only wraps the two new routes, same thin-wrapper convention as
   hearingRequestsApi.js's adminListHearingRequests etc. Neither call ever
   changes a hearing's status, escrow, or assignment. */
export async function getOrderAgentSummary() {
  const { data } = await api.get("/admin/order-agent/summary");
  return data;
}

export async function getOrderAgentHearingSummary(hearingId) {
  const { data } = await api.get(`/admin/order-agent/hearings/${hearingId}/summary`);
  return data;
}
