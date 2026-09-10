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
    // Browse-page filters (founder follow-up, 2026-08) — time_slot matches
    // counsel_matching.PRICING_SLOTS keys ("morning"/"afternoon"/...),
    // experience_bracket matches practice.EXPERIENCE_BRACKETS keys
    // ("0-3"/"3-5"/"5-7"/"10+"). Both optional, undefined when unset so an
    // empty filter never gets sent as a literal "" query param.
    time_slot: context?.time_slot || undefined,
    experience_bracket: context?.experience_bracket || undefined,
    // Bug fix (founder direction, 2026-09): Hearing Date was collected
    // (required to book at all) but never actually narrowed who's shown —
    // a client could pick a counsel who'd already blocked that exact day.
    // Now cross-checked against each candidate's own availability_slots
    // server-side (see counsel_matching.list_and_recommend/
    // practice.is_available_on_date).
    hearing_date: context?.hearing_date || undefined,
    // Backend defaults to 20 (a reasonable AI-recommendation batch size),
    // which silently truncated the browse grid — this page wants "show all
    // verified counsels for these filters", not a top-20 pick, so it always
    // asks for the backend's actual ceiling.
    limit: context?.limit || 100,
  };
  const { data } = await api.get("/public/proxy-counsels", { params });
  return { metadata: data.metadata, advocates: data.advocates || [] };
}

/* Full profile detail for the "View Profile" dialog — viewable by anyone,
   logged in or not (see HireProxyCounsel.jsx: only "Select Counsel" gates on
   login, not viewing a profile). Backed by the same unauthenticated route
   /public/proxy-counsels/{id}/profile uses whether or not a session exists,
   so there's no login/logout flicker on the profile dialog itself. */
export async function getAdvocateProfile(advocateId) {
  const { data } = await api.get(`/public/proxy-counsels/${advocateId}/profile`);
  return data;
}
