import { api } from "./api";

/* My Practice (Proxy Counsel) — profile, availability, performance.
   Same axios-wrapper shape as leadsApi.js/reviewsApi.js. All gated
   server-side by the can_practice_proxy_counsel capability. */

export async function getPracticeProfile() {
  const { data } = await api.get("/practice/profile");
  return data;
}

export async function updatePracticeProfile(patch) {
  const { data } = await api.put("/practice/profile", patch);
  return data;
}

export async function listAvailabilitySlots() {
  const { data } = await api.get("/practice/availability");
  return data;
}

export async function addAvailabilitySlot(slot) {
  const { data } = await api.post("/practice/availability", slot);
  return data;
}

export async function updateAvailabilitySlot(slotId, slot) {
  const { data } = await api.put(`/practice/availability/${slotId}`, slot);
  return data;
}

export async function removeAvailabilitySlot(slotId) {
  const { data } = await api.delete(`/practice/availability/${slotId}`);
  return data;
}

/* Which client-search gates this counsel currently fails (approval, profile
   courts, slot pricing). See practice.client_visibility. */
export async function getPracticeVisibility() {
  const { data } = await api.get("/practice/visibility");
  return data;
}

export async function getPracticePerformance() {
  const { data } = await api.get("/practice/performance");
  return data;
}
