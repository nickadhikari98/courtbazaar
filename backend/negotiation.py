"""Negotiation Module — chat is `hearing_messages` (hearings.py, unchanged); this
module owns exactly the offer/counter-offer/agreement state, in its own
`negotiations` collection, the same one-collection-per-module split
hearings.py/escrow.py/counsel_matching.py already use.

One document per hearing_id (unique index, same idiom as
counsel_matching_log): an append-only `offers` history plus a `timeline`
event log the frontend merges with hearing_messages into one chat feed
(offer_proposed/negotiation_agreed events render as "Offer"/"Counter
Offer"/"System" entries there — this module has no idea that rendering
happens, it just appends generic events, same spirit as
counsel_matching.append_session_event).

Business rule (founder, Proxy Counsel negotiation milestone): proposing an
offer is that party's own implicit acceptance of it — only the OTHER party
can accept it, and doing so locks the negotiation permanently. A new offer
supersedes whatever was previously active. Once agreed, status is terminal:
no more offers, no reopening, and — per the commercial-lock rule — no
walking away either: accept_offer flips hearings.hearing_requests'
commercially_locked flag (see hearings.set_negotiated_fee) atomically
*before* this module's own status flips to "agreed", so
cancel_hearing_request/reject_hearing_request (hearings.py, unchanged)
refuse outright from that point on. Payment is the only forward action;
post-lock cancellation, if the business ever wants it, is a separate
workflow, not a reuse of the pre-negotiation cancel/reject actions. This
module still never implements a "decline this offer" or "reopen" action
because none was asked for.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

# Hearing statuses a negotiation can no longer meaningfully happen against —
# mirrors hearings.HEARING_STATUSES' terminal off-ramps for a pre-payment
# hearing (see hearings.py's module docstring).
_TERMINAL_HEARING_STATUSES = ("cancelled", "rejected", "expired")


def new_negotiation_id() -> str:
    return f"neg_{uuid.uuid4().hex[:12]}"


def new_offer_id() -> str:
    return f"offer_{uuid.uuid4().hex[:12]}"


async def ensure_indexes(db) -> None:
    await db.negotiations.create_index([("hearing_id", 1)], name="negotiation_hearing", unique=True)
    await db.negotiations.create_index([("negotiation_id", 1)], name="negotiation_id", unique=True)


def _check_negotiation_participant(hearing: dict, user: dict) -> None:
    if user.get("role") == "admin":
        return
    if user["user_id"] not in (hearing.get("requesting_user_id"), hearing.get("target_advocate_id")):
        raise HTTPException(403, "Only the requester and the targeted advocate can negotiate this hearing")


def _role_of(hearing: dict, user_id: str) -> str:
    return "customer" if hearing.get("requesting_user_id") == user_id else "counsel"


async def get_or_create_negotiation(db, hearing_id: str) -> dict:
    """Idempotent, same pattern as counsel_matching.get_or_create_matching_session
    — the unique index on hearing_id is the actual concurrency guard, not an
    application-level check-then-insert."""
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "negotiation_id": new_negotiation_id(),
        "hearing_id": hearing_id,
        "status": "open",  # open | agreed
        "offers": [],
        "current_offer_id": None,
        "locked_amount": None,
        "locked_at": None,
        "timeline": [],
        "created_at": now,
        "updated_at": now,
    }
    try:
        await db.negotiations.insert_one(doc)
    except DuplicateKeyError:
        existing = await db.negotiations.find_one({"hearing_id": hearing_id}, {"_id": 0})
        return existing
    doc.pop("_id", None)
    return doc


async def get_negotiation(db, hearing_id: str) -> Optional[dict]:
    return await db.negotiations.find_one({"hearing_id": hearing_id}, {"_id": 0})


async def get_negotiation_for_user(db, hearing_id: str, user: dict) -> dict:
    """Fetch-or-create + participant check bundled together — the one call
    server.py's GET endpoint needs, same shape as hearings.get_hearing_request
    bundling fetch+visibility. Kept separate from get_negotiation (used
    internally by propose_offer/accept_offer, and by hearings.initiate_payment's
    guard, neither of which wants a participant check re-run)."""
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    _check_negotiation_participant(hearing, user)
    return await get_or_create_negotiation(db, hearing_id)


async def _append_event(db, negotiation_id: str, event: str, detail: Optional[dict] = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.negotiations.update_one(
        {"negotiation_id": negotiation_id},
        {"$push": {"timeline": {"event": event, "detail": detail or {}, "at": now}}, "$set": {"updated_at": now}},
    )


async def _load_hearing_for_negotiation(db, hearing_id: str, user: dict) -> dict:
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    _check_negotiation_participant(hearing, user)
    if hearing["status"] in _TERMINAL_HEARING_STATUSES:
        raise HTTPException(400, "This request is no longer open for negotiation")
    return hearing


async def propose_offer(db, hearing_id: str, user: dict, amount: float, note: Optional[str]) -> dict:
    hearing = await _load_hearing_for_negotiation(db, hearing_id, user)
    negotiation = await get_or_create_negotiation(db, hearing_id)
    if negotiation["status"] != "open":
        raise HTTPException(400, "This negotiation is already agreed — no further offers are allowed")

    is_counter = negotiation.get("current_offer_id") is not None
    now = datetime.now(timezone.utc).isoformat()
    offer = {
        "offer_id": new_offer_id(),
        "amount": amount,
        "note": note,
        "proposed_by_user_id": user["user_id"],
        "proposed_by_role": _role_of(hearing, user["user_id"]),
        "status": "active",
        "created_at": now,
    }

    # Supersede whatever was active before this one, atomically with the
    # insert of the new offer, via the array positional operator — avoids a
    # separate read-modify-write race between two near-simultaneous proposals.
    await db.negotiations.update_one(
        {"negotiation_id": negotiation["negotiation_id"], "offers.status": "active"},
        {"$set": {"offers.$.status": "superseded"}},
    )
    await db.negotiations.update_one(
        {"negotiation_id": negotiation["negotiation_id"]},
        {"$push": {"offers": offer}, "$set": {"current_offer_id": offer["offer_id"], "updated_at": now}},
    )
    await _append_event(db, negotiation["negotiation_id"], "offer_proposed", {
        "offer_id": offer["offer_id"], "amount": amount, "note": note,
        "proposed_by_user_id": user["user_id"], "proposed_by_role": offer["proposed_by_role"],
        "is_counter": is_counter,
    })
    return await get_negotiation(db, hearing_id)


async def accept_offer(db, hearing_id: str, offer_id: str, user: dict) -> dict:
    hearing = await _load_hearing_for_negotiation(db, hearing_id, user)
    negotiation = await get_negotiation(db, hearing_id)
    if not negotiation:
        raise HTTPException(404, "No negotiation has been started for this hearing yet")
    if negotiation["status"] != "open":
        raise HTTPException(400, "This negotiation is already agreed")
    if negotiation.get("current_offer_id") != offer_id:
        raise HTTPException(409, "This offer is no longer the active one — refresh and try again")

    offer = next((o for o in negotiation["offers"] if o["offer_id"] == offer_id), None)
    if not offer or offer["status"] != "active":
        raise HTTPException(409, "This offer is no longer the active one — refresh and try again")
    if offer["proposed_by_user_id"] == user["user_id"]:
        raise HTTPException(403, "You already implicitly accepted your own offer — waiting on the other party")

    # Cross-collection commercial lock happens FIRST, before this negotiation
    # ever flips to "agreed" — it's the single serialization point against
    # hearings.cancel_hearing_request/reject_hearing_request (see
    # hearings.set_negotiated_fee's docstring). If the hearing was
    # cancelled/rejected a moment ago, or another accept already locked it,
    # this fails and we abort right here — the negotiation stays "open", so
    # an "agreed" negotiation can never end up sitting on a dead hearing.
    # Same cross-module call convention as counsel_matching.admin_assign_counsel
    # lazy-importing hearings — negotiation.py never writes hearing_requests
    # directly, hearings.py stays the only writer of its own collection.
    import hearings
    locked = await hearings.set_negotiated_fee(db, hearing_id, offer["amount"])
    if not locked:
        raise HTTPException(409, "This request's status changed — refresh and try again")

    now = datetime.now(timezone.utc).isoformat()
    updated = await db.negotiations.find_one_and_update(
        {"negotiation_id": negotiation["negotiation_id"], "status": "open", "current_offer_id": offer_id},
        {"$set": {
            "status": "agreed", "locked_amount": offer["amount"], "locked_at": now,
            "offers.$[o].status": "accepted", "updated_at": now,
        }},
        array_filters=[{"o.offer_id": offer_id}],
        projection={"_id": 0},
    )
    if not updated:
        # The hearing is now locked but this specific accept lost (a counter
        # offer raced in first) — no agreement actually landed, so roll the
        # lock back rather than leaving the hearing stuck uncancellable.
        await hearings.unlock_commercially(db, hearing_id)
        raise HTTPException(409, "This offer is no longer the active one — refresh and try again")

    await _append_event(db, negotiation["negotiation_id"], "negotiation_agreed", {
        "offer_id": offer_id, "amount": offer["amount"], "accepted_by_user_id": user["user_id"],
    })

    return await get_negotiation(db, hearing_id)
