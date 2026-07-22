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
from datetime import datetime, timezone
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
