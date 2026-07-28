"""Hearing Payment/Broadcast Reorder (Counsel Matching Agent roadmap M6).

Exercises hearings.py/escrow.py directly rather than through HTTP — same
reasoning as test_escrow_deferred_payee.py: the server.py endpoint wiring
(escrow.create_and_hold + the notify relocation) isn't itself state-machine
logic, so a black-box HTTP test isn't needed to verify the reorder. Plain
asyncio.run() wrappers, no pytest (not installed in this environment —
confirmed: `import pytest` fails here, so test_escrow_deferred_payee.py's
pytest.raises usage can't actually run in this environment either; these
tests use plain try/except instead, matching test_counsel_matching_*.py).

Each test creates its own throwaway users/hearing rows and cleans them up in
a finally block.
"""
import asyncio
import os
import sys
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hearings  # noqa: E402
import escrow  # noqa: E402
import negotiation  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _user(prefix):
    return {"user_id": f"test_m6_{prefix}_{uuid.uuid4().hex[:10]}"}


async def _hold_escrow(db, hearing_id, requester, fee, payee_user_id=None):
    """Mirrors what server.py's verify_hearing_payment does before calling
    mark_payment_confirmed — these tests call hearings.py directly, so they
    reproduce that one escrow call rather than going through HTTP."""
    return await escrow.create_and_hold(
        db, context_type="hearing", context_id=hearing_id, service_id=hearings.ESCROW_SERVICE_ID,
        matter_id=None, payer_user_id=requester["user_id"], payee_user_id=payee_user_id,
        amount=fee, platform_commission_pct=0.1,
        razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
    )


async def _cleanup(db, hearing_ids=()):
    if hearing_ids:
        await db.hearing_requests.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
        await db.escrow_transactions.delete_many({"context_id": {"$in": list(hearing_ids)}})
        await db.counsel_matching_log.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
        await db.negotiations.delete_many({"hearing_id": {"$in": list(hearing_ids)}})


def test_full_happy_path_new_order():
    async def body():
        db = _db()
        requester = _user("requester")
        counsel = _user("counsel")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            )
            hearing_id = hearing["hearing_id"]
            assert hearing["status"] == "requested"

            await hearings.initiate_payment(db, hearing_id, requester)
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "payment_pending"

            await _hold_escrow(db, hearing_id, requester, 1500.0, payee_user_id=None)
            result = await hearings.mark_payment_confirmed(db, hearing_id, requester)
            assert result["status"] == "broadcast"
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "broadcast"
            assert fetched["proxy_counsel_user_id"] is None

            accepted = await hearings.accept_hearing_request(db, hearing_id, counsel)
            assert accepted["status"] == "documents_shared"  # M12: auto-chains straight through, "accepted" is no longer the resting status
            assert accepted["proxy_counsel_user_id"] == counsel["user_id"]
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_cancel_from_requested_no_refund():
    async def body():
        db = _db()
        requester = _user("requester")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            )
            hearing_id = hearing["hearing_id"]
            result = await hearings.cancel_hearing_request(db, hearing_id, requester)
            assert result["ok"] is True
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "cancelled"
            escrow_doc = await db.escrow_transactions.find_one({"context_id": hearing_id})
            assert escrow_doc is None
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_cancel_from_payment_pending_no_refund():
    async def body():
        db = _db()
        requester = _user("requester")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            )
            hearing_id = hearing["hearing_id"]
            await hearings.initiate_payment(db, hearing_id, requester)
            result = await hearings.cancel_hearing_request(db, hearing_id, requester)
            assert result["ok"] is True
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "cancelled"
            escrow_doc = await db.escrow_transactions.find_one({"context_id": hearing_id})
            assert escrow_doc is None
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_cancel_from_broadcast_triggers_refund():
    """New case per the roadmap's M6 acceptance criteria — didn't exist
    before the reorder, since escrow was never held by the time a hearing
    reached "broadcast" under the old order."""
    async def body():
        db = _db()
        requester = _user("requester")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            )
            hearing_id = hearing["hearing_id"]
            await hearings.initiate_payment(db, hearing_id, requester)
            await _hold_escrow(db, hearing_id, requester, 1500.0, payee_user_id=None)
            await hearings.mark_payment_confirmed(db, hearing_id, requester)

            result = await hearings.cancel_hearing_request(db, hearing_id, requester)
            assert result["ok"] is True
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "cancelled"
            escrow_doc = await db.escrow_transactions.find_one({"context_id": hearing_id}, {"_id": 0})
            assert escrow_doc["status"] == "refunded"
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_cancel_from_accepted_triggers_refund():
    """Also a new case per the roadmap — "accepted" now happens after escrow
    is already held, unlike under the old order."""
    async def body():
        db = _db()
        requester = _user("requester")
        counsel = _user("counsel")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            )
            hearing_id = hearing["hearing_id"]
            await hearings.initiate_payment(db, hearing_id, requester)
            await _hold_escrow(db, hearing_id, requester, 1500.0, payee_user_id=None)
            await hearings.mark_payment_confirmed(db, hearing_id, requester)
            await hearings.accept_hearing_request(db, hearing_id, counsel)

            result = await hearings.cancel_hearing_request(db, hearing_id, requester)
            assert result["ok"] is True
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "cancelled"
            escrow_doc = await db.escrow_transactions.find_one({"context_id": hearing_id}, {"_id": 0})
            assert escrow_doc["status"] == "refunded"
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_accept_before_payment_returns_400():
    async def body():
        db = _db()
        requester = _user("requester")
        counsel = _user("counsel")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            )
            hearing_id = hearing["hearing_id"]
            try:
                await hearings.accept_hearing_request(db, hearing_id, counsel)
                assert False, "expected HTTPException"
            except HTTPException as e:
                assert e.status_code == 400
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_accept_during_payment_pending_returns_400():
    async def body():
        db = _db()
        requester = _user("requester")
        counsel = _user("counsel")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            )
            hearing_id = hearing["hearing_id"]
            await hearings.initiate_payment(db, hearing_id, requester)
            try:
                await hearings.accept_hearing_request(db, hearing_id, counsel)
                assert False, "expected HTTPException"
            except HTTPException as e:
                assert e.status_code == 400
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_initiate_payment_only_valid_from_requested():
    async def body():
        db = _db()
        requester = _user("requester")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            )
            hearing_id = hearing["hearing_id"]
            await hearings.initiate_payment(db, hearing_id, requester)  # requested -> payment_pending, OK
            try:
                await hearings.initiate_payment(db, hearing_id, requester)  # already payment_pending, should fail now
                assert False, "expected HTTPException"
            except HTTPException as e:
                assert e.status_code == 400
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_targeted_request_under_new_order():
    async def body():
        db = _db()
        requester = _user("requester")
        target_counsel = _user("target")
        other_counsel = _user("other")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
                target_advocate_id=target_counsel["user_id"],
            )
            hearing_id = hearing["hearing_id"]
            assert hearing["status"] == "requested"
            assert hearing["target_advocate_id"] == target_counsel["user_id"]

            # Negotiation Module: a targeted request must reach "agreed"
            # before payment can be initiated — see hearings.initiate_payment's
            # guard. Propose+accept here mirrors what the Negotiation Module UI
            # does before the customer ever reaches the pay button.
            await negotiation.propose_offer(db, hearing_id, requester, 1500.0, None)
            offer_id = (await negotiation.get_negotiation(db, hearing_id))["current_offer_id"]
            await negotiation.accept_offer(db, hearing_id, offer_id, target_counsel)

            await hearings.initiate_payment(db, hearing_id, requester)
            await _hold_escrow(db, hearing_id, requester, 1500.0, payee_user_id=None)
            await hearings.mark_payment_confirmed(db, hearing_id, requester)
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "broadcast"

            # Manual advocate selection: AI matching must never run for a
            # targeted request — no matching session should be opened at all.
            session = await db.counsel_matching_log.find_one({"hearing_id": hearing_id})
            assert session is None

            try:
                await hearings.accept_hearing_request(db, hearing_id, other_counsel)
                assert False, "expected HTTPException"
            except HTTPException as e:
                assert e.status_code == 403

            accepted = await hearings.accept_hearing_request(db, hearing_id, target_counsel)
            assert accepted["status"] == "documents_shared"  # M12: auto-chains straight through, "accepted" is no longer the resting status
            assert accepted["proxy_counsel_user_id"] == target_counsel["user_id"]
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_targeted_advocate_can_reject_during_negotiation_before_payment():
    async def body():
        db = _db()
        requester = _user("requester")
        target_counsel = _user("target")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
                target_advocate_id=target_counsel["user_id"],
            )
            hearing_id = hearing["hearing_id"]
            assert hearing["status"] == "requested"

            # Negotiation Module: reject must work pre-payment (status
            # "requested") — the advocate can walk away from a negotiation
            # before the customer has ever paid, not just from "broadcast".
            result = await hearings.reject_hearing_request(db, hearing_id, target_counsel)
            assert result["status"] == "rejected"
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "rejected"
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())
