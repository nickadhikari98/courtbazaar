import { useEffect, useRef, useState } from "react";
import { api } from "./api";

/* Data layer for the Proxy Counsel Recommendations module
   (AvailableAdvocatesPanel.jsx) — calls the real recommendation endpoint
   (GET /recommendations/advocates — see server.py, backed by
   counsel_matching.list_and_recommend, which reuses score_candidates
   unchanged rather than a separate recommendation engine).

   This module is intentionally the only thing AvailableAdvocatesPanel
   fetches through; the panel calls useAdvocateRecommendations itself and
   owns its own location/filter state — it does not take a hearing-request
   form's context as input, so this data layer works identically regardless
   of what page or form embeds the panel. */

export async function getAvailableAdvocates(context) {
  const params = {
    court_id: context?.court_id || undefined,
    state_id: context?.state_id || undefined,
    district: context?.district || undefined,
    specialization: context?.specialization || undefined,
    min_experience_years: context?.min_experience_years || undefined,
    min_rating: context?.min_rating || undefined,
    fee_min: context?.fee_min || undefined,
    fee_max: context?.fee_max || undefined,
    available_only: context?.available_only || undefined,
  };
  // TEMP DEBUG (remove before commit) -----------------------------------
  // eslint-disable-next-line no-console
  console.log("[CB-DEBUG][3] request URL:", api.getUri({ url: "/recommendations/advocates", params }));
  // eslint-disable-next-line no-console
  console.log("[CB-DEBUG][3] request query params:", params);
  // -----------------------------------------------------------------------
  const response = await api.get("/recommendations/advocates", { params });
  const { data, status } = response;
  // TEMP DEBUG (remove before commit) -----------------------------------
  // eslint-disable-next-line no-console
  console.log("[CB-DEBUG][4] response status:", status);
  // eslint-disable-next-line no-console
  console.log("[CB-DEBUG][5] full response JSON:", JSON.parse(JSON.stringify(data)));
  // eslint-disable-next-line no-console
  console.log("[CB-DEBUG][6] metadata.total_candidates:", data?.metadata?.total_candidates);
  // eslint-disable-next-line no-console
  console.log("[CB-DEBUG][7] advocates.length (from response):", data?.advocates?.length);
  // eslint-disable-next-line no-console
  console.log("[CB-DEBUG][8] advocates array (from response):", data?.advocates);
  // -----------------------------------------------------------------------
  return { source: data.source, metadata: data.metadata, advocates: data.advocates || [] };
}

// State + City (district) is the mandatory Step 1/2 gate the founder asked
// for — no recommendation is fetched until both are chosen, court_id alone
// (an optional Step 3 filter) is never sufficient on its own.
const hasMinimumContext = (context) => !!(context?.state_id && context?.district);

/* Owns everything data-related — the minimum-context gate, the debounce,
   calling getAvailableAdvocates, and turning the result into one status
   AvailableAdvocatesPanel can render directly.

   `context` carries both the location (state_id/district) and the page's
   optional filter inputs (court_id, specialization, min_experience_years,
   min_rating, fee_min, fee_max, available_only) — the caller merges those
   into one object, and a change to any of them re-triggers this same
   debounced fetch since they all live in the one serialized `contextKey`. */
export function useAdvocateRecommendations(context) {
  const [state, setState] = useState({ status: "idle", advocates: [], source: null, metadata: undefined });
  const requestIdRef = useRef(0);

  const contextKey = JSON.stringify(context || {});

  const runFetch = () => {
    if (!hasMinimumContext(context)) {
      setState({ status: "idle", advocates: [], source: null, metadata: undefined });
      return;
    }
    const requestId = ++requestIdRef.current;
    setState((s) => ({ ...s, status: "loading" }));
    getAvailableAdvocates(context)
      .then(({ source, metadata, advocates }) => {
        if (requestId !== requestIdRef.current) {
          // TEMP DEBUG (remove before commit) — a newer request superseded
          // this one, so its result is intentionally discarded, not applied.
          // eslint-disable-next-line no-console
          console.log("[CB-DEBUG] stale response discarded — requestId", requestId, "!= current", requestIdRef.current, "(advocates.length was", advocates?.length, ")");
          return;
        }
        setState({ status: advocates?.length ? "ready" : "empty", advocates: advocates || [], source, metadata });
      })
      .catch(() => {
        if (requestId !== requestIdRef.current) return;
        setState({ status: "error", advocates: [], source: null, metadata: undefined });
      });
  };

  useEffect(() => {
    const timer = setTimeout(runFetch, 400); // debounced so rapid field edits don't spam calls
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refetch keyed on the serialized context, not the object identity
  }, [contextKey]);

  return { ...state, refetch: runFetch };
}
