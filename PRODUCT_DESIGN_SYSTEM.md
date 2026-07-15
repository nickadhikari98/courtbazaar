# CourtBazaar Product Design System

A scalable, token-based design system built for legal-tech SaaS. This system powers the entire product ecosystem from marketing pages to enterprise dashboards.

This is the single source of truth for colors, typography, spacing, component variants, and layout patterns. If you're about to hardcode a color, invent a new spacing value, or build a new card/button style, it belongs here first — see §8.4 "Do / Don't" before writing new UI code.

Related docs: [FOUNDING_ENGINEER_PLAYBOOK.md](FOUNDING_ENGINEER_PLAYBOOK.md) owns process/architecture (this doc owns UI only); [DESIGN_SYSTEM_AUDIT.md](DESIGN_SYSTEM_AUDIT.md) tracks the gap between this spec and the current codebase — read it alongside this doc, since **not every component below is built yet** (see the Build Status legend in §8).

---

## 1. Design Principles

### 1.1 Clarity Over Aesthetics
- Every UI element serves a function
- No decorative elements without purpose
- Enterprise-grade trust signals over startup flash

### 1.2 Consistency Across Surfaces
- Same patterns work for marketing, portals, dashboards, and admin panels
- Users recognize CourtBazaar whether they're on landing or admin console
- Reusable components prevent drift

### 1.3 Scale-First Architecture
- Design for Delhi MVP, but scale to Pan-India, enterprise, and government integrations
- Information architecture accommodates expansion without redesign
- Component system grows with product complexity

### 1.4 Accessibility by Default
- WCAG AA compliance baked into components
- Semantic HTML, keyboard navigation, screen reader support
- Not an afterthought; built-in from day one

### 1.5 Performance Conscious
- Component system reduces bundle size through reuse
- Token-based design prevents style duplication
- Responsive design serves fast on mobile networks

---

## 2. Product Sitemap

### 2.1 Marketing & Auth Layer
```
/                          → Landing page
/login                     → Login page
/register                  → Registration page
/vendor-signup             → Vendor onboarding landing
```

### 2.2 Customer Portal (Advocates, Law Firms)
```
/dashboard                 → Customer dashboard
/order/new                 → Order wizard
/orders                    → Orders list
/orders/:id                → Order details
/marketplace               → Service catalog
/courts                    → Court directory
/ai                        → AI assistant
/wallet                    → Wallet & transactions
/subscription              → Plans & billing
/profile                   → Customer profile
/notifications             → Notification preferences
/firm                      → Law firm management
/firm/bulk-import          → Bulk order import
/my-data                   → Personal data & DPDP
```

### 2.3 Vendor Portal
```
/vendor                    → Vendor dashboard
/vendor/onboard            → Vendor onboarding form
/vendor/settlements        → Settlement history
/orders                    → Order queue (vendor view)
/profile                   → Vendor shop profile
/wallet                    → Vendor earnings
/notifications             → Vendor notifications
```

### 2.4 Delivery Partner Portal
```
/delivery                  → Delivery queue
/profile                   → Delivery profile
/notifications             → Delivery notifications
```

### 2.5 Admin Panel
```
/admin/console             → Command center (super admin)
/admin                     → Analytics dashboard
/admin/vendors             → Vendor management
/admin/pricing             → Pricing controls
/admin/users               → User management
/admin/reconciliation      → Payment reconciliation
/admin/settlements         → Settlement controls
/admin/whatsapp            → WhatsApp template management
/admin/leaderboard         → Vendor leaderboard
/admin/audit-log           → Audit & compliance logs
```

### 2.6 Special Pages
```
/stenographer              → Stenographer booking
```

---

## 3. Shared Components Across Pages

**Legend:** ✅ built and in real use · ⚠️ built but not wired up anywhere · ❌ not built (target only) · 🔀 built 2-3× independently, needs consolidating into one. Full detail on each ✅/🔀 component is in §8; full audit detail (file paths, duplication specifics) is in [DESIGN_SYSTEM_AUDIT.md](DESIGN_SYSTEM_AUDIT.md).

### 3.1 Navigation Components
- ✅ **LandingNav** (`components/landing/LandingNav.jsx`) — marketing nav (landing, login, register, mega menu)
- ✅ **AppLayout** (`components/layout/AppLayout.jsx`) — authenticated nav, sidebar + topbar, role-aware
- 🔀 **Breadcrumb** (`components/legal/Breadcrumb.jsx`) — bespoke, legal pages only; the shadcn `ui/breadcrumb.jsx` primitive it replaced was removed from the project
- ✅ **Tabs** (`ui/tabs.jsx`) — shadcn primitive, used in 8 files

### 3.2 Container & Layout
- ✅ **AppLayout** (`components/layout/AppLayout.jsx`) — sidebar + topbar wrapper; this **is** the dashboard-shell primitive (no separate `DashboardLayout` needed — see §8.4 Do/Don't)
- ✅ **LegalPageLayout** (`components/legal/LegalPageLayout.jsx`) — full legal-doc shell (TOC, breadcrumb, search, print/share); this **is** the legal-layout primitive. Only 1 of 2 legal pages uses it today (`LegalCenter.jsx` doesn't) — that's an adoption gap, not a missing component.
- ✅ **PageContainer** (`components/layout/PageContainer.jsx`) — max-width + padding wrapper. Built 2026-07-15; adoption completed in a follow-up pass — all 27 pages that hand-copied `p-6 lg:p-10 max-w-Nxl mx-auto` (a different max-width passed via `className` where it wasn't the default `max-w-7xl`) now use it, on top of the original 3. See DESIGN_SYSTEM_AUDIT.md §9.1 for the full list. One documented exception: `AIAssistant.jsx` keeps its own wrapper — it's a full-viewport-height flex chat column, not a padded content page.
- ✅ **PageHeader** (`components/layout/PageHeader.jsx`) — eyebrow + h1 + optional description, the pattern hand-copied in ~30 pages. Built and adopted in 8 of them (`AdminAuditLog`, `AdminLeaderboard`, `AdminReconciliation`, `AdminSettlements`, `VendorSettlements`, `MyData`, `FirmManagement` ×2) — see DESIGN_SYSTEM_AUDIT.md §9.2. ~20 more instances exist with minor variance (icon-prefixed eyebrow, different title size, extra trailing element) and are available-to-migrate, not yet done — flagged rather than silently left.
- ✅ **MarketingLayout** (`components/layout/MarketingLayout.jsx`) — UtilityBar + LandingNav + LandingFooter shell. Built 2026-07-15; `Landing.jsx`, `About.jsx`, `Contact.jsx`, `Pricing.jsx`, `Security.jsx`, `Trust.jsx` migrated onto it. `VendorOnboarding.jsx` still opts out (unchanged — see §8.4).
- ✅ **Stack** / **Cluster** (`components/layout/Stack.jsx` / `Cluster.jsx`) — vertical/horizontal flex with a spacing-scale `gap` prop. Built 2026-07-15 and available for new work; not retrofitted onto existing pages since no exact duplicated Stack/Cluster pattern was found to justify a mechanical migration (unlike PageContainer/MarketingLayout, which replaced literal, verified duplicates).
- ❌ **SectionHeader** (a sub-page section variant, distinct from the top-of-page `PageHeader` above) — not built; no page-internal section-header duplication was found frequent/identical enough to justify one yet.
- ❌ **AuthLayout** — deliberately not built. `Login.jsx` and `Register.jsx` share the *concept* of a two-column split but have genuinely different markup (full-bleed image panel with absolute overlays vs. a centered flex container with a bento-card grid). Forcing them onto one shared layout component would require visibly changing one of them to match the other, which is out of scope for an architecture-only pass — see DESIGN_SYSTEM_AUDIT.md §5 for this tracked as a deliberate deferral, not an oversight.

### 3.3 Content Blocks (Landing)
- ✅ **HeroSection** (`components/landing/HeroSection.jsx`) — headline + CTA + `HeroBadge` + `TrackingWidget`
- ✅ **PricingCard** (`components/landing/PricingCard.jsx`) — consolidated 2026-07-15. Was two independent implementations (`PricingCard.jsx` + `pricing/PricingPackageCard.jsx`) with different class-name prefixes; now one component with `variant="teaser"` (homepage) / `variant="full"` (`/pricing` page). No visual change; only the internal prop contract moved to `pkg={...} variant="..."`.
- **`ServiceCard.jsx` / `FeaturedServiceCard.jsx`** — evaluated for the same consolidation and deliberately **left separate**. Unlike the pricing cards, these aren't the same component with cosmetic differences: `ServiceCard` is a small flat grid tile; `FeaturedServiceCard` is a large dark-themed promo unit with two layout modes (vertical/horizontal) and a Link-or-Button CTA. Merging them would mean recreating that branching inside one file with no reduction in actual duplication — the kind of forced abstraction to avoid. Both already share the one thing that was genuinely duplicated (the "Coming Soon" ribbon) via `ComingSoonBadge`.
- ❌ **StatTile**, **MetricsGrid** — not built as standalone components; stat numbers are hand-formatted inline wherever they appear (landing stats, dashboard stats use different font sizes for the same concept — see audit §C)
- ❌ **EmptyState**, **LoadingState**, **ErrorState** — not built as reusable components

### 3.4 Forms
- ✅ **RoleForm + FieldKit** (`components/landing/join/RoleForm.jsx`, `FieldKit.jsx`) — a real, working multi-step form engine (progress bar, step nav, draft autosave via `useDraftForm.js`) driving all 5 "Join as..." role forms from `roleFormData.js` schema. This is the closest thing to the target Form system already in production — extend this pattern rather than building a parallel one.
- ✅ **Combobox** (`components/landing/join/Combobox.jsx`) — single/multi-select, Popover+Command+Checkbox composite
- ✅ **CourtOfPracticeField**, **StateDistrictField**, **DateField** (`components/landing/join/*`) — domain-specific fields built on Combobox/Popover+Calendar
- ✅ **InputOTP** (`ui/input-otp.jsx`) — used in `Login.jsx` only
- ❌ **FormField** (generic label+input+error+hint wrapper), **FormSection**, **FormActions** — not built as standalone generic components outside the join-form engine

### 3.5 Tables & Lists
- ✅ **Table primitives** (`components/ui/table.jsx`) — built 2026-07-15: `Table`, `TableHeader`, `TableBody`, `TableRow`, `TableHead`, `TableCell`, `TableEmpty`, `TableLoading`, `TableSortHead` (optional per-column sorting), `TablePagination` (presentational — caller owns page state). Thin semantic wrappers carrying the styling that was already being hand-typed, not a new visual design.
- ✅ **`AdminAuditLog.jsx`** migrated onto them as the first adopter (zero visual change — same classes, now applied via the component).
- ❌ **Not yet migrated:** `AdminUsers`, `AdminLeads`, `AdminVendors`, `AdminSettlements`, `AdminReconciliation`, `AdminWhatsAppTemplates` still hand-roll their own list/table markup. Each has different columns and none currently implement real sorting/pagination against the API, so migrating them means adapting column-by-column, not a mechanical find-replace — left for a follow-up pass with visual QA per page (see DESIGN_SYSTEM_AUDIT.md §5).
- ❌ **FilterBar** — not built; each admin page still hand-rolls its own filter controls with `Select`/`Input` directly.

### 3.6 Modals & Overlays
- ✅ **Dialog** (`ui/dialog.jsx`) — used in 10 files (RoleSelectModal, WriteReviewModal, etc.)
- ✅ **DropdownMenu** (`ui/dropdown-menu.jsx`) — used only in `AppLayout.jsx` (user menu)
- ✅ **Command** (`ui/command.jsx`) — powers `LegalSearchPalette` and `Combobox`
- ✅ **Popover** (`ui/popover.jsx`) — used in Combobox, DateField
- ❌ **Confirmation**, **Drawer** (mobile nav uses AppLayout's own sidebar toggle, not a generic Drawer primitive)

### 3.7 Feedback & Status
- ✅ **Badge** (`ui/badge.jsx`) — used in 26 files
- ✅ **ComingSoonBadge** (`components/shared/ComingSoonBadge.jsx`) — the one genuinely canonical shared badge instance; other cards reference it directly rather than reimplementing it
- ✅ **Progress** (`ui/progress.jsx`) — used in 2 files
- ✅ **Skeleton** (`ui/skeleton.jsx`) — used only in `VendorSettlements.jsx`
- ✅ **Toast** (`components/ui/sonner.jsx`) — wrapper built 2026-07-15; `App.js`'s `<Toaster/>` mount now goes through it instead of importing `sonner` directly. The imperative `toast(...)` calls in ~30 files still import from the `sonner` package directly — that's correct and matches shadcn's own convention (only the mount point is wrapped, not the function).
- ❌ **Pill**, **Tag**, **StatusIndicator** (as a distinct component — status is currently rendered ad hoc via `Badge` + custom color logic per page)

### 3.8 Dashboard-Specific
- ❌ **DashboardHero, QuickActionsGrid, ActivityFeed, MetricsCard, OrderCard, VendorCard** — none built as standalone components. Dashboard pages hand-build equivalent markup directly (~40 pages under `pages/customer|vendor|admin|delivery`, no `components/dashboard/` folder exists).

### 3.9 Workflow-Specific
- ✅ **RoleForm's step engine** covers step indicator / step panel / progress for the 5 join forms (see 3.4) — this satisfies the "multi-step workflow" need for that flow.
- ❌ **StepIndicator / WorkflowProgress / TimelineStep** as *generic*, reusable-outside-join-forms components — not built. Order tracking/timeline UI (`OrderDetail.jsx`) is hand-rolled separately and doesn't share code with RoleForm's step engine.

---

## 4. Design Tokens

**Implementation:** `frontend/tailwind.config.js` (theme + extend) and the CSS variables in `frontend/src/index.css` (`:root`, lines 39–66) are the single, canonical source for every value below — this section documents that implementation, it does not define a second one. `frontend/src/lib/tokens.js`, a duplicate JS token module with zero imports anywhere in the app, was deleted 2026-07-15 rather than kept as an unused second source (see DESIGN_SYSTEM_AUDIT.md §2.A). If you need a token value in JS (not just a Tailwind class), read it from `getComputedStyle` against the CSS variable, or add it to `tailwind.config.js` `theme.extend` — don't recreate a parallel constants file.

### 4.1 Color Tokens

#### Brand Colors
```
primary: #0F172A (Deep Navy)
accent: #D97706 (Warm Ochre)
```

#### Semantic Colors
```
success: #059669 (Green) — order completed, payment received
warning: #F59E0B (Amber) — pending action, review needed
error: #DC2626 (Red) — failure, cancellation, critical
info: #0EA5E9 (Blue) — informational, notice
```

#### Neutral Colors
```
background: #FAFAFA (Off-white) — page background
foreground: #0A1128 (Dark Navy) — text
card: #FFFFFF (White) — card background
border: #E2E8F0 (Slate-200) — subtle divider
muted: #64748B (Slate-500) — secondary text
```

#### Semantic Backgrounds
```
background-primary: rgba(15, 23, 42, 0.05) — light navy tint
background-accent: rgba(217, 119, 6, 0.05) — light orange tint
background-success: rgba(5, 150, 105, 0.05) — light green tint
background-warning: rgba(245, 158, 11, 0.05) — light amber tint
background-error: rgba(220, 38, 38, 0.05) — light red tint
```

### 4.2 Spacing Scale

**Implementation:** Tailwind's own default spacing scale — no override needed, use `p-*`/`m-*`/`gap-*` directly. These are the named tiers referenced elsewhere in this doc (§6), mapped to the Tailwind classes that actually produce them:

```
2xs:  4px   →  1  (p-1, gap-1, ...)
xs:   8px   →  2
sm:   12px  →  3
md:   16px  →  4
lg:   24px  →  6
xl:   32px  →  8
2xl:  48px  →  12
3xl:  64px  →  16
4xl:  80px  →  20
5xl:  96px  →  24
```

**Usage patterns:**
- Component internal spacing: `xs`, `sm`, `md`
- Section margins: `lg`, `xl`, `2xl`
- Page padding: `md` (mobile), `lg` (tablet), `xl` (desktop)
- Full-bleed sections: no padding

### 4.3 Border Radius

**Implementation:** `frontend/tailwind.config.js` `borderRadius` + `--radius` in `index.css` (currently `0.625rem` / 10px). `sm`/`md`/`lg` are derived from that variable; `xl`/`2xl`/`3xl`/`full` are Tailwind's untouched defaults. This table is the real, current mapping — it doesn't match a round xs/sm/md/lg/xl progression because `--radius` (10px) doesn't evenly divide that way; changing it to fit a cleaner table would visibly change every card/button/input radius, so the table below documents what exists rather than a redesigned scale:

```
rounded-sm:    6px   (var(--radius) - 4px) — inputs, tight elements
rounded-md:    8px   (var(--radius) - 2px) — compact cards, badges
rounded-lg:    10px  (var(--radius))       — standard cards, buttons
rounded-xl:    12px  (Tailwind default)    — larger cards
rounded-2xl:   16px  (Tailwind default)    — hero cards (.bento-card uses this)
rounded-3xl:   24px  (Tailwind default)    — hero sections
rounded-full:  9999px (Tailwind default)   — pills, avatars
```

### 4.4 Shadow System

**Implementation:** Tailwind's default `boxShadow` scale, plus one addition (`shadow-xs`) in `tailwind.config.js` for the one size Tailwind v3 doesn't ship. These are real, measured values — not the rgba(15,23,42,...) navy-tinted recipes an earlier version of this doc specified (those came from the now-deleted `lib/tokens.js`, which was never wired up and didn't match what's actually rendered):

```
shadow-xs:   0 1px 2px 0 rgba(15, 23, 42, 0.05)              — added in tailwind.config.js
shadow-sm:   0 1px 2px 0 rgb(0 0 0 / 0.05)                    — Tailwind default
shadow (DEFAULT): 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)
shadow-md:   0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)
shadow-lg:   0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)
shadow-xl:   0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)
```

**Usage:**
- Cards at rest: `sm`
- Cards on hover: `md`
- Modals/overlays: `lg`
- Elevated UI (popovers): `xl`

### 4.5 Borders

```
width:    1px (standard), 2px (prominent)
color:    border token (E2E8F0)
style:    solid (normal), dashed (optional, for drag zones)
```

---

## 5. Typography

### 5.1 Font Families

- **Display**: Cabinet Grotesk 700–900 (headlines, navigation)
- **Body**: Manrope 400–600 (body text, UI labels)
- **Mono**: JetBrains Mono (order IDs, codes, data)

### 5.2 Type Scale

#### Display Levels (Headlines)
- **Display XL** — 72px / 80px (landing hero)
- **Display L** — 56px / 64px (page titles)
- **Display M** — 48px / 56px (section titles)
- **Display S** — 32px / 40px (subsection titles)

#### Heading Levels (Section Headers)
- **H1** — 48px / 56px (Cabinet Grotesk 700)
- **H2** — 32px / 40px (Cabinet Grotesk 700)
- **H3** — 24px / 32px (Cabinet Grotesk 600)
- **H4** — 20px / 28px (Cabinet Grotesk 600)
- **H5** — 16px / 24px (Cabinet Grotesk 600)
- **H6** — 14px / 22px (Cabinet Grotesk 600)

#### Body Text
- **Body Large** — 18px / 28px (Manrope 400) — hero copy
- **Body Base** — 16px / 24px (Manrope 400) — standard text
- **Body Small** — 14px / 20px (Manrope 400) — secondary text
- **Body XS** — 12px / 16px (Manrope 400) — metadata, captions

#### UI Labels
- **Label** — 14px / 20px (Manrope 600) — form labels, button text
- **Label Small** — 12px / 16px (Manrope 600) — badge, pill, tag
- **Label XS** — 11px / 16px (Manrope 700, uppercase) — overline, metadata
- **Label 2XS** — 10px (Manrope 600) — dense dashboard/admin micro-labels (table meta, compact stat captions). Implemented as `text-2xs` in `tailwind.config.js` (font-size only, no forced line-height, so it drops in wherever `text-[10px]` was used without changing line spacing). All 51 prior `text-[10px]` call sites were migrated to it 2026-07-15. Any new micro-label text must use `text-2xs`, not `text-[10px]`.

### 5.3 Line Height & Letter Spacing

```
Display:    1.2 (tight)    tracking: -0.02em
Heading:    1.3 (tight)    tracking: -0.01em
Body:       1.5 (normal)   tracking: 0
Label:      1.4 (normal)   tracking: 0
UI:         1.2 (tight)    tracking: +0.02em
```

### 5.4 Font Weight Usage

```
400 (Regular)    — body text, secondary text
500 (Medium)     — table data, less emphasis
600 (Semibold)   — form labels, button text, UI labels
700 (Bold)       — headings, emphasis, nav items
800 (Extrabold)  — display, hero titles
900 (Black)      — landing page hero only
```

---

## 6. Spacing System

### 6.1 Vertical Spacing Rules

**Page level:**
- Top padding: `md` (24px mobile), `lg` (32px tablet), `xl` (40px desktop)
- Bottom padding: same as top
- Section margin: `2xl` (48px mobile), `3xl` (64px tablet/desktop)

**Component level:**
- Component internal padding: `sm` to `md`
- Card padding: `lg` (24px)
- Section header spacing: `sm` between overline and title

**Text spacing:**
- Paragraph margin: `md` (16px)
- List item spacing: `sm` (12px)
- Form field spacing: `md` (16px)

### 6.2 Horizontal Spacing Rules

**Page margins:**
- Mobile: `md` (16px left/right)
- Tablet: `lg` (24px left/right)
- Desktop: `xl` (40px left/right), max-width 1280px

**Grid gaps:**
- Tight grid: `sm` (12px) — service cards, stat tiles
- Standard grid: `md` (16px) — card grids
- Loose grid: `lg` (24px) — section grids
- Extra loose: `xl` (32px) — full-width sections

### 6.3 Container Width & Columns

```
Mobile:     full width (no max)
Tablet:     full width (no max)
Desktop:    1200px max-width (max-w-7xl)
Large:      1440px max-width (max-w-screen-2xl)
```

**Grid:**
- Mobile: 4 columns (stacked to 1 or 2)
- Tablet: 8 columns
- Desktop: 12 columns
- Large: 12 columns (increased gap)

---

## 7. Color System (In Practice)

### 7.1 Usage Guidelines

**Primary (Navy):**
- Primary CTA buttons
- Navigation highlights
- Sidebar background
- Page backgrounds
- Headings

**Accent (Orange):**
- Secondary CTA buttons
- Status indicators
- Links
- Badges
- Highlights

**Semantic:**
- Success (Green) — completed orders, approved status
- Warning (Amber) — pending action, review needed
- Error (Red) — cancellation, failure, critical
- Info (Blue) — notifications, informational

**Neutral:**
- Text on white: use foreground
- Secondary text: use muted
- Dividers: use border
- Backgrounds: use background or card

### 7.2 Dark Mode Preparation

**Token structure (for future):**
```css
--primary: light 0F172A / dark F1F5F9
--foreground: light 0A1128 / dark F8FAFC
--card: light FFFFFF / dark 1E293B
--border: light E2E8F0 / dark 334155
```

---

## 8. Component Library

Same legend as §3: ✅ built & live · ⚠️ built but orphaned · ❌ not built · 🔀 duplicated, needs consolidating.

### 8.1 Component Categories

#### Layout Components
- ✅ `PageContainer`, `Stack`, `Cluster` (see §3.2 for build status/adoption detail)
- ✅ `PageHeader` (see §3.2)
- ❌ `Grid`, `Section` — not built

#### Typography Components — all ❌ not built
No typography components exist as such; every page applies the Tailwind classes from §5 directly (`font-display font-black text-5xl ...`). This is workable at current scale but is exactly the pattern the old audit flagged as hard to update consistently (a hero-size change means editing every page that hand-typed the classes). Not urgent to build ahead of the higher-priority gaps in §3.2/§3.5, but the next component built here should be `Heading`/`SectionTitle` since font-size drift between Landing and Dashboard hero text is a real, already-observed instance of this problem.

#### Interactive Components
- ✅ `Button` (`ui/button.jsx`) — primary/secondary/tertiary + size variants, CVA-based, used in 37+ files (2 more converted 2026-07-15). 🔀 **but** 40+ other files still use a raw `<button>` instead (see DESIGN_SYSTEM_AUDIT.md §2.G for the full triage — icon-size conflicts, custom-CSS-class conflicts, and cases that are a genuinely different UI pattern, not a Button).
- ✅ `Select`, `Checkbox`, `Switch`, `RadioGroup`, `Textarea`, `Input`, `Label` — all live shadcn primitives (`ui/*`), each used in 3–23 files
- ✅ `Calendar` + `DateField` — used in the join-form flow only
- ✅ `OTPInput` — used in `Login.jsx` only
- ✅ `FileUpload` (as `add_document` flow in `join/FieldKit.jsx`) — drag-drop exists inside the join-form engine, not as a standalone reusable component yet
- ❌ `ButtonGroup`, generic `Link`, `SearchInput` — not built as standalone components

#### Data Display
- ✅ `Card` (`ui/card.jsx`) — used in 33 files, but 🔀 only `Card`+`CardContent` are ever actually imported; `CardHeader`/`CardTitle`/`CardDescription`/`CardFooter` have zero call sites in `pages/` (see DESIGN_SYSTEM_AUDIT.md §2.F). Prefer the flat `<Card><CardContent>` idiom that's already standard — don't reach for the unused subcomponents without a reason.
- ✅ `Badge` — 26 files
- ❌ `DataTable`, `DataGrid`, `List`, `ListItem`, `StatTile`, `MetricsGrid`, `Tag`, `Pill`, `Timeline` — none built (see §3.5, §3.7, §3.9)
- ✅ `ProgressBar` (`ui/progress.jsx`) — 2 files

#### Feedback Components
- ✅ `Dialog` — 10 files
- ⚠️ `Toast` (via raw `sonner`, no wrapper — see §3.7)
- ✅ `Skeleton` — 1 file (`VendorSettlements.jsx`) only; not yet a general loading pattern
- ❌ `Alert`, `EmptyState`, `LoadingState`, `ErrorState`, `ConfirmationDialog` — not built

#### Dashboard Components — all ❌ not built
`DashboardHero`, `QuickActionsGrid`, `ActivityFeed`, `OrderCard`, `VendorCard`, `DashboardHeader`. No `components/dashboard/` folder exists at all today; this entire category is hand-built per page across ~40 files under `pages/customer|vendor|admin|delivery`.

### 8.2 Component Variants (CVA)

Each component uses class-variance-authority for predictable variants:

```typescript
// Button example
const buttonVariants = cva(
  "px-3 py-2 rounded-md text-sm font-semibold transition-all",
  {
    variants: {
      intent: {
        primary: "bg-primary text-white hover:bg-primary/90",
        secondary: "bg-white border border-border hover:bg-secondary",
        tertiary: "bg-transparent text-primary hover:bg-primary/5",
      },
      size: {
        sm: "h-8 px-2 text-xs",
        md: "h-10 px-4 text-sm",
        lg: "h-12 px-6 text-base",
      },
    },
    defaultVariants: { intent: "primary", size: "md" },
  }
);
```

---

### 8.4 Do / Don't (design-drift rules)

These are not aspirational — every "Don't" below is a real, currently-existing pattern in the codebase that a new engineer might copy without knowing it's already flagged as debt.

- **Don't** create a new pricing/service card. Two pricing-card and three service-card implementations already exist and need consolidating (§3.3, §8.1) — extend one of those, don't add a fourth.
- **Don't** write `text-[10px]`. Use `text-2xs` (§5.2) — the 10px size is already needed everywhere, it just isn't declared as a class yet. If it doesn't exist in `tailwind.config.js` yet, add it there first, then use it.
- **Don't** hardcode hex colors, especially `#0F172A` / `#D97706` / chart-color arrays. Import from the color tokens in §4.1. If a chart needs a color sequence, add one named token (`chart.1`–`chart.5` already exist in `tailwind.config.js`) rather than a new local array.
- **Don't** use a raw `<button>` for anything clickable that isn't a native form submit needing zero styling. Use `ui/button.jsx` variants; if the variant you need doesn't exist (e.g. icon-only ghost for a sidebar toggle), add it to `buttonVariants` in §8.2 first.
- **Don't** hand-roll a table. There's no `DataTable` yet (§8.1) — if you're about to build one for a new admin page, that's the signal to build the shared component instead of a 6th hand-rolled one.
- **Don't** copy `p-6 lg:p-10 max-w-7xl mx-auto` into a new dashboard page. Until `PageContainer` exists, treat this exact string as the de facto standard and don't vary it — but flag to whoever owns the design system backlog that this is the next component to build.
- **Do** reuse `AppLayout` for any new authenticated page and `LegalPageLayout` for any new legal document page — both are real, working, and already handle the hard parts (nav, role-awareness, TOC/search).
- **Do** extend `RoleForm`/`FieldKit` (§3.4) for any new multi-step form rather than building a new step engine — it already has draft autosave, progress tracking, and 5 working schemas to copy from.
- **Do** put any new component that doesn't fit an existing category into this document (§3 or §8) before writing it, per the folder map in §16.
- **Naming convention for content containers** (found inconsistent in a follow-up audit — not worth renaming existing components over, but apply going forward): "Card" = a clickable/bordered standalone unit (`PricingCard`, `ServiceCard`); "Panel" = an expandable/collapsible section (`PricingDetailsPanel`); "Blocks" = a set of related sub-pieces rendered together (`LegalContentBlocks`). Pick the one that matches the new component's actual behavior rather than defaulting to "Card" for everything.

Several of these rules are backed by an ESLint warning (hardcoded hex colors, `text-[10px]` regressing back in, inline `style={{}}`) — see `frontend/craco.config.js` and DESIGN_SYSTEM_AUDIT.md §6 for what's mechanically enforced vs. what relies on code review. The reasoning behind these architectural choices (why Tailwind, why shadcn, when to extend vs. create new) is in FOUNDING_ENGINEER_PLAYBOOK.md §14 (Architecture Decision Records).

---

## 9. Page Templates

### 9.1 Marketing Page Template

```
<Navbar />
<Hero section />
<Content sections (2–5 sections) />
<CTA section />
<Footer />
```

**Examples:** Landing, Pricing page, Features page

### 9.2 Authentication Page Template

```
<Navbar />
<PageContainer>
  <PageHeader title="..." description="..." />
  <Form />
  <SignupLink / LoginLink />
</PageContainer>
```

**Examples:** Login, Register, Vendor Signup

### 9.3 Dashboard Page Template

```
<AppLayout>
  <PageContainer>
    <PageHeader title="..." />
    <DashboardHero (optional) />
    <MetricsGrid (optional) />
    <Content sections (cards, lists, forms) />
  </PageContainer>
</AppLayout>
```

**Examples:** Dashboard, Orders, Wallet, Profile

### 9.4 Admin Panel Template

```
<AppLayout>
  <PageContainer>
    <PageHeader title="..." description="..." />
    <FilterBar />
    <DataTable />
  </PageContainer>
</AppLayout>
```

**Examples:** Users, Vendors, Reconciliation, Audit Log

---

## 10. Navigation System

### 10.1 Navbar (Marketing & Auth)

**Structure:**
- Logo (left)
- Nav links (center, hidden on mobile)
- Auth buttons (right)

**States:**
- Default: white background, navy text
- Scrolled: subtle shadow, backdrop blur
- Mobile: hamburger menu, drawer nav

### 10.2 AppNav (Authenticated)

**Structure:**
- Sidebar (left, collapsible on mobile)
- Topbar (full-width header)

**Sidebar:**
- Logo (top)
- Role-based nav items
- Subscription card (bottom)
- Collapsible on mobile

**Topbar:**
- Welcome message (left)
- Wallet balance (center-right, hidden on mobile)
- Notifications (right)
- User menu (far right)

---

## 11. Workflow Components

### 11.1 Multi-Step Workflows (Order, Onboarding)

**Structure:**
- Step indicator (breadcrumb or progress)
- Current step form
- Step navigation (previous, next, skip)
- Progress indication

**States:**
- Not started: disabled
- Current: active, editable
- Completed: done, review-able
- Skipped: optional steps

### 11.2 Order Timeline

**Visualization:**
- Vertical timeline (default)
- Horizontal timeline on mobile (scroll)
- Status badges (pending, in-progress, completed, failed)
- Time estimates / actual times

---

## 12. Dashboard System

### 12.1 Dashboard Shells by Role

#### Advocate Dashboard
- Quick actions (new order, marketplace, courts)
- Active orders
- Recent orders
- Wallet balance
- Upgrade prompt

#### Vendor Dashboard
- Order queue
- Earnings summary
- SLA score
- Active deliveries
- Settlement status

#### Admin Dashboard
- Command center (revenue metrics)
- Revenue breakdown
- Top services
- Pending approvals
- Recent orders

### 12.2 Consistent Patterns

**Hero section:** configurable CTA + optional image
**Metrics grid:** stat tiles with icon + label + value
**Quick actions:** service/action cards in grid
**Activity feed:** timeline of events

---

## 13. Responsive Rules

### 13.1 Breakpoints (Mobile-First)

```
base:      0px    (mobile)
sm:        640px  (landscape mobile / small tablet)
md:        768px  (NOT USED — gap too small)
lg:        1024px (tablet / small desktop)
xl:        1280px (desktop)
2xl:       1536px (large desktop)
```

**Apply only `sm:` and `lg:` consistently.**

### 13.2 Responsive Patterns

**Single column to grid:**
```jsx
<Grid cols="1 sm:2 lg:4"> — 1 col mobile, 2 tablet, 4 desktop
```

**Hide on mobile:**
```jsx
<div className="hidden sm:block"> — hidden mobile, shown tablet+
```

**Adjust spacing:**
```jsx
<div className="p-4 sm:p-6 lg:p-8"> — 16px → 24px → 32px
```

**Adjust font:**
```jsx
<h1 className="text-3xl sm:text-4xl lg:text-5xl"> — scale with viewport
```

### 13.3 Touch-Friendly Sizing

- Minimum tap target: 44x44px
- Buttons: `h-10` (40px) minimum
- Spacing between buttons: `gap-2` (8px) minimum
- Form inputs: `h-10` (40px) minimum

---

## 14. Accessibility

### 14.1 Semantic HTML

- Use `<button>` for buttons, not `<div>`
- Use `<nav>`, `<main>`, `<footer>` for landmarks
- Use `<table>` for tabular data
- Use `<form>` for forms

### 14.2 ARIA Attributes

- Add `aria-label` for icon-only buttons
- Add `aria-describedby` for form field hints
- Add `aria-live` for toast notifications
- Add `aria-hidden` for decorative icons

### 14.3 Color & Contrast

- Text contrast: 4.5:1 for normal text, 3:1 for large text
- Don't rely on color alone (status badges need icons too)
- Test with Contrast Checker

### 14.4 Keyboard Navigation

- Tab order is logical (top to bottom, left to right)
- Modals trap focus
- Close button always available (Escape key)
- Arrow keys work in dropdowns, tabs, etc.

### 14.5 Screen Reader Support

- Form labels are associated with inputs
- Table headers use `<th>`
- Skip navigation link available
- Status updates announced via `aria-live`

---

## 15. Animation Rules

### 15.1 Transitions

**Default:** 200ms ease-in-out for all interactive elements

```css
transition-all duration-200 ease-in-out
```

**Entrance:** 300ms ease-out (elements entering viewport)
**Exit:** 150ms ease-in (elements leaving viewport)

### 15.2 Animations

- Hover: 200ms color/shadow change
- Pulse: 1.5s infinite (live indicators)
- Shimmer: 2s infinite (loading states)
- Bounce: brief feedback on click (button)

### 15.3 Motion Preferences

- Respect `prefers-reduced-motion`
- Disable animations for users who opt-in
- Animations enhance, not replace, feedback

---

## 16. Folder Structure

### 16.1 Current actual structure (as of 2026-07-15)

```
src/
├── components/
│   ├── ui/              # shadcn primitives — 20 files, all live (§3, §8)
│   ├── landing/          # marketing page sections (HeroSection, ServiceCard, LandingNav, ...)
│   │   ├── join/         # "Join as..." multi-step lead forms (RoleForm, FieldKit, Combobox, ...)
│   │   └── pricing/      # /pricing page components (PricingPackageCard, PricingComparisonTable, ...)
│   ├── layout/           # AppLayout.jsx — the one authenticated-app shell
│   ├── legal/            # LegalPageLayout, Breadcrumb, LegalSearchPalette, ...
│   ├── shared/           # ComingSoonBadge, MapView — genuinely cross-cutting pieces
│   └── ScrollToTop.jsx
├── pages/                # ~40+ page files (marketing/, auth/, customer/, vendor/, admin/, delivery/, legal/)
├── lib/
│   ├── tokens.js         # complete but orphaned — zero imports (§4)
│   └── utils.js
└── styles/
    ├── index.css         # real token source (:root CSS vars) + informal utility classes
    ├── landing.css
    └── legal.css
```

There is **no** `components/cards/`, `components/forms/`, or `components/dashboard/` folder — dashboard/admin/vendor/delivery pages build all their UI directly in `pages/*` using `ui/*` primitives. New reusable domain components (StatTile, PageContainer, DataTable, etc., per §3/§8) should go in `components/design-system/` per the target layout below, or in a new `components/dashboard/` if they're dashboard-specific — pick the target structure in §16.2 when creating new shared components, don't invent a third convention.

### 16.2 Target structure (not yet built — the destination for new design-system components)

```
src/
├── components/
│   ├── ui/                     # Primitive components (shadcn)
│   │   ├── button.jsx
│   │   ├── card.jsx
│   │   ├── input.jsx
│   │   └── ... (40+ shadcn components)
│   │
│   ├── design-system/          # Design system components
│   │   ├── layout/             # Layout helpers
│   │   │   ├── PageContainer.jsx
│   │   │   ├── Stack.jsx
│   │   │   ├── Cluster.jsx
│   │   │   ├── Section.jsx
│   │   │   └── Grid.jsx
│   │   │
│   │   ├── typography/         # Text components
│   │   │   ├── PageTitle.jsx
│   │   │   ├── SectionTitle.jsx
│   │   │   ├── Heading.jsx
│   │   │   ├── Body.jsx
│   │   │   └── Label.jsx
│   │   │
│   │   ├── content/            # Content components
│   │   │   ├── StatTile.jsx
│   │   │   ├── MetricsGrid.jsx
│   │   │   ├── EmptyState.jsx
│   │   │   ├── LoadingState.jsx
│   │   │   ├── ErrorState.jsx
│   │   │   ├── Badge.jsx
│   │   │   ├── Tag.jsx
│   │   │   └── Pill.jsx
│   │   │
│   │   ├── forms/              # Form components
│   │   │   ├── FormField.jsx
│   │   │   ├── FormSection.jsx
│   │   │   ├── FormActions.jsx
│   │   │   ├── FileUpload.jsx
│   │   │   ├── DateField.jsx
│   │   │   ├── SelectField.jsx
│   │   │   └── OTPInput.jsx
│   │   │
│   │   ├── table/              # Table components
│   │   │   ├── DataTable.jsx
│   │   │   ├── DataRow.jsx
│   │   │   ├── DataCell.jsx
│   │   │   ├── FilterBar.jsx
│   │   │   └── Pagination.jsx
│   │   │
│   │   ├── dashboard/          # Dashboard components
│   │   │   ├── DashboardHero.jsx
│   │   │   ├── QuickActionsGrid.jsx
│   │   │   ├── ActivityFeed.jsx
│   │   │   ├── OrderCard.jsx
│   │   │   └── VendorCard.jsx
│   │   │
│   │   └── feedback/           # Feedback components
│   │       ├── Alert.jsx
│   │       ├── Toast.jsx
│   │       ├── ConfirmationDialog.jsx
│   │       └── Skeleton.jsx
│   │
│   ├── layout/                 # Layout wrappers
│   │   ├── Navbar.jsx          # Marketing nav
│   │   ├── AppLayout.jsx       # App shell (sidebar + topbar)
│   │   ├── Topbar.jsx
│   │   ├── Sidebar.jsx
│   │   └── Footer.jsx
│   │
│   └── sections/               # Page sections (reusable)
│       ├── landing/
│       │   ├── HeroSection.jsx
│       │   ├── ServiceGrid.jsx
│       │   ├── WorkflowSteps.jsx
│       │   ├── CoverageSection.jsx
│       │   ├── TrustSection.jsx
│       │   ├── TestimonialCards.jsx
│       │   ├── PricingCards.jsx
│       │   ├── FAQAccordion.jsx
│       │   └── CTASection.jsx
│       └── ...
│
├── pages/                      # Page components
│   ├── Landing.jsx             # Composes sections
│   ├── Login.jsx
│   ├── Register.jsx
│   ├── Dashboard.jsx
│   ├── Orders.jsx
│   ├── VendorDashboard.jsx
│   ├── AdminDashboard.jsx
│   └── ...
│
├── hooks/                      # Custom hooks
│   ├── useAuth.js
│   ├── useApi.js
│   ├── useForm.js
│   └── ...
│
├── lib/                        # Utilities & helpers
│   ├── api.js
│   ├── tokens.js               # Design tokens (JS exports)
│   ├── constants.js
│   └── utils.js
│
├── styles/                     # Global styles
│   ├── index.css               # Tailwind + design system tokens
│   ├── animations.css          # Shared animations
│   └── utilities.css           # Custom utilities (minimal)
│
└── App.jsx                     # Root component
```

---

## 17. Implementation Roadmap

Status as of 2026-07-15 — see DESIGN_SYSTEM_AUDIT.md §5 for the prioritized, deduplicated version of this list; phases below are kept for historical context on what was planned vs. what actually landed.

### Phase 1: Design System Foundation — not started
- [ ] Create design system components directory structure (§16.2)
- [ ] Implement layout components: `PageContainer`, `Stack`, `Cluster`, `Grid`, `Section`
- [ ] Implement typography components: `PageTitle`, `SectionTitle`, `Heading`, `Body`, `Label`
- [ ] Implement content components: `StatTile`, `MetricsGrid`, `EmptyState`, `LoadingState`
- [ ] Wire up (or remove) `lib/tokens.js`
- [ ] Verify all components work with both light mode and dark mode (CSS variables)

### Phase 2: Landing Page — ✅ done
- [x] Extract landing sections: `HeroSection`, `ServiceCard`/`FeaturedServiceCard`, `CoverageSection`, `ReviewsSection`, `PricingSection`, `LandingFooter`, `ProductTour` all exist as real components in `components/landing/`
- [x] Refactor `Landing.jsx` to compose sections only — confirmed, `Landing.jsx` is now composition + data constants, not markup
- [ ] Still open: pricing/service cards are 🔀 duplicated across `landing/`, `landing/pricing/` rather than fully shared (§3.3); other marketing pages (`About`, `Contact`, `Pricing`, `Security`, `Trust`) still repeat the Nav+Footer shell by hand instead of sharing a `MarketingLayout`

### Phase 3: Dashboard Templates — not started
- [ ] Implement form components: `FormField`, `FormSection`, `FormActions` (generic, outside the join-form engine — see §3.4 for what already exists there)
- [ ] Implement dashboard components: `DashboardHero`, `QuickActionsGrid`, `ActivityFeed`, `OrderCard`
- [ ] Refactor `Dashboard.jsx`/`AdminDashboard.jsx`/`VendorDashboard.jsx` to share a `PageContainer` at minimum, dashboard components ideally
- [ ] Test quick actions, metrics, and activity displays

### Phase 4: Admin & Data Tables — not started
- [ ] Implement table components: `DataTable`, `DataRow`, `DataCell`, `FilterBar`, `Pagination`
- [ ] Refactor admin pages: Users, Vendors, Reconciliation, Audit Log
- [ ] Implement list patterns for Orders, Marketplace
- [ ] Test filtering, sorting, pagination

---

## Glossary

**Design Token:** A semantic variable (color, spacing, shadow) that represents a design decision
**Component:** Reusable React component built from design tokens
**Section:** Larger composition of components (used on landing page)
**Template:** Page layout pattern (dashboard, admin, auth)
**Variant:** Component style option (size, color, state) managed by CVA
**Build status legend:** ✅ built & live · ⚠️ built but orphaned/unwired · ❌ not built · 🔀 built more than once, needs consolidating — used throughout §3 and §8

---

## Next Steps

1. ✅ Design principles, tokens, sitemap, and shared-components list are documented (above)
2. ✅ Phase 2 (Landing Page componentization) is done
3. **→ Phase 1 (Design System Foundation)** — start here; `PageContainer` and wiring up `lib/tokens.js` unblock everything else
4. **→ Phase 3–4 (Dashboards, Admin & Data Tables)** — blocked on Phase 1's layout primitives

All work follows this design system. Any new component must fit within the structure above (§16) or be added to this document first — see §8.4 for the specific Do/Don't rules and DESIGN_SYSTEM_AUDIT.md for the live priority-ordered punch list.

