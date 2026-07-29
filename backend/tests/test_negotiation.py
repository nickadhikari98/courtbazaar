"""Negotiation Module — offer/counter-offer/agreement (negotiation.py).

Same rationale/style as test_hearings_payment_broadcast_reorder.py: exercises
negotiation.py/hearings.py directly via Motor with plain asyncio.run()
wrappers, no HTTP layer. Each test creates its own throwaway requester/
counsel/hearing rows and cleans them up in a finally block.
"""
import asyncio
import os
import sys
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hearings  # noqa: E402
import negotiation  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _user(prefix):
    return {"user_id": f"test_neg_{prefix}_{uuid.uuid4().hex[:10]}", "capabilities": ["can_practice_proxy_counsel"]}


async def _make_hearing(db, requester, counsel):
    hearing = await hearings.create_hearing_request(
        db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
        target_advocate_id=counsel["user_id"],
    )
    return hearing["hearing_id"]


async def _cleanup(db, hearing_ids=()):
    if hearing_ids:
        await db.hearing_requests.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
        await db.negotiations.delete_many({"hearing_id": {"$in": list(hearing_ids)}})


def test_propose_then_accept_locks_and_sets_fee():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = await _make_hearing(db, requester, counsel)
        try:
            await negotiation.propose_offer(db, hearing_id, requester, 3000.0, "Opening offer")
            neg = await negotiation.get_negotiation(db, hearing_id)
            offer_id = neg["current_offer_id"]
            assert neg["status"] == "open"

            result = await negotiation.accept_offer(db, hearing_id, offer_id, counsel)
            assert result["status"] == "agreed"
            assert result["locked_amount"] == 3000.0
            assert result["offers"][0]["status"] == "accepted"

            hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert hearing["fee"] == 3000.0
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_counter_offer_supersedes_previous():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = await _make_hearing(db, requester, counsel)
        try:
            await negotiation.propose_offer(db, hearing_id, requester, 3000.0, None)
            first_offer_id = (await negotiation.get_negotiation(db, hearing_id))["current_offer_id"]

            await negotiation.propose_offer(db, hearing_id, counsel, 3500.0, "Counter")
            neg = await negotiation.get_negotiation(db, hearing_id)
            assert neg["current_offer_id"] != first_offer_id
            by_id = {o["offer_id"]: o for o in neg["offers"]}
            assert by_id[first_offer_id]["status"] == "superseded"
            assert by_id[neg["current_offer_id"]]["status"] == "active"
            assert by_id[neg["current_offer_id"]]["amount"] == 3500.0

            offer_events = [e for e in neg["timeline"] if e["event"] == "offer_proposed"]
            assert offer_events[0]["detail"]["is_counter"] is False
            assert offer_events[1]["detail"]["is_counter"] is True
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_self_accept_is_forbidden():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = await _make_hearing(db, requester, counsel)
        try:
            await negotiation.propose_offer(db, hearing_id, requester, 3000.0, None)
            offer_id = (await negotiation.get_negotiation(db, hearing_id))["current_offer_id"]
            with pytest.raises(HTTPException) as exc_info:
                await negotiation.accept_offer(db, hearing_id, offer_id, requester)
            assert exc_info.value.status_code == 403
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_non_participant_is_forbidden():
    async def body():
        db = _db()
        requester, counsel, stranger = _user("requester"), _user("counsel"), _user("stranger")
        hearing_id = await _make_hearing(db, requester, counsel)
        try:
            with pytest.raises(HTTPException) as exc_info:
                await negotiation.propose_offer(db, hearing_id, stranger, 3000.0, None)
            assert exc_info.value.status_code == 403
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_accepting_a_stale_offer_conflicts():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = await _make_hearing(db, requester, counsel)
        try:
            await negotiation.propose_offer(db, hearing_id, requester, 3000.0, None)
            stale_offer_id = (await negotiation.get_negotiation(db, hearing_id))["current_offer_id"]
            await negotiation.propose_offer(db, hearing_id, counsel, 3500.0, None)

            with pytest.raises(HTTPException) as exc_info:
                await negotiation.accept_offer(db, hearing_id, stale_offer_id, requester)
            assert exc_info.value.status_code == 409
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_no_further_offers_once_agreed():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = await _make_hearing(db, requester, counsel)
        try:
            await negotiation.propose_offer(db, hearing_id, requester, 3000.0, None)
            offer_id = (await negotiation.get_negotiation(db, hearing_id))["current_offer_id"]
            await negotiation.accept_offer(db, hearing_id, offer_id, counsel)

            with pytest.raises(HTTPException) as exc_info:
                await negotiation.propose_offer(db, hearing_id, counsel, 4000.0, None)
            assert exc_info.value.status_code == 400
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_negotiation_offer_amount_must_be_positive():
    from server import NegotiationOfferCreate
    with pytest.raises(ValidationError):
        NegotiationOfferCreate(amount=0)
    with pytest.raises(ValidationError):
        NegotiationOfferCreate(amount=-100)
    assert NegotiationOfferCreate(amount=100).amount == 100


def test_agreement_commercially_locks_hearing_and_blocks_cancel_reject():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = await _make_hearing(db, requester, counsel)
        try:
            await negotiation.propose_offer(db, hearing_id, requester, 3000.0, None)
            offer_id = (await negotiation.get_negotiation(db, hearing_id))["current_offer_id"]
            await negotiation.accept_offer(db, hearing_id, offer_id, counsel)

            hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert hearing["commercially_locked"] is True
            assert hearing["status"] == "requested"  # lock doesn't move status — payment still the only forward action

            with pytest.raises(HTTPException) as exc_info:
                await hearings.cancel_hearing_request(db, hearing_id, requester)
            assert exc_info.value.status_code == 400

            with pytest.raises(HTTPException) as exc_info:
                await hearings.reject_hearing_request(db, hearing_id, counsel)
            assert exc_info.value.status_code == 400

            # Neither rejected attempt should have moved the status.
            hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert hearing["status"] == "requested"
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_accept_offer_aborts_without_agreeing_when_hearing_already_locked():
    """Simulates the race directly: something else (another accept, in
    practice) already flipped commercially_locked before this accept_offer
    call reaches its own lock attempt. It must abort — negotiation must
    never end up "agreed" once that happens."""
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = await _make_hearing(db, requester, counsel)
        try:
            await negotiation.propose_offer(db, hearing_id, requester, 3000.0, None)
            offer_id = (await negotiation.get_negotiation(db, hearing_id))["current_offer_id"]

            locked = await hearings.set_negotiated_fee(db, hearing_id, 9999.0)
            assert locked is True

            with pytest.raises(HTTPException) as exc_info:
                await negotiation.accept_offer(db, hearing_id, offer_id, counsel)
            assert exc_info.value.status_code == 409

            neg = await negotiation.get_negotiation(db, hearing_id)
            assert neg["status"] == "open"  # never flipped to agreed
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_accept_offer_rolls_back_lock_when_offer_goes_stale_after_locking(monkeypatch):
    """The narrower race: this accept_offer call wins the hearing lock, but
    a counter-offer lands before its own negotiation-side CAS runs, so that
    CAS loses. The hearing must not stay stuck commercially locked with no
    agreement to show for it — set_negotiated_fee is monkeypatched to inject
    the counter-offer at the exact point the real race would land it."""
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = await _make_hearing(db, requester, counsel)
        try:
            await negotiation.propose_offer(db, hearing_id, requester, 3000.0, None)
            offer_id = (await negotiation.get_negotiation(db, hearing_id))["current_offer_id"]

            import hearings as hearings_module
            real_set_negotiated_fee = hearings_module.set_negotiated_fee

            async def racing_set_negotiated_fee(db_, hid, amount):
                result = await real_set_negotiated_fee(db_, hid, amount)
                # Land a counter-offer right after the lock succeeds, before
                # negotiation.accept_offer's own CAS runs — same effect as a
                # second request racing in on the negotiations collection.
                await negotiation.propose_offer(db_, hid, requester, 3500.0, "Racing counter")
                return result

            # negotiation.accept_offer does `import hearings` lazily inside the
            # function body — same module object as hearings_module (Python
            # caches imports in sys.modules), so patching the attribute here
            # is visible to that call too.
            monkeypatch.setattr(hearings_module, "set_negotiated_fee", racing_set_negotiated_fee)

            with pytest.raises(HTTPException) as exc_info:
                await negotiation.accept_offer(db, hearing_id, offer_id, counsel)
            assert exc_info.value.status_code == 409

            neg = await negotiation.get_negotiation(db, hearing_id)
            assert neg["status"] == "open"  # the counter-offer, not an agreement

            hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert hearing["commercially_locked"] is False  # rolled back — still cancellable

            result = await hearings.cancel_hearing_request(db, hearing_id, requester)
            assert result["ok"] is True
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_initiate_payment_blocked_until_agreed_then_succeeds():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = await _make_hearing(db, requester, counsel)
        try:
            with pytest.raises(HTTPException) as exc_info:
                await hearings.initiate_payment(db, hearing_id, requester)
            assert exc_info.value.status_code == 400

            await negotiation.propose_offer(db, hearing_id, requester, 3000.0, None)
            offer_id = (await negotiation.get_negotiation(db, hearing_id))["current_offer_id"]
            await negotiation.accept_offer(db, hearing_id, offer_id, counsel)

            result = await hearings.initiate_payment(db, hearing_id, requester)
            assert result["status"] == "payment_pending"
            assert result["fee"] == 3000.0
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_broadcast_hearing_pays_without_negotiation():
    """Broadcast requests (no target_advocate_id) never negotiate — the
    frontend's payment-card gate (HearingDetailDialog.jsx) relies on this
    exemption matching hearings.initiate_payment exactly: it only requires
    commercially_locked when target_advocate_id is set, otherwise a fee set
    at creation is enough."""
    async def body():
        db = _db()
        requester = _user("requester")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
                target_advocate_id=None,
            )
            hearing_id = hearing["hearing_id"]
            assert hearing["commercially_locked"] is False

            neg = await negotiation.get_negotiation(db, hearing_id)
            assert neg is None  # no negotiation record ever needed to exist for this hearing

            result = await hearings.initiate_payment(db, hearing_id, requester)
            assert result["status"] == "payment_pending"
            assert result["fee"] == 1500.0
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())
