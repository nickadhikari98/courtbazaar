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
from typing import List, Optional

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
