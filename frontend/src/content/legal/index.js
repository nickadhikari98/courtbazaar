import terms from "./terms";
import privacy from "./privacy";
import refund from "./refund";
import delivery from "./delivery";
import cookies from "./cookies";
import disclaimer from "./disclaimer";
import confidentiality from "./confidentiality";
import dataRetention from "./data-retention";
import grievance from "./grievance";
import vendorTerms from "./vendor-terms";
import advocateTerms from "./advocate-terms";
import counselTerms from "./counsel-terms";
import efilingTerms from "./efiling-terms";

// Display order for the Legal Center hub grid.
const registry = {
  terms,
  privacy,
  refund,
  delivery,
  cookies,
  disclaimer,
  confidentiality,
  "data-retention": dataRetention,
  grievance,
  "vendor-terms": vendorTerms,
  "advocate-terms": advocateTerms,
  "counsel-terms": counselTerms,
  "efiling-terms": efilingTerms,
};

export const legalDocsList = Object.values(registry);

export function getLegalDoc(slug) {
  return registry[slug];
}
