import { useEffect, useRef, useState } from "react";
import { api } from "./api";

/* Data layer for the Proxy Counsel Recommendations module
   (AvailableAdvocatesPanel.jsx) — calls the real recommendation endpoint
   (GET /recommendations/advocates — see server.py, backed by
   counsel_matching.list_and_recommend, which reuses score_candidates
   unchanged rather than a separate recommendation engine).

   This module is intentionally the only thing AvailableAdvocatesPanel
   fetches through; the panel calls useAdvocateRecommendations itself and
   owns its own AI-mode/filter state — it does not take a hearing-request
   form's context as input, so this data layer works identically regardless
   of what page or form embeds the panel.

   Every field below is optional server-side (list_and_recommend ranks
   whatever verified_counsel_query matches, even with zero filters) — an
   empty context is a valid call, not a special case: it's exactly how AI
   Mode asks for "the best verified proxy counsel" with no manual filters
   applied. */

export async function getAvailableAdvocates(context) {
  const params = {
    court_id: context?.court_id || undefined,
    state_id: context?.state_id || undefined,
    district: context?.district || undefined,
    specialization: context?.specialization || undefined,
    min_experience_years: context?.min_experience_years || undefined,
  };
  const response = await api.get("/recommendations/advocates", { params });
  const { data } = response;
  return { source: data.source, metadata: data.metadata, advocates: data.advocates || [] };
}

const IDLE_STATE = { status: "idle", advocates: [], source: null, metadata: undefined };

/* Owns everything data-related — the debounce, calling getAvailableAdvocates,
   and turning the result into one status AvailableAdvocatesPanel can render
   directly.

   `context === null` means "don't fetch" — Manual Mode passes this before
   the user has applied any filter, so nothing is preloaded/recommended;
   the panel renders its own idle prompt for that status. Any other context
   (including `{}`, which is what AI Mode always passes) triggers a fetch:
   with no filters that simply returns the top verified advocates overall,
   which is exactly what AI Mode wants — Manual Mode never passes `{}`, only
   `null` or a context with at least one filter set, so it can't accidentally
   trigger the same zero-filter "recommend everything" behavior.

   A change to `context` (including flipping between `null` and a real
   object) re-triggers this same debounced fetch since it's serialized into
   the one `contextKey`. */
export function useAdvocateRecommendations(context) {
  const [state, setState] = useState(context ? { ...IDLE_STATE, status: "loading" } : IDLE_STATE);
  const requestIdRef = useRef(0);

  const contextKey = JSON.stringify(context);

  const runFetch = () => {
    if (!context) {
      setState(IDLE_STATE);
      return;
    }
    const requestId = ++requestIdRef.current;
    setState((s) => ({ ...s, status: "loading" }));
    getAvailableAdvocates(context)
      .then(({ source, metadata, advocates }) => {
        if (requestId !== requestIdRef.current) return; // a newer request superseded this one
        setState({ status: advocates?.length ? "ready" : "empty", advocates: advocates || [], source, metadata });
      })
      .catch(() => {
        if (requestId !== requestIdRef.current) return;
        setState({ status: "error", advocates: [], source: null, metadata: undefined });
      });
  };

  useEffect(() => {
    // Drop the previous context's results the instant the context itself
    // changes (e.g. an AI Mode <-> Manual Mode switch, or the user clearing
    // every filter back to idle) rather than leaving them visible for the
    // debounce window — stale results from one mode/search must never
    // remain on screen while the next one is in flight (or not happening).
    requestIdRef.current += 1;
    if (!context) {
      setState(IDLE_STATE);
      return;
    }
    setState({ status: "loading", advocates: [], source: null, metadata: undefined });
    const timer = setTimeout(runFetch, 400); // debounced so rapid field edits don't spam calls
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refetch keyed on the serialized context, not the object identity
  }, [contextKey]);

  return { ...state, refetch: runFetch };
}
