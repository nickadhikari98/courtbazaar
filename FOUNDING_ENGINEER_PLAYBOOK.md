# CourtBazaar Founding Engineer Playbook

This playbook is the operating guide for building and shipping CourtBazaar as a lean, high-velocity founding team. It is meant to be practical: clear enough for a new contributor to follow, and strict enough to keep the product reliable.

---

## 1. Project philosophy

CourtBazaar is a legal-ops and court-services marketplace for India. The core product loop is simple:

1. A user selects a legal service.
2. They choose a court and delivery preference.
3. The system matches a vendor.
4. The order is tracked through fulfillment.
5. Payments, notifications, and admin operations complete the loop.

Our default philosophy is:

- Build for the Delhi MVP first.
- Favor clear user value over broad feature scope.
- Keep the core flow reliable before expanding the platform.
- Make changes small, testable, and reversible.
- Treat launch quality as a product requirement, not an afterthought.

---

## 2. First-day checklist

When you join or start a new sprint, do this first:

- Read the product brief in [memory/PRD.md](memory/PRD.md).
- Review the repository layout below.
- Confirm local backend and frontend dependencies are installed.
- Confirm MongoDB is reachable.
- Run the backend and frontend locally once to verify the baseline.
- Pick a single small task and understand the end-to-end user path before coding.

---

## 3. Product mental model

Think about CourtBazaar in three layers:

- Customer experience: what the advocate, vendor, or admin sees.
- Operations layer: how orders, payments, notifications, and approvals flow.
- Platform layer: how data, auth, and integrations are wired together.

If a change affects one layer, check the others. For example, changing an order status flow may require updates to the UI, backend logic, notifications, and admin reporting.

---

## 4. Repository structure

At a high level:

- [backend](backend) — FastAPI backend, API routes, business logic, and integrations.
  - [backend/server.py](backend/server.py) — main FastAPI entrypoint.
  - [backend/requirements.txt](backend/requirements.txt) — Python dependencies.
  - [backend/tests](backend/tests) — backend test suite.
  - [backend/audit_log.py](backend/audit_log.py), [backend/notifications.py](backend/notifications.py), [backend/ocr_engine.py](backend/ocr_engine.py), [backend/razorpay_svc.py](backend/razorpay_svc.py), [backend/vendor_sla.py](backend/vendor_sla.py) — domain modules.
- [frontend](frontend) — React frontend.
  - [frontend/src/pages](frontend/src/pages) — page-level screens.
  - [frontend/src/components](frontend/src/components) — shared UI components. All colors, typography, spacing, and component variants follow [PRODUCT_DESIGN_SYSTEM.md](PRODUCT_DESIGN_SYSTEM.md) — that document, not this one, is the source of truth for UI decisions. Check [DESIGN_SYSTEM_AUDIT.md](DESIGN_SYSTEM_AUDIT.md) before assuming a documented component already exists.
  - [frontend/src/lib](frontend/src/lib) — API helpers and utilities.
  - [frontend/package.json](frontend/package.json) — scripts and dependency manifest.
- [memory](memory) — product requirements and planning artifacts.
  - [memory/PRD.md](memory/PRD.md) — product direction and roadmap.
- [tests](tests) — repo-level test hooks.
- [test_reports](test_reports) — historical verification reports.

Quick navigation guide:

- UI changes usually start in [frontend/src/pages](frontend/src/pages).
- Order flow, auth, payments, vendor matching, and admin logic usually start in [backend/server.py](backend/server.py) and the relevant backend module.
- Product intent lives in [memory/PRD.md](memory/PRD.md).

---

## 5. Local development setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB reachable on port 27017
- Optional: Tesseract for OCR-related flows

### Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Start the API:

```bash
cd backend
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

### Frontend setup

```bash
cd frontend
npm install
npm start
```

The frontend should be available at:

```text
http://localhost:3000
```

### Running MongoDB with Docker

If Docker is available, this is the fastest local setup:

```bash
docker run -d --name courtbazaar-mongo -p 27017:27017 mongo:7
```

Verify it is reachable:

```bash
docker ps
```

Expected local connection string:

```text
mongodb://localhost:27017
```

### Local sanity checklist

- Backend starts without crashing.
- Frontend starts without dependency issues.
- MongoDB is reachable.
- You can log in and reach the dashboard.
- A basic order can be created end to end.

---

## 6. Feature development workflow

Use this workflow for almost every feature.

1. Start from the user need.
   - Who is the user?
   - What problem are we solving?
   - What is the smallest useful version?

2. Define the behavior.
   - Write down the happy path and the main edge case.
   - Prefer a clear backend contract first.

3. Build backend logic first.
   - Add or update tests.
   - Implement the behavior.
   - Keep it isolated and easy to reason about.

4. Wire the frontend.
   - Connect the UI to the new backend behavior.
   - Keep the user flow simple and consistent.

5. Verify manually.
   - Smoke test the feature end to end.
   - Confirm there are no regressions in adjacent flows.

Avoid mixing unrelated changes in one PR. A single PR should ideally do one thing well.

---

## 7. Git branching strategy

Use a simple branch model.

### Branch types

- main — protected and always releasable.
- feature/<short-name> — new product work.
- fix/<short-name> — bug fixes.
- hotfix/<short-name> — urgent production issues.
- chore/<short-name> — tooling, dependency, or maintenance updates.

### Branch rules

- Branch from main.
- Keep branches short-lived.
- Sync with main regularly.
- Do not merge without a PR and review.
- Do not leave a branch behind if the work is complete.

### Example names

- feature/delhi-order-flow
- feature/vendor-approval-ui
- fix/payment-status-bug
- hotfix/auth-token-expiry

---

## 8. Pull request guidelines

Every PR should be easy to review and easy to ship.

### Required PR contents

- A short summary of the change.
- Why the change is needed.
- What was tested locally.
- Any migration, environment, or deployment note.
- Screenshots or a short video if the UI changed.

### Review checklist

- The change matches the stated goal.
- The scope is reasonable.
- Tests were added or updated where needed.
- No obvious security or data-handling issues were introduced.
- The change does not break the main happy path.

---

## 9. Testing strategy

CourtBazaar should be tested at three levels.

### 1. Backend tests

```bash
cd backend
pytest
```

For a focused run:

```bash
cd backend
pytest tests/test_courtbazaar_api.py -q
```

### 2. Frontend checks

```bash
cd frontend
npm test -- --watch=false
```

### 3. Manual smoke tests

For every feature, verify:

- Register or log in.
- Create a sample order.
- Verify the court selection behavior.
- Confirm the vendor matching or approval flow.
- Verify payment and order status updates.
- Review relevant admin screens.

If a feature changes the core order journey, test that journey end to end before calling it done.

---

## 10. Deployment to the Hostinger VPS

Deployment, rollback, environment variables, Nginx/systemd config, and the pre-deploy checklist are fully documented in [DEPLOYMENT.md](DEPLOYMENT.md) — that document owns this topic; don't duplicate its steps here. The short version: `git pull`, reinstall/rebuild both sides, restart the systemd unit, reload Nginx. See DEPLOYMENT.md for the actual commands and the environment variable checklist.

For local development (not production), see §5 above.

---

## 11. Delhi MVP roadmap

The Delhi MVP should be treated as a launchable slice, not a perfect version of the full platform. This is the engineering-facing summary; deeper product rationale and detail live in [memory/PRD.md](memory/PRD.md).

### Phase 1 — Foundation

- Finalize auth and role handling.
- Ensure Delhi courts are serviceable.
- Build the core order flow.
- Add basic vendor matching.
- Make the dashboard usable for advocates and admins.

### Phase 2 — Trust and conversion

- Add payment handling.
- Add notifications for key lifecycle events.
- Improve admin visibility for orders and vendors.
- Add basic vendor approval and KYC flow.

### Phase 3 — Launch readiness

- Test the full Delhi journey end to end.
- Validate data quality for courts, services, and vendors.
- Add basic monitoring and error handling.
- Prepare internal support and escalation playbooks.

### Phase 4 — Soft launch

- Open the product to a small set of Delhi users.
- Monitor conversion, failures, and support issues.
- Fix the highest-friction issues quickly.
- Expand only after the experience is stable.

### Delhi MVP definition of done

The Delhi MVP is ready when:

- Delhi users can create orders successfully.
- Vendors can be matched and notified.
- Payments and order status updates work.
- Admins can approve vendors and inspect orders.
- The experience is stable enough for a real first wave of users.

---

## 12. Coding standards

Keep the codebase easy to read and easy to maintain.

- Write clear, descriptive names.
- Keep functions focused and small.
- Prefer straightforward logic over clever abstractions.
- Add comments only where they help explain intent.
- Avoid duplicating logic across frontend and backend when it can be centralized.
- Keep user-facing copy clear and concise.

---

## 13. Architecture principles

Follow these rules as the system grows:

- Keep the backend the source of truth for business rules.
- Keep the frontend thin and focused on user interaction.
- Prefer simple integrations over over-engineered infrastructure.
- Make failures visible and understandable.
- Keep data flow explicit and testable.
- Use environment variables for secrets and deployment-specific config.
- Frontend UI decisions (colors, spacing, typography, component variants) follow [PRODUCT_DESIGN_SYSTEM.md](PRODUCT_DESIGN_SYSTEM.md) — don't invent a new color, spacing value, or card/button style ad hoc; extend or add to that document first.

---

## 14. Architecture Decision Records (ADRs)

Short records of *why*, not just *what*, for the decisions most likely to confuse a new engineer or get silently relitigated. Update this section when a decision below changes or a new one is worth recording — don't let it go stale.

### ADR-1: Tailwind CSS for styling

**Decision:** Tailwind utility classes, not CSS-in-JS or hand-written CSS modules, for nearly all styling.

**Why:** Utility classes keep styling co-located with markup, so a component's visual behavior is readable in one place instead of split across a JSX file and a separate stylesheet. Tailwind's config (`tailwind.config.js`) also gives us one place to define the color/spacing/radius/shadow scale that every class ultimately reads from — see PRODUCT_DESIGN_SYSTEM.md §4.

**What this doesn't mean:** a handful of custom CSS files (`styles/landing.css`, `styles/legal.css`) and hand-authored utility classes in `index.css` (`.bento-card`, `.cb-overline`, etc.) still exist for patterns that don't fit cleanly into single utility classes — box-shadow recipes, gradient textures. That's fine; Tailwind doesn't need to own 100% of styling, just the default.

### ADR-2: shadcn/ui as the primitive layer

**Decision:** `components/ui/*` are shadcn-style primitives (Radix UI underneath, styled with Tailwind + `class-variance-authority`), not a third-party component library imported as a black box, and not hand-rolled from scratch.

**Why:** shadcn primitives are copied into the repo as source, not installed as an opaque dependency — we own and can modify every line. Radix underneath handles the genuinely hard parts (focus trapping, keyboard nav, ARIA) that are easy to get subtly wrong by hand. `class-variance-authority` (CVA) gives every primitive a consistent `variant`/`size` prop API instead of each component inventing its own.

**How this should be used:** before building a new interactive primitive (a new kind of dropdown, a new modal pattern), check whether shadcn already has it — see PRODUCT_DESIGN_SYSTEM.md §3.1-3.9 for what's already built vs. missing. Don't hand-roll something Radix already solved.

### ADR-3: Reusable primitives over page-specific components

**Decision:** shared layout/UI concerns (page containers, marketing page shells, table markup) belong in `components/`, not copy-pasted per page.

**Why:** this codebase's biggest source of design drift historically wasn't bad taste, it was the same literal Tailwind string (`p-6 lg:p-10 max-w-7xl mx-auto`, a full marketing-page Nav+Footer shell) getting hand-copied into 3-6 files. Every copy is a place a future edit can be applied inconsistently. See DESIGN_SYSTEM_AUDIT.md for the specific instances this caused and PRODUCT_DESIGN_SYSTEM.md §3.2 for the `PageContainer`/`MarketingLayout` primitives that replaced them.

**The counter-principle, equally important:** don't force two genuinely different things into one shared component just because they're superficially similar. `ServiceCard` and `FeaturedServiceCard` look like they could be "the same card," but one's a small grid tile and the other's a two-layout-mode flagship promo unit — merging them would recreate the duplication *inside* one file instead of removing it. See PRODUCT_DESIGN_SYSTEM.md §3.3 for that specific call and the reasoning.

### ADR-4: Centralized design tokens

**Decision:** one token source — `tailwind.config.js` (theme/extend) plus the CSS variables in `index.css`. Not a separate JS constants file re-declaring the same values.

**Why:** this codebase had exactly that second file (`lib/tokens.js`) for a while — fully written, fairly well-designed, and imported by zero components, because Tailwind classes (not JS imports) are how styling actually gets applied here. A token that isn't in the file components actually read from isn't a source of truth, it's a decoy. Deleted 2026-07-15 — see DESIGN_SYSTEM_AUDIT.md §2.A.

**How to add a new token:** add it to `tailwind.config.js` `theme.extend` (or a CSS variable in `index.css` if it needs to be theme-switchable), document it in PRODUCT_DESIGN_SYSTEM.md §4, then use the resulting Tailwind class. Don't add a parallel JS export "for convenience" — if something genuinely needs the raw value in JS (not just a className), read it via `getComputedStyle` against the CSS variable.

### ADR-5: How to introduce a new component

1. Check PRODUCT_DESIGN_SYSTEM.md §3 and §8 — does something close enough already exist? Extending an existing component's props is almost always better than a new one (see ADR-3's counter-principle for when it isn't).
2. Check `components/ui/*` for a shadcn primitive that solves the interactive/accessibility part (ADR-2).
3. Build it under the folder that matches its scope — `components/ui/` for a generic primitive, `components/layout/` for a shell/wrapper, `components/landing/`, `components/legal/`, etc. for a domain-specific piece. See PRODUCT_DESIGN_SYSTEM.md §16.1 for the current real folder layout.
4. Document it in PRODUCT_DESIGN_SYSTEM.md §3/§8 — purpose, variants, when to use it — before (or alongside) writing the code, not after it's already spread across five pages copy-pasted.

### ADR-6: When to extend vs. create new

Extend an existing component when the difference is a **prop-driven variant** — a size, a color, a boolean flag, a slot for optional content. That's what `PricingCard`'s `variant="teaser"|"full"` is (ADR-3 / PRODUCT_DESIGN_SYSTEM.md §3.3): two contexts for fundamentally the same card.

Create a new component when the difference is **structural** — different DOM shape, different layout modes, different interaction model. Forcing a structural difference into one component with a growing pile of conditional branches doesn't reduce duplication, it just hides it inside one file (see `ServiceCard` vs. `FeaturedServiceCard` in ADR-3 again — the honest call was two components, not one with a `size="huge"` prop).

If you're not sure which side of that line something is on, prototype the "merged" version first: if it needs more than 2-3 top-level conditional branches to cover both cases, it's probably two components.

### ADR-7: Route-level code splitting, not component-level

**Decision:** every page component imported in `App.js`'s route table is `React.lazy()`-loaded, wrapped in one `Suspense` boundary around `<Routes>`. Shared layout (`AppLayout`) and tiny UI primitives are not lazy-loaded.

**Why:** this app's bundle was ~643KB gzipped, shipped in full to every visitor regardless of which single page they came for — a marketing visitor downloaded the entire admin console and vendor dashboard along with the landing page. Splitting at the route boundary is the natural unit: a route is already the point where the user has committed to a specific page, so a brief chunk fetch there is the right trade. Splitting `AppLayout` or a `ui/` primitive separately would add chunk-fetch overhead for something every authenticated page needs anyway, with no download ever avoided. Cut the main bundle to ~147KB gzipped (see DESIGN_SYSTEM_AUDIT.md §9.3).

**How to add a new page:** add it to `App.js` as `const NewPage = lazy(() => import("@/pages/.../NewPage"));` following the existing pattern, not a static `import`. It'll automatically render through the existing `Suspense` fallback — no per-route Suspense boundary needed.

---

## 15. Definition of Done

A piece of work is done when:

- The intended user outcome is achieved.
- The happy path works locally.
- Relevant tests pass.
- Edge cases are handled gracefully.
- The change does not break the adjacent core flow.
- The PR description is complete and review-ready.

---

## 16. Common troubleshooting

### Frontend fails to start

- Delete the local install cache and reinstall dependencies.
- Check whether the right Node version is installed.
- Confirm there is no conflicting local package lock or stale install state.

### Backend fails to connect to MongoDB

- Confirm MongoDB is running.
- Verify the connection string.
- Check firewall or container networking if using Docker.

### API returns unexpected errors

- Check the backend logs.
- Confirm the request payload matches the expected shape.
- Verify whether the issue is a validation error, auth issue, or integration failure.

### Deployment looks broken

See [DEPLOYMENT.md](DEPLOYMENT.md) §8 for the rollback procedure. Quick checks: server logs, environment variables present, backend service running, frontend build deployed correctly.

---

## 17. Command cheat sheet

Local development only — for VPS deployment commands, see [DEPLOYMENT.md](DEPLOYMENT.md).

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install
npm start

# MongoDB with Docker
docker run -d --name courtbazaar-mongo -p 27017:27017 mongo:7

# Tests
cd backend
pytest
```

This playbook should evolve with the product. Update it whenever the team changes process, architecture, or launch strategy.
