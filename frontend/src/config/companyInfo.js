// Single shared source of company facts for the marketing pages that are
// NOT themselves legal documents — About, Contact, Trust Center, Security,
// and the footer. Change a value once here and every page that imports it
// updates together.
//
// IMPORTANT — scope boundary: this file has no relationship to the contact
// details embedded inside the 13 legal documents under `src/content/legal/`.
// Each of those documents preserves its own contact text exactly as it
// appears in the approved source, independently and verbatim — including
// cases where different documents intentionally (or not) show different
// emails. Nothing here is used to infer, backfill, or standardize any legal
// document's own wording. If the founder decides to standardize contact
// details across the legal documents, that is a separate, explicit edit to
// each affected `src/content/legal/*.js` file after legal review — not an
// import from this file.
//
// `supportEmail`/`generalEmail`/`partnershipEmail` below all read
// "info@courtbazaar.com" because that is the literal, repeated value in the
// approved About Us / Contact Us content itself (used 3x, verbatim) — not
// an inference. Fields with `needsConfig: true` are genuinely unconfirmed —
// the UI renders a visible "Configuration Required" badge for these rather
// than guessing.

export const companyInfo = {
  legalName: "LexOrbit Technologies",
  brandName: "CourtBazaar",
  tagline: "India's First Legal Operations Network & Services Platform",

  supportEmail: { value: "support@courtbazaar.com", needsConfig: false },
  generalEmail: { value: "support@courtbazaar.com", needsConfig: false },
  partnershipEmail: { value: "support@courtbazaar.com", needsConfig: false },
  mediaEmail: { value: null, needsConfig: true },
  grievanceOfficer: { name: null, email: null, needsConfig: true },

  location: { value: "Delhi, India", needsConfig: false },
  officeAddress: {
    value: "DPT, 808B, F-79 & 80, DLF Prime Tower, Okhla Phase-1, Okhla Industrial Estate, New Delhi - 110020, India",
    needsConfig: false,
  },
  businessHours: {
    value: "Monday – Saturday, 10:00 AM – 6:00 PM (IST). Closed on Sundays and public holidays.",
    needsConfig: false,
  },

  operatingCourts: ["Delhi District Courts", "Delhi High Court", "Supreme Court of India"],

  website: "www.courtbazaar.com",

  // Okhla Phase-1 / Okhla Industrial Estate, New Delhi — general-area
  // placement for the map marker (the registered office address above is
  // the confirmed text; this is an approximate coordinate for that area).
  officeCoordinates: { lat: 28.5355, lng: 77.2910 },

  socialLinks: [
    { icon: "f", href: "https://www.facebook.com/share/18wecnfNK8/", label: "Facebook" },
    { icon: "in", href: "https://www.linkedin.com/company/courtbazaar/", label: "LinkedIn" },
    { icon: "X", href: "https://x.com/court_bazaar", label: "X (Twitter)" },
  ],
};
