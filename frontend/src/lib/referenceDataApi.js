import { api } from "./api";

/* Backend-sourced reference data (states + courts), seeded from
   court_seed_expanded.py. Used by the Court of Practice field so the
   `state_id` it sends to the courts lookup always matches a real record —
   distinct from the unrelated bundled state/district dataset in
   lib/indiaLocations.js. */

export async function getStates() {
  const { data } = await api.get("/states");
  return data; // [{ state_id, name, code, ... }]
}

export async function getCourtsByState(stateId) {
  const { data } = await api.get("/courts", { params: { state_id: stateId } });
  return data; // [{ court_id, name, type, ... }]
}
