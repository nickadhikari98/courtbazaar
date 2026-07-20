import { useEffect, useRef, useState } from "react";

/* Everything below `getAvailableAdvocates` is the ONLY function
   AvailableAdvocatesPanel's data (via useAdvocateRecommendations) ever
   comes from. It has no idea whether the result came from mock data, a
   plain backend listing endpoint, or the eventual AI recommendation
   engine. Swapping the mock body below for a real
   `api.get("/recommendations/advocates", { params: context })` call is the
   entire future integration — the return shape ({ source, metadata,
   advocates }) must stay stable, and no component changes.

   `source` is also the mechanism that prevents mock data from ever
   producing an invalid hearing request: "mock" today, "live" (or any
   non-"mock" value) once a real implementation is backed by real
   accounts — AvailableAdvocatesPanel derives `selectable = source !==
   "mock"` and disables Select while it's false. */

const MOCK_ADVOCATES = [
  {
    advocate_id: "mock_adv_1", name: "Adv. Priya Nair", avatar_url: null,
    primary_courts: ["Tis Hazari Court Complex", "Patiala House Court"],
    practice_areas: ["Criminal", "Bail Matters"], languages: ["Hindi", "English", "Punjabi"],
    rating: 4.7, hearings_completed: 138,
    availability: { available_now: true, note: "Available Today" },
    proposed_fee: 1500,
    bio: "12 years at the Delhi District Courts, focused on criminal bail and remand matters.",
    experience_years: 12, education: "LL.B., Faculty of Law, Delhi University",
  },
  {
    advocate_id: "mock_adv_2", name: "Adv. Rohan Deshpande", avatar_url: null,
    primary_courts: ["Mumbai City Civil Court"],
    practice_areas: ["Civil", "Property Disputes"], languages: ["Marathi", "Hindi", "English"],
    rating: 4.5, hearings_completed: 94,
    availability: { available_now: false, note: "Busy Until 3 PM" },
    proposed_fee: 2000,
    bio: "Civil litigation practice with a focus on property and tenancy disputes across Mumbai.",
    experience_years: 9, education: "LL.B., Government Law College, Mumbai",
  },
  {
    advocate_id: "mock_adv_3", name: "Adv. Ayesha Khan", avatar_url: null,
    primary_courts: ["Bengaluru City Civil Court"],
    practice_areas: ["Family", "Consumer"], languages: ["Kannada", "English", "Urdu"],
    rating: 4.9, hearings_completed: 210,
    availability: { available_now: true, note: "Available Today" },
    proposed_fee: 1800,
    bio: "Family court practitioner with a decade of experience in matrimonial and consumer matters.",
    experience_years: 10, education: "LL.B., National Law School of India University",
  },
  {
    advocate_id: "mock_adv_4", name: "Adv. Karthik Subramaniam", avatar_url: null,
    primary_courts: ["Madras City Civil Court"],
    practice_areas: ["Civil", "Writ Petitions"], languages: ["Tamil", "English"],
    rating: 4.3, hearings_completed: 61,
    availability: { available_now: false, note: "Available Tomorrow" },
    proposed_fee: null,
    bio: "Writ and civil practice before the Madras courts, open to short-notice mentioning work.",
    experience_years: 6, education: "B.A. LL.B., School of Excellence in Law, Chennai",
  },
  {
    advocate_id: "mock_adv_5", name: "Adv. Simran Kaur", avatar_url: null,
    primary_courts: ["Saket District Court", "Rohini District Court"],
    practice_areas: ["Criminal", "Cheque Bounce"], languages: ["Punjabi", "Hindi", "English"],
    rating: 4.1, hearings_completed: 42,
    availability: { available_now: false, note: "Unavailable" },
    proposed_fee: 1200,
    bio: "Focused practice in cheque-bounce and NI Act matters across South and North Delhi.",
    experience_years: 5, education: "LL.B., Campus Law Centre, Delhi University",
    // Reserved fields intentionally absent everywhere in this mock set:
    // ai_match_score, ai_match_reasons, estimated_response_time — never
    // fabricated, only ever rendered once a real recommendation source
    // actually provides them.
  },
];

export async function getAvailableAdvocates(context) {
  // `context` is accepted for forward compatibility and intentionally
  // unused by the mock — a real implementation reads it to filter/rank.
  await new Promise((resolve) => setTimeout(resolve, 350)); // simulated latency, so the loading state is visibly exercised
  return { source: "mock", metadata: undefined, advocates: MOCK_ADVOCATES };
}

const hasMinimumContext = (context) =>
  !!context?.court_id || !!(context?.state_id && context?.district);

/* Owns everything data-related — the minimum-context gate, the debounce,
   calling getAvailableAdvocates, and turning the result into one status
   AvailableAdvocatesPanel can render directly. The panel itself never
   imports this module or calls a fetch — see AvailableAdvocatesPanel.jsx. */
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
        if (requestId !== requestIdRef.current) return; // a newer request superseded this one
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
