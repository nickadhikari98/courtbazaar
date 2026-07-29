import { api } from "./api";

/* Negotiation Module — offer/counter-offer/agreement state. Chat itself is
   listHearingMessages/postHearingMessage (hearingRequestsApi.js, unchanged);
   NegotiationChat.jsx merges the two into one feed. Same thin axios-wrapper
   shape as hearingRequestsApi.js. */

export async function getNegotiation(hearingId) {
  const { data } = await api.get(`/hearing-requests/${hearingId}/negotiation`);
  return data;
}

export async function proposeOffer(hearingId, amount, note) {
  const { data } = await api.post(`/hearing-requests/${hearingId}/negotiation/offers`, { amount, note });
  return data;
}

export async function acceptOffer(hearingId, offerId) {
  const { data } = await api.post(`/hearing-requests/${hearingId}/negotiation/offers/${offerId}/accept`);
  return data;
}
