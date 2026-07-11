/* Thin accessor over a bundled India states/UTs → districts dataset.
   Components should only ever call getStates()/getDistricts() from here —
   never import the JSON directly. When location data moves to a backend
   endpoint, only this file's internals change (e.g. becomes async and fetches
   `/api/locations`); call sites stay the same.

   Data source: vendored from the `india-states-districts` npm package
   (v1.8.0, all 28 states + 8 union territories) at ./data/indiaStatesDistricts.json.
   Vendored locally rather than imported from node_modules because the
   package's `exports` map only exposes its Node-only (`fs`-based) entry
   point, which can't run in a browser bundle. To refresh with newer data,
   replace that JSON file with an updated official/well-maintained source. */

import locationsData from "./data/indiaStatesDistricts.json";

export const DEFAULT_STATE = "Delhi";

const ALL_REGIONS = [
  ...(locationsData.states || []),
  ...(locationsData.union_territories || []),
];

export function getStates() {
  return ALL_REGIONS.map((region) => region.name);
}

export function getDistricts(stateName) {
  if (!stateName) return [];
  const region = ALL_REGIONS.find(
    (r) => r.name.toLowerCase() === stateName.toLowerCase()
  );
  return region ? region.districts : [];
}
