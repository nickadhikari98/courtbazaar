"""Counsel Matching & Assignment Agent — session ledger.

This module owns the counsel_matching_log collection: one document per
hearing's matching lifecycle, opened when matching starts and closed out
with a final status once it's over. Deliberately minimal at this stage
(roadmap M4): it knows how to open a session, append a generic event to it,
and close it — it has no idea what a "candidate," "tier," or "ranking" is.
Eligibility filtering, scoring, notification and the waterfall scheduler are
separate, later milestones that build on top of these primitives, the same
way hearings.py builds its own operational workflow on top of escrow.py's
payment primitives without either module reaching into the other's state.

get_or_create_matching_session is idempotent by relying on the unique index
on hearing_id (see ensure_indexes) as the actual concurrency guard, rather
than an application-level check-then-insert.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Callable, List, Optional, Tuple

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError


def new_match_id() -> str:
    return f"match_{uuid.uuid4().hex[:12]}"


async def ensure_indexes(db) -> None:
    """One doc per hearing's matching lifecycle — moved here from
    hearings.py (roadmap M1) now that this module exists to own it."""
    await db.counsel_matching_log.create_index([("hearing_id", 1)], name="matching_log_hearing", unique=True)
    await db.counsel_matching_log.create_index([("match_id", 1)], name="matching_log_match_id", unique=True)


async def get_or_create_matching_session(db, hearing_id: str, urgent: bool = False) -> dict:
    """Opens a matching session for a hearing if one doesn't already exist.
    Idempotent: a second call for the same hearing_id returns the session
    created by the first, never a duplicate."""
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "match_id": new_match_id(),
        "hearing_id": hearing_id,
        "urgent": urgent,
        "status": "in_progress",  # in_progress | matched | unmatched | escalated | refunded
        "tiers": [],              # populated by later milestones (waterfall/notification)
        "accepted_by": None,
        "accepted_at": None,
        "escalated_at": None,
        "refunded_at": None,
        "final_decision": None,
        "timeline": [],           # generic session event log — see append_session_event
        "created_at": now,
        "updated_at": now,
    }
    try:
        await db.counsel_matching_log.insert_one(doc)
    except DuplicateKeyError:
        existing = await db.counsel_matching_log.find_one({"hearing_id": hearing_id}, {"_id": 0})
        return existing
    doc.pop("_id", None)
    return doc


async def get_matching_session(db, hearing_id: str) -> Optional[dict]:
    return await db.counsel_matching_log.find_one({"hearing_id": hearing_id}, {"_id": 0})


async def append_session_event(db, match_id: str, event: str, detail: Optional[dict] = None) -> None:
    """Generic timeline entry — same shape/spirit as hearings.py's
    _push_activity. Later milestones use this to record tier notifications,
    acceptances, escalations etc. without this module needing to understand
    what any of those mean."""
    await db.counsel_matching_log.update_one(
        {"match_id": match_id},
        {"$push": {"timeline": {
            "event": event, "detail": detail or {},
            "at": datetime.now(timezone.utc).isoformat(),
        }}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )


async def finalize_matching_session(db, match_id: str, status: str, final_decision: Optional[str] = None) -> dict:
    """Generic session-closing primitive. This function doesn't decide what
    "matched"/"unmatched"/"escalated"/"refunded" mean or when they apply —
    it just records whatever the caller (a later milestone) determines."""
    now = datetime.now(timezone.utc).isoformat()
    await db.counsel_matching_log.update_one(
        {"match_id": match_id},
        {"$set": {"status": status, "final_decision": final_decision, "updated_at": now}},
    )
    return await db.counsel_matching_log.find_one({"match_id": match_id}, {"_id": 0})


async def discover_candidates(db, hearing_id: str) -> List[dict]:
    """Candidate Discovery Engine (roadmap M5) — a coarse, wide-net first
    pass, not a precise shortlist. Eligibility here is deliberately limited
    to three hard gates on the counsel's own profile:
        - kyc_status == "approved"      (see practice.approve_kyc)
        - bar_council_verified == True  (see practice.verify_bar_council)
        - availability_mode == True     (coarse "taking hearings" toggle)

    Court and practice-area matching are NOT applied yet: hearing_requests
    has no practice_areas field in the current schema (a later milestone
    adds it), and court matching wasn't part of this milestone's scope even
    though court_id already exists on hearing_requests today. Likewise,
    per-date availability_slots conflict checking (recurring slots, holiday
    blocks) is a precision-scoring concern for a later milestone, not this
    coarse discovery pass.

    Returns full proxy_counsel_profiles documents (or an empty list if no
    one qualifies) — the exact input shape a later ranking/scoring milestone
    plugs into, without this function knowing anything about ranking."""
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
    if not hearing:
        raise HTTPException(404, "Hearing not found")

    query = {
        "kyc_status": "approved",
        "bar_council_verified": True,
        "availability_mode": True,
    }
    return await db.proxy_counsel_profiles.find(query, {"_id": 0}).to_list(500)


# ---------------------------------------------------------------------------
# Candidate Scoring Engine (roadmap M6)
#
# Only founder-named ranking factors backed by real, already-populated data
# are included: Rating, Court Familiarity (as a court_id membership check),
# and Past Performance (as cases_completed). Two additional real-but-not-
# founder-named signals are folded in as their own tunable weights rather
# than silently blended into another factor: experience_years and
# instant_booking.
#
# Deliberately excluded, and why (see M6 design notes for the full version):
#   - Practice Area Match / Distance: would require inventing a schema field
#     (hearing_requests.practice_areas, counsel/court geocoordinates) that
#     doesn't exist today — not allowed this milestone.
#   - Response Time / Acceptance Rate: counsel_matching_log (M4) exists as a
#     collection, but no milestone has written real notification/acceptance
#     timestamps into it yet, so every candidate would show identical,
#     meaningless data — not a real signal, so not included.
#   - success_rate: present as a field on every profile document, but no
#     code path anywhere ever writes a value to it (always None today) —
#     same "field exists, no real data" reasoning as the two factors above.
# ---------------------------------------------------------------------------

CASES_COMPLETED_SATURATION = 20  # cases_completed at/above this scores the max for that factor
EXPERIENCE_YEARS_SATURATION = 15  # experience_years at/above this scores the max for that factor


def _score_rating(counsel: dict, hearing: dict) -> float:
    rating = counsel.get("rating") or 0
    return min(float(rating) / 5.0, 1.0)


def _score_court_match(counsel: dict, hearing: dict) -> float:
    return 1.0 if hearing.get("court_id") in (counsel.get("courts") or []) else 0.0


def _score_cases_completed(counsel: dict, hearing: dict) -> float:
    cases = counsel.get("cases_completed") or 0
    return min(float(cases) / CASES_COMPLETED_SATURATION, 1.0)


def _score_experience_years(counsel: dict, hearing: dict) -> float:
    years = counsel.get("experience_years") or 0
    return min(float(years) / EXPERIENCE_YEARS_SATURATION, 1.0)


def _score_instant_booking(counsel: dict, hearing: dict) -> float:
    return 1.0 if counsel.get("instant_booking") else 0.0


# (name, weight, compute_fn) — weights sum to 1.0. This is the seam future
# milestones use to add/remove/reweight factors: edit this list, never the
# loop in score_candidates.
SCORING_FACTORS: List[Tuple[str, float, Callable[[dict, dict], float]]] = [
    ("rating", 0.35, _score_rating),
    ("court_match", 0.25, _score_court_match),
    ("cases_completed", 0.20, _score_cases_completed),
    ("experience_years", 0.10, _score_experience_years),
    ("instant_booking", 0.10, _score_instant_booking),
]


def score_candidates(hearing: dict, candidates: List[dict]) -> List[dict]:
    """Attaches a confidence_score (0-1, in-memory only — never written back
    to proxy_counsel_profiles) to each candidate and returns them sorted
    highest-first. Pure and synchronous: no database access, no mutation of
    the input list/dicts. Does not select a shortlist size, notify anyone,
    or decide anything beyond "here is a score" — see module notes above for
    what later milestones own instead."""
    scored = [
        {**counsel, "confidence_score": round(
            sum(weight * fn(counsel, hearing) for _, weight, fn in SCORING_FACTORS), 4,
        )}
        for counsel in candidates
    ]
    scored.sort(key=lambda c: c["confidence_score"], reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Top Candidate Selection (roadmap M7)
# ---------------------------------------------------------------------------

# The single place to change how many top-ranked candidates get selected by
# default. A later milestone can either edit this constant directly, or pass
# batch_size explicitly to select_top_candidates — neither requires changing
# that function's signature/callers.
TOP_CANDIDATE_BATCH_SIZE = 5


def select_top_candidates(hearing: dict, scored_candidates: List[dict], batch_size: Optional[int] = None) -> List[dict]:
    """Takes the output of score_candidates() (already sorted highest-first)
    and returns the top batch_size candidates, exactly as given — no
    re-sorting, no score mutation, no persistence. This function trusts
    score_candidates' ordering completely rather than re-deriving it.

    `hearing` is accepted but unused by this milestone's plain top-N
    strategy — kept in the signature so a future selection strategy (e.g. a
    different batch size for urgent hearings) can read hearing context
    without any caller needing to change how it invokes this function."""
    size = batch_size if batch_size is not None else TOP_CANDIDATE_BATCH_SIZE
    size = max(size, 0)  # avoid Python's negative-slice semantics (list[:-1] != "select none")
    return scored_candidates[:size]


# ---------------------------------------------------------------------------
# Notification Batch Preparation (roadmap M8)
#
# Candidates here are proxy_counsel_profiles documents — they have no
# phone/email/notif_prefs (those live on the separate `users` collection,
# keyed by the same user_id). Resolving contact details and composing actual
# message copy are both delivery concerns for a future notification sender
# (see notifications.py's tmpl_* convention for where copy gets rendered) —
# this layer only identifies who and what, as plain structured context.
#
# Deliberately excluded, and why:
#   - urgent: reserved on hearing_requests since M1 but never populated by
#     create_hearing_request (same "field exists, no real data yet" case as
#     success_rate in M6) — including it would default every entry to a
#     misleading False rather than reflecting real data.
#   - case_details/matter_id: real fields, but not needed to identify who to
#     notify about what; a sender can fetch the full hearing by hearing_id.
#   - phone/email/notif_prefs: belong to the `users` collection and the
#     eventual sender, not this preparation layer.
# ---------------------------------------------------------------------------

# Default label for the future sender to key its template/channel selection
# on. Like TOP_CANDIDATE_BATCH_SIZE, overridable per-call without changing
# this function's signature.
NOTIFICATION_EVENT_TYPE = "hearing_offer"


def prepare_notification_batch(hearing: dict, selected_candidates: List[dict],
                                event_type: Optional[str] = None) -> List[dict]:
    """Turns select_top_candidates()'s output into an in-memory notification
    batch — one entry per candidate, order preserved, candidate objects
    untouched. Sends nothing, writes nothing, creates no session, assigns no
    one, updates no hearing status. Just structured context a future
    notification sender consumes."""
    resolved_event_type = event_type if event_type is not None else NOTIFICATION_EVENT_TYPE
    return [
        {
            "counsel_user_id": candidate.get("user_id"),
            "hearing_id": hearing.get("hearing_id"),
            "court_id": hearing.get("court_id"),
            "hearing_date": hearing.get("hearing_date"),
            "fee": hearing.get("fee"),
            "confidence_score": candidate.get("confidence_score"),
            "event_type": resolved_event_type,
        }
        for candidate in selected_candidates
    ]


# ---------------------------------------------------------------------------
# Notification Dispatch Engine (roadmap M9)
#
# notifications.notify() only recognizes a fixed set of event strings
# ("order_placed", "order_status", "otp", "hearing_event") — there is no
# "hearing_offer" branch. Rather than add one (a notifications.py change
# beyond this milestone's minimum-files scope, and arguably a step toward
# "new provider" territory), dispatch reuses the existing, fully-implemented
# "hearing_event" type — the same one server.py's _notify_hearing_event
# already uses for every other hearing lifecycle notification. M8's
# event_type label is preserved in the dispatch result for traceability, but
# the actual notify() call always goes through "hearing_event".
# ---------------------------------------------------------------------------

def _offer_message(entry: dict) -> Tuple[str, str]:
    """Builds minimal notification copy from fields prepare_notification_batch()
    already assembled — the same inline string-formatting convention every
    _notify_hearing_event call site in server.py already uses, not a new
    templating abstraction."""
    title = "New hearing offer"
    court_id = entry.get("court_id") or "a court"
    hearing_date = entry.get("hearing_date") or "a date to be confirmed"
    fee = entry.get("fee")
    fee_clause = f" Fee: Rs.{fee}." if fee else ""
    body = f"You've been offered a hearing at {court_id} on {hearing_date}.{fee_clause} Log in to accept."
    return title, body


async def dispatch_notifications(db, notification_batch: List[dict]) -> List[dict]:
    """Attempts delivery for every entry in prepare_notification_batch()'s
    output, in order, using only notify()/record_notification_event() — no
    new provider, no new notify() branch. Recipient info (phone/email/
    notif_prefs) is resolved from db.users by counsel_user_id since batch
    entries only carry the user_id. Never assigns a counsel, never updates
    hearing status, never implements acceptance or waterfall logic — purely
    delivery + a per-notification result. One entry failing (missing
    recipient, an unexpected exception) never aborts the rest of the batch."""
    from notifications import notify, record_notification_event

    results = []
    for entry in notification_batch:
        counsel_user_id = entry.get("counsel_user_id")
        hearing_id = entry.get("hearing_id")
        try:
            recipient = await db.users.find_one({"user_id": counsel_user_id}, {"_id": 0})
            if not recipient:
                results.append({
                    "counsel_user_id": counsel_user_id, "hearing_id": hearing_id,
                    "status": "failed", "reason": "recipient user not found", "channel_results": [],
                })
                continue

            title, body = _offer_message(entry)
            channel_results = notify(recipient, "hearing_event", {"title": title, "body": body})
            await record_notification_event(db, counsel_user_id, "hearing_event", title, body, "hearing", hearing_id)
            results.append({
                "counsel_user_id": counsel_user_id, "hearing_id": hearing_id,
                "status": "dispatched", "channel_results": channel_results,
            })
        except Exception as e:
            results.append({
                "counsel_user_id": counsel_user_id, "hearing_id": hearing_id,
                "status": "failed", "reason": str(e), "channel_results": [],
            })
    return results


# ---------------------------------------------------------------------------
# Matching Orchestration — Tier 1 (roadmap M10)
#
# run_matching/notify_tier compose the M4-M9 pipeline (session ledger,
# discover_candidates, score_candidates, select_top_candidates,
# prepare_notification_batch, dispatch_notifications) into one orchestrated
# pass — no pipeline stage's own logic is reimplemented here, only glued
# together and persisted. Tier-1 only, on purpose: notify_tier's tier/
# tier_size parameters exist because the roadmap names them in this
# function's signature, but this milestone only ever calls tier=1 — picking
# per-tier candidate slices for tier 2/3, deadline-driven advancement, and
# admin escalation are M13/M14/M15's scope, not this one's (see the guard in
# notify_tier and the zero-candidate branch in run_matching below).
#
# ai_agent_logs (named in the original roadmap draft) doesn't exist anywhere
# in this codebase and isn't created here either — audit_log already exists
# for exactly this kind of traceability record (see audit_log.log_audit,
# used the same way by practice.py's approve_kyc/verify_bar_council), so
# this reuses that instead of standing up a parallel logging collection.
# ---------------------------------------------------------------------------

# How long each tier's candidates have to respond before a tier advancement
# is due. M10 only ever needed a flat tier-1 value; M13 (waterfall) is what
# actually reads the tier-2/3 rows and the urgent table. Keyed by tier, not
# computed from it, since the roadmap never specifies these should scale
# linearly. `urgent` is read from the matching session (frozen at
# run_matching/get_or_create_matching_session time), not re-read from
# hearing_requests.urgent, which stays reserved-but-unpopulated upstream —
# the session is the authoritative record of what was true when matching
# started for this hearing.
TIER_RESPONSE_WINDOW_MINUTES = {1: 30, 2: 20, 3: 15}
URGENT_TIER_RESPONSE_WINDOW_MINUTES = {1: 10, 2: 7, 3: 5}


async def notify_tier(db, hearing: dict, ranked: List[dict], tier: int, tier_size: int) -> dict:
    """Notifies one tier's worth of already-ranked candidates and persists
    the result. Tiers 1-3 (M10 built tier 1; M13 extends this to 2/3 for
    waterfall advancement) — reuses select_top_candidates for the tier's
    slice. The caller (run_matching for tier 1, advance_or_escalate for tier
    2/3) is responsible for handing this an already-filtered `ranked` list
    with any previously-notified/declined candidates already excluded; this
    function itself has no notion of "previous tiers."

    Stamps exactly the fields the roadmap named for M10: match_id/
    match_tier/match_tier_deadline_at/notified_counsel_ids/match_confidence
    on hearing_requests, a tiers[] entry + timeline event on
    counsel_matching_log, and one audit_log entry. Never touches
    hearing_requests.status or proxy_counsel_user_id.

    M13 hardening: the hearing_requests write is an atomic conditional
    update (status=="broadcast", and for tier>1 match_tier==tier-1),
    performed BEFORE dispatching any notifications, not after. If the
    hearing has already moved on — accepted, cancelled, or already advanced
    past this tier by a concurrent poll tick — the write simply matches
    nothing and this returns a "skipped" result without notifying anyone or
    writing any log entry, instead of resurrecting stale scheduling fields
    on a hearing this tier no longer applies to, or wasting a notification
    send on an already-resolved hearing."""
    if tier not in (1, 2, 3):
        raise ValueError("notify_tier only supports tiers 1-3 (roadmap M10-M13)")

    from audit_log import log_audit

    hearing_id = hearing["hearing_id"]
    session = await get_matching_session(db, hearing_id)
    if not session:
        raise HTTPException(500, "No matching session open for this hearing — call run_matching first")

    tier_candidates = select_top_candidates(hearing, ranked, tier_size)
    notified_counsel_ids = [c.get("user_id") for c in tier_candidates]
    match_confidence = tier_candidates[0].get("confidence_score") if tier_candidates else None

    urgent = bool(session.get("urgent"))
    window_minutes = (URGENT_TIER_RESPONSE_WINDOW_MINUTES if urgent else TIER_RESPONSE_WINDOW_MINUTES)[tier]
    now = datetime.now(timezone.utc)
    deadline_at = (now + timedelta(minutes=window_minutes)).isoformat()

    claim_filter = {"hearing_id": hearing_id, "status": "broadcast"}
    if tier > 1:
        claim_filter["match_tier"] = tier - 1
    claim_result = await db.hearing_requests.update_one(
        claim_filter,
        {"$set": {
            "match_id": session["match_id"],
            "match_tier": tier,
            "match_tier_deadline_at": deadline_at,
            "notified_counsel_ids": notified_counsel_ids,
            "match_confidence": match_confidence,
            "updated_at": now.isoformat(),
        }},
    )
    if claim_result.matched_count == 0:
        return {
            "status": "skipped", "match_id": session["match_id"], "tier": tier,
            "notified_counsel_ids": [], "match_confidence": None,
            "match_tier_deadline_at": None, "dispatch_results": [],
        }

    batch = prepare_notification_batch(hearing, tier_candidates)
    dispatch_results = await dispatch_notifications(db, batch)

    tier_entry = {
        "tier": tier, "tier_size": tier_size,
        "notified_counsel_ids": notified_counsel_ids,
        "match_confidence": match_confidence,
        "notified_at": now.isoformat(),
    }
    await db.counsel_matching_log.update_one(
        {"match_id": session["match_id"]}, {"$push": {"tiers": tier_entry}},
    )
    await append_session_event(db, session["match_id"], "tier_notified", {**tier_entry, "dispatch_results": dispatch_results})
    await log_audit(db, "matching.tier_notified", None, {
        "hearing_id": hearing_id, "match_id": session["match_id"], "tier": tier,
        "notified_counsel_ids": notified_counsel_ids,
    })

    return {
        "status": "notified",
        "match_id": session["match_id"], "tier": tier,
        "notified_counsel_ids": notified_counsel_ids,
        "match_confidence": match_confidence,
        "match_tier_deadline_at": deadline_at,
        "dispatch_results": dispatch_results,
    }


async def run_matching(db, hearing: dict) -> dict:
    """Write-path orchestrator (roadmap M10): opens/reuses the matching
    session, discovers + scores eligible candidates, and notifies tier 1 —
    composing get_or_create_matching_session, discover_candidates,
    score_candidates and notify_tier without reimplementing any of them.

    Zero eligible candidates: only records the terminal outcome —
    finalize_matching_session(status="escalated") plus one audit_log entry —
    and returns without touching hearing_requests at all (no tier/
    notification/scheduling fields get written, since nothing was
    notified). This deliberately does not implement admin escalation itself
    (no escalate_to_admin function is created here); that workflow is M15's.

    Never transitions hearing status, never assigns proxy_counsel_user_id,
    never touches escrow, never advances past tier 1."""
    from audit_log import log_audit

    hearing_id = hearing["hearing_id"]
    urgent = bool(hearing.get("urgent"))  # reserved field, still unpopulated upstream — see discover_candidates notes
    session = await get_or_create_matching_session(db, hearing_id, urgent=urgent)

    candidates = await discover_candidates(db, hearing_id)
    if not candidates:
        session = await finalize_matching_session(
            db, session["match_id"], status="escalated", final_decision="no_eligible_candidates",
        )
        await log_audit(db, "matching.escalated", None, {
            "hearing_id": hearing_id, "match_id": session["match_id"],
            "reason": "no_eligible_candidates",
        })
        return {
            "status": "escalated", "match_id": session["match_id"], "tier": None,
            "notified_counsel_ids": [], "match_confidence": None,
            "match_tier_deadline_at": None, "dispatch_results": [],
        }

    ranked = score_candidates(hearing, candidates)
    tier_result = await notify_tier(db, hearing, ranked, tier=1, tier_size=TOP_CANDIDATE_BATCH_SIZE)
    return {"status": "notified", **tier_result}


# ---------------------------------------------------------------------------
# Waterfall Tier Advancement (roadmap M13)
#
# advance_or_escalate handles one hearing already known to be past its
# current tier's deadline; check_stalled_matches (below) is the recurring
# poll that finds those hearings and calls it once per hearing.
#
# Candidate selection re-derives eligibility/ranking fresh at each tier
# rather than reusing tier-1's original in-memory ranked list — nothing
# persists that list anywhere (counsel_matching_log's tiers[] only ever
# stored the per-tier summary, never the full scored pool), and re-discovery
# also naturally reflects any eligibility changes since the previous tier
# ran. Exclusion is by user_id (already-notified, unioned across every prior
# tier, plus anyone in hearing_requests.declined_by), not by re-deriving
# position from score order, so re-ranking drift between tiers can't
# accidentally re-notify someone already contacted or someone who
# explicitly declined.
# ---------------------------------------------------------------------------

async def _escalate_match(db, hearing_id: str, session: dict, reason: str) -> dict:
    """Shared terminal-outcome path for advance_or_escalate's two escalation
    triggers (tier-3 expiry, zero remaining candidates at any tier) — same
    shape as run_matching's own zero-candidate escalation (M10), not shared
    code with it (run_matching stays untouched, per this milestone's scope),
    just the same pattern: finalize_matching_session + one audit_log entry,
    no hearing_requests write, no admin-facing workflow (that's M15's job)."""
    from audit_log import log_audit
    session = await finalize_matching_session(db, session["match_id"], status="escalated", final_decision=reason)
    await log_audit(db, "matching.escalated", None, {
        "hearing_id": hearing_id, "match_id": session["match_id"], "reason": reason,
    })
    return {
        "status": "escalated", "match_id": session["match_id"], "tier": None,
        "notified_counsel_ids": [], "match_confidence": None,
        "match_tier_deadline_at": None, "dispatch_results": [],
    }


async def advance_or_escalate(db, hearing: dict) -> dict:
    """Given one hearing already past its current tier's deadline, either
    notifies the next tier or escalates.

    Re-fetches the hearing fresh first — a cheap fail-fast check so a
    hearing already accepted/cancelled between check_stalled_matches's query
    and this call is skipped without wasted discovery/scoring work. This
    check alone isn't the race-safety guarantee, though: the actual
    correctness guard is notify_tier's own atomic conditional write: there's
    still a gap between this read and that write, and notify_tier's
    conditional update is what closes it."""
    hearing_id = hearing["hearing_id"]
    current = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
    if not current or current.get("status") != "broadcast":
        return {"status": "skipped", "reason": "hearing no longer in broadcast"}

    session = await get_matching_session(db, hearing_id)
    if not session:
        raise HTTPException(500, "No matching session open for this hearing — call run_matching first")

    current_tier = current.get("match_tier") or 1
    if current_tier >= 3:
        return await _escalate_match(db, hearing_id, session, reason="tier_3_expired")
    next_tier = current_tier + 1

    candidates = await discover_candidates(db, hearing_id)
    ranked = score_candidates(current, candidates)

    already_notified = set()
    for tier_entry in session.get("tiers") or []:
        already_notified.update(tier_entry.get("notified_counsel_ids") or [])
    already_declined = set(current.get("declined_by") or [])
    excluded = already_notified | already_declined

    remaining = [c for c in ranked if c.get("user_id") not in excluded]
    if not remaining:
        return await _escalate_match(db, hearing_id, session, reason=f"no_eligible_candidates_tier_{next_tier}")

    return await notify_tier(db, current, remaining, tier=next_tier, tier_size=TOP_CANDIDATE_BATCH_SIZE)


async def check_stalled_matches(db) -> List[dict]:
    """Poll entry point (roadmap M13) — registered from server.py on a
    recurring interval (see schedule_matching_waterfall). Finds every
    hearing past its current tier's deadline and still open, and advances/
    escalates each independently; one hearing's failure is logged and never
    stops the rest of the batch — same convention as dispatch_notifications'
    per-entry isolation."""
    from audit_log import log_audit

    now = datetime.now(timezone.utc).isoformat()
    stalled = await db.hearing_requests.find(
        {"status": "broadcast", "proxy_counsel_user_id": None,
         "match_tier_deadline_at": {"$ne": None, "$lt": now}},
        {"_id": 0},
    ).to_list(500)

    results = []
    for hearing in stalled:
        hearing_id = hearing.get("hearing_id")
        try:
            result = await advance_or_escalate(db, hearing)
            results.append({"hearing_id": hearing_id, **result})
        except Exception as e:
            await log_audit(db, "matching.poll_error", None, {"hearing_id": hearing_id, "error": str(e)})
            results.append({"hearing_id": hearing_id, "status": "error", "error": str(e)})
    return results
