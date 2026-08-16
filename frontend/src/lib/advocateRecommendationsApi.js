import { api } from "./api";

/* Data layer for the Proxy Counsel request flow's recommendation step —
   both CounselDiscoveryPanel (AI recommendations, called with the just-
   submitted request's context) and ManualCounselSearch (the "Search More
   Counsels" fallback, called with `{}`) go through this same function, so
   both ultimately rank against the same verified counsel pool.

   Calls the real recommendation endpoint (GET /recommendations/advocates —
   see server.py, backed by counsel_matching.list_and_recommend, which
   reuses score_candidates unchanged rather than a separate recommendation
   engine). Only court_id/state_id/district are forwarded from `context`:
   those are the only fields on it the endpoint has a matching filter for
   today (work_type, priority, hearing_date, budget are collected by the
   request form but have no backend equivalent yet — not silently
   repurposed as a stand-in for one, e.g. budget is a single figure, not
   the fee_min/fee_max range the endpoint actually supports).

   Every field the endpoint takes is optional server-side (list_and_recommend
   ranks whatever verified_counsel_query matches, even with zero filters) —
   `{}` is a valid call, not a special case: it's exactly what surfaces "the
   best verified proxy counsel" with no filters applied. */
export async function getAvailableAdvocates(context) {
  const params = {
    court_id: context?.court_id || undefined,
    state_id: context?.state_id || undefined,
    district: context?.district || undefined,
  };
  const { data } = await api.get("/recommendations/advocates", { params });
  return { source: data.source, metadata: data.metadata, advocates: data.advocates || [] };
}

/* Public, unauthenticated counterpart to getAvailableAdvocates — backs the
   counsel browse grid on HireProxyCounsel.jsx, which the founder wants
   visible with no login wall (see server.py's /public/proxy-counsels).
   Returns the same shape, just trimmed server-side to card-level fields. */
export async function getPublicProxyCounsels(context) {
  const params = {
    court_id: context?.court_id || undefined,
    state_id: context?.state_id || undefined,
    district: context?.district || undefined,
  };
  const { data } = await api.get("/public/proxy-counsels", { params });
  return { metadata: data.metadata, advocates: data.advocates || [] };
}

/* Full profile detail for the "View Profile" dialog — only ever called once
   a user is logged in (see HireProxyCounsel.jsx's requireLogin gate); the
   backend route itself requires auth too, this isn't just a UI-level gate. */
export async function getAdvocateProfile(advocateId) {
  const { data } = await api.get(`/advocates/${advocateId}/profile`);
  return data;
}
