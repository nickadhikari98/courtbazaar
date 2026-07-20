# CourtBazaar Product Design System

This file is the reference other code in this repo already points to (ESLint's
`no-restricted-syntax` messages cite "PRODUCT_DESIGN_SYSTEM.md §4.1"; several
components cite "DESIGN_SYSTEM_AUDIT.md §2.H" / "§7.4"). It didn't exist until
this pass — this is the first version, written after an audit found the app
already consistently on one design system with only a handful of concrete
gaps (see the Branding & UI Consistency plan this repo's history records).

## §1. Landing Page is the design authority

The Landing Page (`frontend/src/pages/marketing/Landing.jsx` and
`frontend/src/styles/landing.css`) is the visual source of truth for the
entire authenticated workspace, not a separate marketing skin. Any new
workspace page inherits Landing's:

- **Typography** — `font-display` (Cabinet Grotesk) for headings, `cb-overline`
  for eyebrow/label text.
- **Spacing** — `PageContainer` (`components/layout/PageContainer.jsx`) for
  every page's outer wrapper, `PageHeader` (`components/layout/PageHeader.jsx`)
  for every page's title block.
- **Branding** — `Logo` (`components/shared/Logo.jsx`) for every logo
  placement; no page hand-rolls its own icon-in-a-box branding mark.
- **Component language** — the shadcn `Button`/`Card`/`Badge`/`Input` primitives,
  not hand-composed `<button>`/`<div>` markup standing in for them.

...unless there's a documented product reason to differ (e.g. a data table
needs its own scroll container). "I built it a little differently" is not
such a reason on its own — check whether an existing shared component already
covers the need before introducing a new pattern.

## §4.1 Card usage: `bento-card` vs. `dashboard-card`

Both are current, intentional tokens (defined in `frontend/src/index.css`) —
neither is legacy. The rule for which one a piece of content gets:

- **`bento-card`** (`rounded-2xl`, subtle shadow, hover-lift on `:hover`) —
  content the user **browses or scans as a set of options**: Marketplace
  catalog cards, the Available Advocates panel's advocate cards, quick-action
  tiles. The hover-lift signals "this is clickable, pick one."
- **`dashboard-card`** (`rounded-xl`, flat, no hover) — **informational or
  status content**: stat tiles (`StatGrid`), list rows, form sections,
  anything the user reads rather than chooses between.

If a card shows a single number/fact and isn't meant to be "picked," it's
`dashboard-card`. If it's one of several comparable options the user is
choosing between, it's `bento-card`.

## §3.2 / §7.4 Shared components — reuse before you rebuild

Before hand-rolling markup for one of these, check whether the shared
component already covers it:

| Need | Component |
|---|---|
| Page title block (eyebrow + title + description, optional trailing action) | `components/layout/PageHeader.jsx` |
| Icon-badge + label + big-number stat tile, one or many in a grid | `components/shared/StatGrid.jsx` |
| A colored hero band (greeting/title + badges + summary + actions) | `components/shared/WorkspaceHero.jsx` |
| The CourtBazaar logo, in any context (sidebar, auth pages, loading screens) | `components/shared/Logo.jsx` |
| A hearing's prospective progress (not its history) | `components/shared/HearingProgressStepper.jsx` |
| A hearing's activity history | `components/shared/HearingTimeline.jsx` |

`WidgetGrid` (`components/dashboard/WidgetGrid.jsx`) is Dashboard-specific —
it's the registry/`appliesTo` filtering layer on top of `StatGrid` for
Dashboard's conditional home widgets. Pages with a fixed (non-conditional)
stat list should use `StatGrid` directly, not `WidgetGrid`.
