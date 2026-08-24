/* Per-surface feature flags — not a flat on/off list. A feature is hidden or
   shown independently on each surface it could appear on, so e.g. AI
   Assistant can be off the sidebar while still available as a quick action,
   and can be rolled onto new surfaces later without touching the surfaces
   that already ship it.

   `hearing`/`documents` entries below are reserved placeholders for a future
   incremental AI rollout — nothing in the app reads them yet, they exist so
   the shape doesn't need to change when that work starts.

   Hiding a flag here never removes the underlying route, API, or component —
   see App.js, which keeps every route registered regardless of nav
   visibility. Flip the value to re-expose a surface, no other changes needed. */
export const FEATURE_FLAGS = {
  sidebar: {
    // Not part of the founder-approved MVP service list — code/routes/APIs
    // stay intact, just off the permanent workspace nav.
    aiAssistant: false,
    lawFirm: false,
    bulkImport: false,
    myData: false,
  },
  quickActions: {
    // AI Assistant's one remaining entry point: a Dashboard quick-action
    // tile instead of a hero CTA + promo card.
    aiAssistant: true,
  },
  services: {
    // Hire Counsel shares Hire Proxy Counsel's full browse/matching/escrow
    // workflow (see CounselHiringPage.jsx) but is its own distinct nav entry
    // — this flag exists for later toggling, not to hide it now.
    hireCounsel: true,
    // Founder direction (2026-08): only Hire Counsel/Hire Proxy Counsel are
    // the live, promoted services for now — the broader printing/scanning/
    // e-filing/notary/stenographer catalog is real and functional (routes/
    // APIs untouched, see this file's top note) but off nav/Dashboard/hero
    // so a new user isn't shown services alongside the 2 the founder wants
    // front and center. Flip these back on to re-promote that catalog, no
    // other changes needed — see AppLayout.jsx and Dashboard.jsx.
    marketplace: false,
    newOrder: false,
    stenographer: false,
    packages: false,
  },
  hearing: {
    aiAssistant: false, // reserved — no AI-in-hearing UI exists yet
  },
  documents: {
    aiAssistant: false, // reserved — no AI-in-documents UI exists yet
  },
};

/** `isFeatureEnabled("sidebar.aiAssistant")` -> bool. Missing paths default
    to false (fail closed) rather than throwing. */
export function isFeatureEnabled(path) {
  const value = path.split(".").reduce((node, key) => (node == null ? undefined : node[key]), FEATURE_FLAGS);
  return value === true;
}
