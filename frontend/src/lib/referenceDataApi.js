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

/* Serviceable courts with geocoded coordinates — used by the landing page's
   coverage map. The map is a pure consumer of this master dataset; no
   marker coordinates are ever hardcoded on the frontend (see
   backend/scripts/import_court_coordinates.py for how latitude/longitude
   get into the database). */
export async function getMapCourts() {
  const { data } = await api.get("/courts", { params: { serviceable_only: true, has_coordinates: true } });
  return data; // [{ court_id, name, type, district, state_name, address, latitude, longitude, serviceable, ... }]
}
