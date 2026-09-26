import { api } from "./api";

/* Public "Raise a Support Ticket" endpoint (Contact Us page). Anonymous,
   single-shot — same shape as reviewsApi's submitReview, no draft/token dance. */
export async function createSupportTicket({ name, email, phone, category, subject, message, orderId }) {
  const { data } = await api.post("/support/tickets", {
    name,
    email,
    phone: phone || undefined,
    category,
    subject,
    message,
    order_id: orderId || undefined,
  });
  return data; // { ticket_id, status, message }
}

/* Admin */

export async function adminListSupportTickets({ status, category, q } = {}) {
  const { data } = await api.get("/admin/support/tickets", { params: { status, category, q } });
  return data;
}

export async function adminGetSupportTicket(ticketId) {
  const { data } = await api.get(`/admin/support/tickets/${ticketId}`);
  return data;
}

export async function adminChangeSupportTicketStatus(ticketId, status, reply) {
  const { data } = await api.put(`/admin/support/tickets/${ticketId}/status`, { status, reply });
  return data;
}

export async function adminDeleteSupportTicket(ticketId) {
  const { data } = await api.delete(`/admin/support/tickets/${ticketId}`);
  return data;
}

export async function adminGetSupportTicketStats() {
  const { data } = await api.get("/admin/support/tickets/stats");
  return data;
}
