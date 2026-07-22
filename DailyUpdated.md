Counsel Matching & Assignment Agent — Implementation Roadmap v1.0

Converting the approved LLD into build order. 18 milestones across 6 phases, sequenced to isolate the one high-risk change (payment/broadcast reorder) from everything else, and to maximize parallel work.

---
Phase overview

┌───────┬───────────────────────────┬─────────────┬──────────────────┐
│ Phase │           Theme           │    Risk     │  Parallelizable  │
├───────┼───────────────────────────┼─────────────┼──────────────────┤
│ 0     │ Foundational/additive     │ Low         │ Yes — up to 5    │
│       │ changes                   │             │ devs             │
├───────┼───────────────────────────┼─────────────┼──────────────────┤
│       │ Payment reorder and       │ High (P1) / │ Yes — 2          │
│ 1+2   │ matching core,            │  Low (P2)   │ independent      │
│       │ concurrently              │             │ tracks           │
├───────┼───────────────────────────┼─────────────┼──────────────────┤
│ 3     │ Wire matching into the    │ Medium      │ No — join point  │
│       │ payment hook + acceptance │             │                  │
├───────┼───────────────────────────┼─────────────┼──────────────────┤
│ 4     │ Scheduler waterfall       │ Medium      │ Partial          │
├───────┼───────────────────────────┼─────────────┼──────────────────┤
│ 5     │ Admin escalation +        │ Low-Medium  │ Partial          │
│       │ auto-refund               │             │                  │
├───────┼───────────────────────────┼─────────────┼──────────────────┤
│ 6     │ Hardening                 │ Low         │ Yes              │
└───────┴───────────────────────────┴─────────────┴──────────────────┘

---
PHASE 0 — Foundational / Additive

M1 — Schema & Collections Bootstrap

Objective
Add every new field/collection the rest of the roadmap depends on, with
zero behavior change. Pure additive migration-free schema work (Mongo is
schemaless — existing docs simply lack the new fields until touched).
────────────────────────────────────────
Files
hearings.py (ensure_indexes), new indexes for counsel_matching_log
────────────────────────────────────────
New functions
ensure_indexes additions: compound index {status:1,
proxy_counsel_user_id:1, match_tier_deadline_at:1} on hearing_requests;
new indexes on counsel_matching_log (hearing_id, match_id)
────────────────────────────────────────
DB changes
New fields on hearing_requests (all optional, default absent):
practice_areas, urgent, match_id, match_tier, match_tier_deadline_at,
notified_counsel_ids, match_confidence, admin_grace_deadline_at,
cancel_reason. New field on proxy_counsel_profiles: bar_council_verified:
  bool = False (set at get_or_create_profile). New collection
counsel_matching_log (no schema enforcement, created on first insert).
────────────────────────────────────────
Dependencies
None
────────────────────────────────────────
Complexity
Easy

- Acceptance criteria: existing hearing/practice endpoints behave identically; new fields readable via .get(..., default) without errors; indexes visible via db.hearing_requests.index_information().
- Test cases: existing test_courtbazaar_api.py suite passes unchanged; new test confirms get_or_create_profile returns bar_council_verified: False for a fresh profile; index-existence assertion.

---
M2 — Escrow Deferred-Payee Support

┌──────────────┬──────────────────────────────────────────────────────┐
│              │                                                      │
├──────────────┼──────────────────────────────────────────────────────┤
│ Objective    │ Allow create_and_hold to hold funds before a payee   │
│              │ is known; add the deferred-assignment path.          │
├──────────────┼──────────────────────────────────────────────────────┤
│ Files        │ escrow.py                                            │
├──────────────┼──────────────────────────────────────────────────────┤
│ New          │ assign_payee(db, context_type, context_id,           │
│ functions    │ payee_user_id)                                       │
├──────────────┼──────────────────────────────────────────────────────┤
│ DB changes   │ escrow_transactions.payee_user_id becomes nullable   │
├──────────────┼──────────────────────────────────────────────────────┤
│ Dependencies │ None                                                 │
├──────────────┼──────────────────────────────────────────────────────┤
│ Complexity   │ Medium (touches money-handling code — needs careful  │
│              │ review)                                              │
└──────────────┴──────────────────────────────────────────────────────┘

- Acceptance criteria: create_and_hold(payee_user_id=None, ...) succeeds, stores payee_user_id: null, does not credit any wallet; assign_payee sets payee_user_id and credits wallet_held_balance exactly once; release()/refund() work correctly both when payee was set at creation (existing vendor-order-style callers, unaffected) and when set later via assign_payee; refund() on a never-assigned escrow doesn't touch any user's wallet.
- Test cases: create-hold with null payee → assert no wallet credit; assign_payee → assert credit fires once; double-call assign_payee → assert no double-credit (idempotency or explicit guard); refund() on unassigned escrow → no exception, no wallet mutation; existing escrow test paths (vendor/order context, if any) still pass unchanged.

---
M3 — Counsel KYC & Bar Council Verification (Admin)

Objective
Give admins a way to actually approve a proxy counsel — doesn't exist
today. Blocking prerequisite for any eligibility filtering.
────────────────────────────────────────
Files
practice.py, server.py
────────────────────────────────────────
New functions/endpoints
practice.py: approve_kyc(db, user_id), verify_bar_council(db, user_id).
server.py: PUT /admin/practice/{user_id}/approve-kyc, PUT
/admin/practice/{user_id}/verify-bar-council (admin-only, mirrors
/vendors/{vendor_id}/approve)
────────────────────────────────────────
DB changes
None beyond M1's bar_council_verified field
────────────────────────────────────────
Dependencies
M1
────────────────────────────────────────
Complexity
Easy

- Acceptance criteria: non-admin gets 403; admin call flips exactly the one targeted field; unrelated profile fields untouched; audit_log entry written (reuse log_audit, consistent with /vendors/{vendor_id}/approve convention — check whether that endpoint logs today and match it).
- Test cases: 403 for non-admin; 200 + field flip for admin; idempotent re-approval; approving a nonexistent user_id returns 404.

---
M4 — Notification Template: hearing_offer

┌──────────────┬──────────────────────────────────────────────────────┐
│              │                                                      │
├──────────────┼──────────────────────────────────────────────────────┤
│ Objective    │ Add the one new notification event type the matching │
│              │  agent needs to fan out offers.                      │
├──────────────┼──────────────────────────────────────────────────────┤
│ Files        │ notifications.py                                     │
├──────────────┼──────────────────────────────────────────────────────┤
│ New          │ tmpl_hearing_offer(counsel, hearing); extend         │
│ functions    │ notify()'s event dispatch with elif event ==         │
│              │ "hearing_offer"                                      │
├──────────────┼──────────────────────────────────────────────────────┤
│ DB changes   │ None                                                 │
├──────────────┼──────────────────────────────────────────────────────┤
│ Dependencies │ None                                                 │
├──────────────┼──────────────────────────────────────────────────────┤
│ Complexity   │ Easy                                                 │
└──────────────┴──────────────────────────────────────────────────────┘

- Acceptance criteria: notify(counsel, "hearing_offer", {"hearing": ...}) produces SMS/WhatsApp/email payloads following the exact same fail-soft/mocked-when-unconfigured contract as every other template in the file.
- Test cases: unit test asserting template renders with required hearing fields (court, date, fee); unconfigured-provider path logs "mocked" and doesn't raise (matches existing convention).

---
M5 — Practice Composite Score Function

Objective
Give the matching agent one function to source
rating/response-time/acceptance-rate/past-performance from, keeping
statistics logic in the counsel domain module (mirrors vendor_sla.py's
role for Vendor Allocation).
────────────────────────────────────────
Files
practice.py
────────────────────────────────────────
New functions
compute_match_score_inputs(db, user_id) -> dict returning {rating,
cases_completed, success_rate, avg_response_seconds, acceptance_rate}
────────────────────────────────────────
DB changes
None (reads proxy_counsel_profiles, professional_ratings; reads
counsel_matching_log for response/acceptance stats — returns neutral
defaults (e.g. None/0) until that collection has data, which is fine
since M1 created it empty)
────────────────────────────────────────
Dependencies
M1
────────────────────────────────────────
Complexity
Medium (aggregation logic)

- Acceptance criteria: function runs against a counsel with zero history without error, returning sane neutral defaults; runs correctly once counsel_matching_log has entries (verified again after M10 lands, as a follow-up regression check, not a hard gate here).
- Test cases: fresh counsel → neutral defaults, no exception; counsel with professional_ratings entries → correct average; (deferred) counsel with counsel_matching_log entries → correct response-time/acceptance-rate, re-tested after M10.

---
PHASE 1 — Critical Path: Payment/Broadcast Reorder

M6 — Reorder Hearing Payment/Broadcast Sequence

This is the single highest-risk milestone in the roadmap — isolate it, fully regression-test it, and ship it before any matching logic depends on it.

Objective
Implement the founder-approved reorder: requested → payment_pending →
confirm_payment → broadcast, with accepted auto-chaining straight to
documents_shared.
────────────────────────────────────────
Files
hearings.py, server.py (endpoint call-site adjustments), frontend companion
 required: HireProxyCounsel.jsx/HearingDetailDialog.jsx must move the
payment trigger to right after creation instead of after acceptance —
flagging this explicitly since shipping the backend reorder alone breaks
the existing UI flow
────────────────────────────────────────
New functions
None new — HEARING_TRANSITIONS table diff only (see LLD §9);
_CANCEL_REQUIRES_REFUND gains broadcast, accepted
────────────────────────────────────────
DB changes
None beyond M1
────────────────────────────────────────
Dependencies
M1 (needs practice_areas/urgent fields present for creation)
────────────────────────────────────────
Complexity
Hard — behavioral change to a well-tested state machine; requires full
regression pass

- Acceptance criteria: full existing hearing lifecycle (create → pay → broadcast → accept → documents → preparation → scheduled → completed → verification → payout → rating) still completes end-to-end with the new ordering; cancelling from broadcast or accepted now correctly triggers a refund; a request can no longer be accepted before payment is confirmed.
- Test cases: full happy-path integration test re-run against new order; cancel-from-broadcast triggers refund (new case, didn't exist before); cancel-from-accepted triggers refund; attempt-to-accept-before-payment returns IllegalTransition/400; existing targeted-request (target_advocate_id) path re-verified under new order.

---
PHASE 2 — Matching Core (runs in parallel with Phase 1)

Independent of M6 — operates on proxy_counsel_profiles/availability_slots, which already exist. A second developer/track can build this while Phase 1 is in review.

M7 — Eligibility & Availability Filtering

┌──────────────┬──────────────────────────────────────────────────────┐
│              │                                                      │
├──────────────┼──────────────────────────────────────────────────────┤
│ Objective    │ Build the hard-gate filtering logic.                 │
├──────────────┼──────────────────────────────────────────────────────┤
│ Files        │ counsel_matching.py (new file)                       │
├──────────────┼──────────────────────────────────────────────────────┤
│ New          │ get_eligible_counsels(db, court_id, practice_areas,  │
│ functions    │ hearing_date), filter_available(db, candidates,      │
│              │ court_id, hearing_date)                              │
├──────────────┼──────────────────────────────────────────────────────┤
│ DB changes   │ None                                                 │
├──────────────┼──────────────────────────────────────────────────────┤
│ Dependencies │ M1 (bar_council_verified field), M3 (need at least   │
│              │ one approved+verified counsel to test against)       │
├──────────────┼──────────────────────────────────────────────────────┤
│ Complexity   │ Medium                                               │
└──────────────┴──────────────────────────────────────────────────────┘

- Acceptance criteria: excludes unapproved/unverified counsels, court-mismatched counsels, practice-area-mismatched counsels, and unavailable/double-booked counsels; includes everyone else.
- Test cases: seeded profiles covering each exclusion reason individually + one fully-eligible control; double-booking conflict test (counsel already accepted a hearing same date).

M8 — Scoring & Ranking Engine

Objective
Implement the RANKING_FACTORS registry and weighted scoring.
────────────────────────────────────────
Files
counsel_matching.py
────────────────────────────────────────
New functions
RANKING_FACTORS config, _score_practice_area, _score_court_familiarity,
_score_availability_quality, _score_distance, _score_rating,
_score_response_time, _score_acceptance_rate, _score_past_performance,
score_candidates(db, candidates), rank_candidates(candidates)
────────────────────────────────────────
DB changes
None
────────────────────────────────────────
Dependencies
M5 (score inputs), M7 (candidate list to score)
────────────────────────────────────────
Complexity
Medium

- Acceptance criteria: score_candidates returns a MatchCandidate per input with confidence_score in [0,1]; rank_candidates sorts descending; adding a new (name, weight, fn) tuple to the registry changes ranking without touching either function's body (explicit extensibility test).
- Test cases: unit tests per factor function with synthetic inputs; end-to-end scoring of a small synthetic candidate set with known expected ordering; registry-extension test (add a dummy factor, confirm it's applied).

M9 — Recommendation Preview Endpoint

Objective
Ship the read-only preview — replaces the frontend's
advocateRecommendationsApi.js mock, delivering customer-visible value
immediately without needing the payment reorder or the write-path agent
at all.
────────────────────────────────────────
Files
counsel_matching.py, server.py
────────────────────────────────────────
New functions/endpoints
preview_candidates(db, court_id, practice_areas, hearing_date); GET
/recommendations/advocates
────────────────────────────────────────
DB changes
None (read-only)
────────────────────────────────────────
Dependencies
M7, M8
────────────────────────────────────────
Complexity
Easy

- Acceptance criteria: response shape matches the frontend's existing mock contract exactly ({source: "live", metadata, advocates}, per-advocate fields including ai_match_score/ai_match_reasons/estimated_response_time where available); frontend mock swap requires no component changes (per the existing docstring's stated contract).
- Test cases: contract test asserting response shape parity with the documented mock shape; empty-eligible-pool → advocates: [], source: "live" (not an error); frontend integration smoke test (manual or Cypress) confirming AvailableAdvocatesPanel renders real data unmodified.

---
PHASE 3 — Matching Write Path (join point — needs Phase 1 + Phase 2 both merged)

M10 — run_matching() + Tier-1 Notification + Logging

┌──────────────┬──────────────────────────────────────────────────────┐
│              │                                                      │
├──────────────┼──────────────────────────────────────────────────────┤
│ Objective    │ Implement the write-path orchestrator: rank, notify  │
│              │ tier 1, persist all logs.                            │
├──────────────┼──────────────────────────────────────────────────────┤
│ Files        │ counsel_matching.py                                  │
├──────────────┼──────────────────────────────────────────────────────┤
│ New          │ run_matching(db, hearing), notify_tier(db, hearing,  │
│ functions    │ ranked, tier, tier_size)                             │
├──────────────┼──────────────────────────────────────────────────────┤
│              │ Writes to hearing_requests (match_id, match_tier=1,  │
│ DB changes   │ match_tier_deadline_at, notified_counsel_ids,        │
│              │ match_confidence), counsel_matching_log (new doc),   │
│              │ ai_agent_logs (new doc), audit_log                   │
├──────────────┼──────────────────────────────────────────────────────┤
│ Dependencies │ M4 (notification template), M8 (scoring), M1         │
│              │ (fields/collections)                                 │
├──────────────┼──────────────────────────────────────────────────────┤
│ Complexity   │ Medium                                               │
└──────────────┴──────────────────────────────────────────────────────┘

- Acceptance criteria: calling run_matching on a valid hearing notifies exactly top-5 (or fewer if the eligible pool is smaller), stamps all new fields correctly, writes exactly one counsel_matching_log doc and one ai_agent_logs doc; zero-eligible-candidates path calls escalate_to_admin instead of silently no-op-ing.
- Test cases: happy path with 8+ eligible counsels → exactly 5 notified, tier=1; pool of 3 → all 3 notified, tier still recorded correctly; zero eligible → escalation path fires; log docs contain the expected structure.

M11 — Wire run_matching into confirm_payment

┌──────────────┬──────────────────────────────────────────────────────┐
│              │                                                      │
├──────────────┼──────────────────────────────────────────────────────┤
│              │ Connect the reordered state machine (M6) to the      │
│ Objective    │ matching agent (M10) via the                         │
│              │ StateMachine.on_transition hook — the first real use │
│              │  of the extension point workflow.py was written for. │
├──────────────┼──────────────────────────────────────────────────────┤
│ Files        │ hearings.py                                          │
├──────────────┼──────────────────────────────────────────────────────┤
│ New          │ None — extends the existing confirm_payment hook to  │
│ functions    │ call escrow.create_and_hold(payee_user_id=None) then │
│              │  counsel_matching.run_matching()                     │
├──────────────┼──────────────────────────────────────────────────────┤
│ DB changes   │ None beyond M10                                      │
├──────────────┼──────────────────────────────────────────────────────┤
│ Dependencies │ M6, M10, M2                                          │
├──────────────┼──────────────────────────────────────────────────────┤
│ Complexity   │ Medium                                               │
└──────────────┴──────────────────────────────────────────────────────┘

- Acceptance criteria: confirming payment on a hearing transitions it to broadcast and triggers matching in the same call; a matching-logic exception doesn't roll back or corrupt the payment-confirmed state (payment success must be durable even if matching has a bug — log and escalate, never re-raise past the payment confirmation).
- Test cases: end-to-end confirm-payment → assert broadcast status + notified_counsel_ids populated in one flow; forced matching-exception (monkeypatch) → payment status still correctly broadcast/held, error logged, escalation fired.

M12 — Acceptance-Side Integration

┌──────────────┬──────────────────────────────────────────────────────┐
│              │                                                      │
├──────────────┼──────────────────────────────────────────────────────┤
│ Objective    │ Complete the accept path: assign payee, clear        │
│              │ scheduling state, auto-chain to documents_shared.    │
├──────────────┼──────────────────────────────────────────────────────┤
│ Files        │ hearings.py                                          │
├──────────────┼──────────────────────────────────────────────────────┤
│ New          │ Extends accept_hearing_request with the three new    │
│ functions    │ side effects from LLD §16                            │
├──────────────┼──────────────────────────────────────────────────────┤
│ DB changes   │ Clears match_tier_deadline_at on the hearing; escrow │
│              │  payee_user_id set via M2's assign_payee             │
├──────────────┼──────────────────────────────────────────────────────┤
│ Dependencies │ M2, M6, M10                                          │
├──────────────┼──────────────────────────────────────────────────────┤
│ Complexity   │ Medium                                               │
└──────────────┴──────────────────────────────────────────────────────┘

- Acceptance criteria: accepting a hearing (from any tier) correctly assigns the escrow payee, clears the deadline (scheduler must skip it thereafter), and lands in documents_shared without a separate payment step.
- Test cases: accept → assert escrow payee_user_id set + wallet_held_balance credited exactly once; assert match_tier_deadline_at cleared; assert status is documents_shared immediately after accept (not accepted); race test — two simultaneous accepts, only one wins, only one assign_payee call fires.

---
PHASE 4 — Waterfall & Scheduler

M13 — APScheduler Waterfall Job

┌──────────────┬──────────────────────────────────────────────────────┐
│              │                                                      │
├──────────────┼──────────────────────────────────────────────────────┤
│              │ Implement tier advancement (1→2→3→escalate) on a     │
│ Objective    │ recurring poll, following the existing               │
│              │ daily-settlement-job registration pattern.           │
├──────────────┼──────────────────────────────────────────────────────┤
│ Files        │ counsel_matching.py, server.py                       │
│              │ (@app.on_event("startup") registration)              │
├──────────────┼──────────────────────────────────────────────────────┤
│ New          │ advance_or_escalate(db, hearing),                    │
│ functions    │ check_stalled_matches(db); startup job registration  │
│              │ with IntervalTrigger(seconds=10), max_instances=1    │
├──────────────┼──────────────────────────────────────────────────────┤
│ DB changes   │ None beyond M1                                       │
├──────────────┼──────────────────────────────────────────────────────┤
│ Dependencies │ M11, M12 (must not fire on already-accepted hearings │
│              │  — depends on M12's deadline-clearing)               │
├──────────────┼──────────────────────────────────────────────────────┤
│ Complexity   │ Hard (timing-sensitive, needs careful testing)       │
└──────────────┴──────────────────────────────────────────────────────┘

- Acceptance criteria: a hearing past its tier-1 deadline with no acceptance gets tier-2 notified automatically within one poll cycle; same for tier-2→tier-3; tier-3 expiry triggers escalation, not silent drop; an accepted hearing is never touched by the job (deadline was cleared); urgent hearings use the shorter stage durations.
- Test cases: time-manipulated test (freeze/advance clock or backdate match_tier_deadline_at) for each tier transition; accepted-hearing-is-skipped test; urgent vs. normal stage-duration test; job overlap test (max_instances=1 prevents concurrent runs on a slow poll).

M14 — Early-Advance on Full-Tier Decline

┌──────────────┬──────────────────────────────────────────────────────┐
│              │                                                      │
├──────────────┼──────────────────────────────────────────────────────┤
│              │ Speed optimization: advance immediately if every     │
│ Objective    │ notified counsel in the current tier has declined,   │
│              │ rather than waiting for the deadline.                │
├──────────────┼──────────────────────────────────────────────────────┤
│ Files        │ hearings.py (decline_hearing_request call site),     │
│              │ counsel_matching.py                                  │
├──────────────┼──────────────────────────────────────────────────────┤
│ New          │ maybe_early_advance(db, hearing_id)                  │
│ functions    │                                                      │
├──────────────┼──────────────────────────────────────────────────────┤
│ DB changes   │ None                                                 │
├──────────────┼──────────────────────────────────────────────────────┤
│ Dependencies │ M13                                                  │
├──────────────┼──────────────────────────────────────────────────────┤
│ Complexity   │ Easy                                                 │
└──────────────┴──────────────────────────────────────────────────────┘

- Acceptance criteria: declining as the last remaining notified counsel in a tier triggers immediate tier advancement; declining while others in the tier haven't responded yet does not.
- Test cases: single-counsel-tier decline → immediate advance; multi-counsel-tier partial decline → no advance until deadline or all decline.

---
PHASE 5 — Escalation, Admin, Refund

M15 — Admin Escalation Queue + Manual Assign

(Can run in parallel with M13/M14 — doesn't depend on the scheduler, since admin can assign at any tier, not just after escalation.)

Objective
Give Ops visibility and override capability.
────────────────────────────────────────
Files
counsel_matching.py, server.py
────────────────────────────────────────
New functions/endpoints
escalate_to_admin(db, hearing, reason), admin_assign_counsel(db,
hearing_id, counsel_user_id, admin_user); GET
/admin/hearing-requests?escalated=true; POST
/admin/hearing-requests/{id}/assign
────────────────────────────────────────
DB changes
admin_grace_deadline_at set on escalation
────────────────────────────────────────
Dependencies
M10 (can integrate against tier-1-only behavior first, then naturally
benefits once M13 lands)
────────────────────────────────────────
Complexity
Medium

- Acceptance criteria: admin can force-assign any open (unaccepted) hearing at any tier; the assignment is race-safe against a simultaneous real accept and against a simultaneous scheduler auto-refund; escalated hearings are queryable and show remaining grace time.
- Test cases: admin-assign on a tier-1 hearing (before any escalation) succeeds; admin-assign racing a real accept — only one wins; admin-assign racing an auto-refund (M16) — only one wins; non-admin gets 403.

M16 — Auto-Refund + Rebook Flow

┌──────────────────────┬──────────────────────────────────────────────┐
│                      │                                              │
├──────────────────────┼──────────────────────────────────────────────┤
│ Objective            │ Terminal SLA-exhaustion handling.            │
├──────────────────────┼──────────────────────────────────────────────┤
│ Files                │ counsel_matching.py, server.py               │
├──────────────────────┼──────────────────────────────────────────────┤
│ New                  │ auto_refund_and_offer_rebook(db, hearing);   │
│ functions/endpoints  │ POST /hearing-requests/{id}/rebook           │
├──────────────────────┼──────────────────────────────────────────────┤
│ DB changes           │ hearing_requests.status → cancelled,         │
│                      │ cancel_reason: "unmatched_sla_expired"       │
├──────────────────────┼──────────────────────────────────────────────┤
│ Dependencies         │ M13, M14, M15, M2 (refund guard)             │
├──────────────────────┼──────────────────────────────────────────────┤
│ Complexity           │ Medium                                       │
└──────────────────────┴──────────────────────────────────────────────┘

- Acceptance criteria: grace-period expiry with no acceptance/admin action triggers exactly one refund call, correct status/reason, customer notified; rebook creates a genuinely new hearing_id/escrow, never resurrects the cancelled one.
- Test cases: full-timeline test (tier1→2→3→escalate→grace-expiry) → refund fires exactly once; refund-then-rebook → new hearing_id, new escrow_id, original stays cancelled; admin assigning during grace period prevents the refund from firing.

---
PHASE 6 — Hardening

M17 — End-to-End Regression + Performance Validation

┌──────────────┬───────────────────────────────────────────────────────┐
│              │                                                       │
├──────────────┼───────────────────────────────────────────────────────┤
│              │ Full regression across the entire reordered +         │
│ Objective    │ agent-augmented lifecycle; validate indexes and query │
│              │  costs under realistic volume.                        │
├──────────────┼───────────────────────────────────────────────────────┤
│ Files        │ backend/tests/test_courtbazaar_api.py (new test       │
│              │ module, e.g. test_counsel_matching.py)                │
├──────────────┼───────────────────────────────────────────────────────┤
│ Dependencies │ All previous milestones                               │
├──────────────┼───────────────────────────────────────────────────────┤
│ Complexity   │ Medium                                                │
└──────────────┴───────────────────────────────────────────────────────┘

- Acceptance criteria: every happy/unhappy path in the LLD's lifecycle (§2) has an automated test; scheduler poll query plan uses the M1 compound index (verified via explain()); no N+1 query pattern in score_candidates under a seeded pool of 50+ counsels.
- Test cases: full lifecycle from booking to payout with matching in the loop; refund lifecycle; admin override lifecycle; index usage assertion; timed load test of score_candidates against a synthetic 50-counsel pool.

M18 — Observability (stretch, optional for v1.0 ship)

┌──────────────┬───────────────────────────────────────────────────────┐
│              │                                                       │
├──────────────┼───────────────────────────────────────────────────────┤
│              │ Admin-facing KPI view (match rate, avg                │
│ Objective    │ time-to-accept, tier-1 success rate) sourced from     │
│              │ counsel_matching_log.                                 │
├──────────────┼───────────────────────────────────────────────────────┤
│ Dependencies │ M10, M13, M17                                         │
├──────────────┼───────────────────────────────────────────────────────┤
│ Complexity   │ Easy                                                  │
└──────────────┴───────────────────────────────────────────────────────┘

- Acceptance criteria: a read-only aggregation endpoint/report surfaces the KPIs named in the original spec goals.
- Test cases: aggregation correctness against seeded counsel_matching_log data.

---
Parallelization plan

┌─────────────────┬────────────────────────────────┬──────────────────┐
│      Track      │           Milestones           │     Can run      │
│                 │                                │    alongside     │
├─────────────────┼────────────────────────────────┼──────────────────┤
│ A               │ M1 → M2, M3, M4, M5 (all       │ —                │
│                 │ parallel after M1)             │                  │
├─────────────────┼────────────────────────────────┼──────────────────┤
│ B (Phase 1)     │ M6                             │ Track C          │
├─────────────────┼────────────────────────────────┼──────────────────┤
│ C (Phase 2)     │ M7 → M8 → M9                   │ Track B          │
├─────────────────┼────────────────────────────────┼──────────────────┤
│ — (join)        │ M10 → M11 → M12                │ requires B + C   │
│                 │                                │ merged           │
├─────────────────┼────────────────────────────────┼──────────────────┤
│ D (Phase 4)     │ M13 → M14                      │ Track E          │
├─────────────────┼────────────────────────────────┼──────────────────┤
│ E (Phase 5,     │ M15                            │ Track D          │
│ partial)        │                                │                  │
├─────────────────┼────────────────────────────────┼──────────────────┤
│ —               │ M16                            │ requires D + E   │
├─────────────────┼────────────────────────────────┼──────────────────┤
│ F               │ M17, M18                       │ after everything │
└─────────────────┴────────────────────────────────┴──────────────────┘

Up to 5 developers can work Phase 0 in parallel; 2 tracks in Phase 1/2; 2 tracks again in Phase 4/5.

---
Implementation dependency graph

mermaid
graph TD
    M1[M1: Schema Bootstrap] --> M6[M6: Payment Reorder]
    M1 --> M7[M7: Eligibility Filter]
    M2[M2: Escrow Deferred Payee] --> M11[M11: Wire run_matching]
    M2 --> M12[M12: Acceptance Integration]
    M2 --> M16[M16: Auto-Refund]
    M3[M3: KYC/Bar Verify] --> M7
    M4[M4: hearing_offer Template] --> M10[M10: run_matching]
    M5[M5: Composite Score Fn] --> M8[M8: Scoring Engine]
    M7 --> M8
    M8 --> M9[M9: Recommendation Endpoint]
    M8 --> M10
    M6 --> M11
    M10 --> M11
    M11 --> M12
    M12 --> M13[M13: Scheduler Waterfall]
    M13 --> M14[M14: Early Advance]
    M10 --> M15[M15: Admin Escalation]
    M13 --> M15
    M13 --> M16
    M14 --> M16
    M15 --> M16
    M12 --> M17[M17: E2E Regression]
    M14 --> M17
    M16 --> M17
    M17 --> M18[M18: Observability]

---
Development checklist

Phase 0 — Foundational
- [ ] M1 — Schema & collections bootstrap (fields, indexes)
- [ ] M2 — Escrow deferred-payee support (assign_payee, nullable payee)
- [ ] M3 — Admin KYC + Bar Council verification endpoints
- [ ] M4 — hearing_offer notification template
- [ ] M5 — Practice composite score function

Phase 1 — Critical reorder
- [ ] M6 — Payment/broadcast reorder (backend + frontend companion) — full regression pass required before merge

Phase 2 — Matching core
- [ ] M7 — Eligibility & availability filtering
- [ ] M8 — Scoring & ranking engine (RANKING_FACTORS registry)
- [ ] M9 — GET /recommendations/advocates (frontend mock replacement)

Phase 3 — Matching write path
- [ ] M10 — run_matching() + tier-1 notify + logging
- [ ] M11 — Wire run_matching into confirm_payment hook
- [ ] M12 — Acceptance-side integration (assign payee, auto-chain)

Phase 4 — Waterfall
- [ ] M13 — APScheduler waterfall job (tier advancement)
- [ ] M14 — Early-advance on full-tier decline

Phase 5 — Escalation & refund
- [ ] M15 — Admin escalation queue + manual assign
- [ ] M16 — Auto-refund + rebook flow

Phase 6 — Hardening
- [ ] M17 — End-to-end regression + performance validation
- [ ] M18 — Observability KPIs (stretch)