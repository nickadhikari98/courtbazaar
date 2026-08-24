import { api } from "./api";

/* Public "Write a Review" endpoint. Anonymous, single-shot (no draft/token
   dance like leadsApi — a review has nothing to resume). Every submission
   lands as status="pending" and only appears in listApprovedReviews() once
   an admin approves it. */
export async function submitReview({ name, designation, organization, rating, review, photo }) {
  const form = new FormData();
  form.append("name", name);
  form.append("rating", String(rating));
  form.append("review", review);
  if (designation) form.append("designation", designation);
  if (organization) form.append("organization", organization);
  if (photo) form.append("photo", photo);
  const { data } = await api.post("/reviews", form);
  return data; // { review_id, status, message }
}

export async function listApprovedReviews() {
  const { data } = await api.get("/reviews");
  return data;
}

/* Admin */

export async function adminListReviews({ status, q } = {}) {
  const { data } = await api.get("/admin/reviews", { params: { status, q } });
  return data;
}

export async function adminGetReview(reviewId) {
  const { data } = await api.get(`/admin/reviews/${reviewId}`);
  return data;
}

export async function adminUpdateReview(reviewId, patch) {
  const { data } = await api.put(`/admin/reviews/${reviewId}`, patch);
  return data;
}

export async function adminChangeReviewStatus(reviewId, status) {
  const { data } = await api.put(`/admin/reviews/${reviewId}/status`, { status });
  return data;
}

export async function adminDeleteReview(reviewId) {
  const { data } = await api.delete(`/admin/reviews/${reviewId}`);
  return data;
}

export async function adminBulkReviewAction(reviewIds, action) {
  const { data } = await api.post("/admin/reviews/bulk", { review_ids: reviewIds, action });
  return data;
}

export async function adminReorderReviews(reviewIdsInOrder) {
  const { data } = await api.post("/admin/reviews/reorder", { review_ids: reviewIdsInOrder });
  return data;
}

export async function adminGetReviewStats() {
  const { data } = await api.get("/admin/reviews/stats");
  return data;
}
