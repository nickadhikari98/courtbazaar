/* The only place "work required" options live, keyed by service type — so
   LegalServiceRequestForm never hardcodes proxy-counsel-specific options.
   Adding a new legal service means adding an entry here (even an empty
   list, if that service doesn't need a work-type checklist — see
   serviceRequestFields.js's `requiresWorkType`). */
export const SERVICE_WORK_TYPES = {
  proxy_counsel: [
    "Appearance Only", "Filing", "Mentioning", "Adjournment",
    "Certified Copy", "Inspection", "Other",
  ],
  counsel: [], // populated when Hire Counsel's request form goes live
};
