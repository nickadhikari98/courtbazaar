# Negotiation Module: notify the counsel, and show them what they need to respond

## Context

While manually testing PR #3's reconciled recommendation flow end-to-end (create a Hire Proxy Counsel request → select a counsel → land on the Negotiation page), two things surfaced:

1. You asked for a way to directly agree to the counsel's price. That "Accept" mechanism **already exists** and is fully implemented (`backend/negotiation.py::accept_offer`, wired through `NegotiationOfferPanel.jsx`'s "Accept ₹X" button) — it was just correctly hidden in the screenshot you saw, because the active offer at that moment was the one *you* had proposed, and the backend explicitly disallows accepting your own offer (`accept_offer` raises 403 on self-accept — that's an intentional business rule, not a bug).
2. You asked me to check whether the counsel got notified about being requested. **They did not.** I traced this to a real gap: `backend/server.py`'s `create_hearing_request` endpoint has a comment — *"M6 reorder: no notify-the-target-advocate here anymore... that's where this notification now fires"* — pointing at `verify_hearing_payment`. That comment predates the Negotiation Module (PR #11). Today, a targeted hearing requires negotiation to be **agreed** before payment can even start (`hearings.initiate_payment` blocks on it), so by the time that leftover notification fires, the negotiation is long since over — the "New hearing request" notification arrives *after* the deal is already done, not when the counsel actually needs to see it. In between, the counsel has zero proactive signal that a request or any offer/counter-offer is waiting on them; they'd only find out by happening to check "My Requests"/Practice manually.

I also found a related, smaller gap while looking at this: `NegotiationModule.jsx` only has the counsel's profile (name, rating, reference fee, etc.) via React Router navigation state (`location.state?.counsel`) — there's no API to fetch it. So refreshing the page, or opening a direct/shared link to a negotiation (exactly what happened when you navigated straight to the URL), shows a placeholder instead of the counsel's reference fee — which is exactly the "concrete number to agree to" you were looking for on that screen.

None of this is on develop/main yet — it's additive, scoped to the Negotiation Module (`negotiation.py`, the hearing-creation notification, and one new small profile-lookup endpoint), and continues on the same `feature/proxy-counsel-ai-recommendation` branch already open as PR #3.

## Plan

### 1. Notify the counsel when they're actually targeted (not at payment time)

**File:** `backend/server.py`, `create_hearing_request` (~line 2403)

Add a call to the existing `_notify_hearing_event` helper (already defined right above this endpoint, already used the same way at 4 other call sites — no new notification plumbing needed) when `payload.target_advocate_id` is set, right after `hearings_svc.create_hearing_request(...)` returns. Message: "New hearing request" / "You've been requested for a hearing at {court}. Open Negotiation to respond." — reusing the same copy style as the existing call at line 2512.

**File:** `backend/server.py`, `verify_hearing_payment` (~line 2511-2514)

The existing `_notify_hearing_event(..., "New hearing request", ...)` call here fires *after* negotiation is already agreed and payment is confirmed — for a targeted hearing that's a stale/misleading message at this point. Change its copy to reflect what's actually happened: "Payment received" / "Payment for your hearing at {court} is confirmed and held in escrow." Scope stays exactly what it is today (only fires when `target_advocate_id` is set; broadcast hearings are handled separately by `counsel_matching`'s own dispatch, untouched).

### 2. Notify both parties on negotiation events

**File:** `backend/negotiation.py`

`propose_offer` and `accept_offer` currently only write to the negotiation's own `timeline` — no one is notified in real time; the only way to see a new offer today is to have the page open and let `useNegotiationPoll` catch it on its next tick, or come back later. Add notification calls following the exact pattern `counsel_matching.dispatch_notifications` already uses (`from notifications import notify, record_notification_event`, lazy-imported, same as this file already does for `hearings`):

- `propose_offer`: after the offer is persisted, notify the *other* participant (`requesting_user_id` if the proposer was the counsel, `target_advocate_id` if the proposer was the customer) — "New offer" / "Counter offer" with the amount.
- `accept_offer`: after the negotiation flips to "agreed", notify the party who did *not* accept — "Offer accepted — {amount} agreed. " + (payment-now-available for the customer / waiting-for-payment for the counsel).

Keep this best-effort/non-fatal the same way every other notify call site in this codebase already is (`_notify_hearing_event`'s try/except, `dispatch_notifications`'s per-entry try/except) — a notification failure must never block the actual offer/accept action.

### 3. Let the Negotiation page show the counsel's reference fee without relying on router state

**File:** `backend/server.py` — new endpoint, e.g. `GET /hearing-requests/{hearing_id}/counsel-profile`, scoped to participants of that hearing (reuse `negotiation._check_negotiation_participant`-style guard or `hearings.get_hearing_request`'s existing visibility check). Returns the same shape `recommendations_advocates` already builds per-candidate (name, rating, primary_courts, practice_areas, `proposed_fee` via `counsel_matching.extract_fee_amount`, `verified: true`) for the hearing's `target_advocate_id`, reusing that existing mapping logic rather than duplicating it.

**File:** `frontend/src/lib/hearingRequestsApi.js` (or `negotiationApi.js`, wherever the other hearing-scoped calls live) — add the client function.

**File:** `frontend/src/pages/customer/NegotiationModule.jsx` — when `location.state?.counsel` is absent (refresh, direct link), fall back to fetching this new endpoint by `hearing.target_advocate_id` instead of showing the placeholder. Keep the router-state path as the fast/no-round-trip default when it's present (per the existing comment's own reasoning) — this is purely a fallback, not a replacement.

## Sequencing

1 and 2 first (backend-only, no frontend changes, directly close the "counsel never finds out" gap you asked about).
3 next (one small new endpoint + a fallback fetch) — it's what actually surfaces a concrete number on that screen to negotiate against/agree to.

## Verification

- Backend: extend `backend/tests/test_recommendations.py` or add a `test_negotiation.py`-adjacent test asserting `notification_events` gets a row for the target advocate on hearing creation, and for the counter-party on `propose_offer`/`accept_offer` — following the existing tests' plain-`asyncio.run` + real-db + cleanup-in-`finally` pattern already used throughout this test suite.
- Manual, using the already-running local backend/frontend and the seeded QA counsel (`test_demo_counsel_001`) and Shobhini's real account: create a targeted hearing, confirm a `notification_events` row appears for the counsel immediately (not just after payment); propose/counter/accept offers from both sides and confirm each step produces a notification for the other party; hard-refresh the Negotiation page and confirm the counsel's reference fee now renders instead of the placeholder.
