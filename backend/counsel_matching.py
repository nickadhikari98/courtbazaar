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
from typing import Optional

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
