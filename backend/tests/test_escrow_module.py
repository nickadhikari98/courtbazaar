"""Escrow Module (founder's rules 1-9): the Hiring Advocate's one-click
"Verify Hearing" (verify_and_release_payout) and the 3-day order-sheet
reminder scan (check_pending_order_sheets).

Same rationale/pattern as test_hearings_payment_broadcast_reorder.py: plain
asyncio.run() wrappers against a real Mongo instance, no HTTP layer. Test
setup jumps straight to the target hearing.status via a direct db write
where the preceding state-machine chain isn't itself under test (document
upload's auto-chain machinery is exercised by test_hearings_payment_
broadcast_reorder.py and test_negotiation.py already, not duplicated here).
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hearings  # noqa: E402
import escrow  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _user(prefix):
    return {"user_id": f"test_escrow_{prefix}_{uuid.uuid4().hex[:10]}"}


async def _hold_escrow(db, hearing_id, requester, fee, payee_user_id):
    return await escrow.create_and_hold(
        db, context_type="hearing", context_id=hearing_id, service_id=hearings.ESCROW_SERVICE_ID,
        matter_id=None, payer_user_id=requester["user_id"], payee_user_id=payee_user_id,
        amount=fee, platform_commission_pct=0.1,
        razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
    )


async def _make_hearing_awaiting_verification(db, requester, counsel, fee=1500.0):
    """Fast-forwards a targeted hearing straight to "verification_pending"
    with escrow already held for this counsel — the state this module's new
    functions actually operate on. The chain to get there (accept ->
    documents_shared -> ... -> hearing_completed -> order sheet upload) is
    already covered by other test files; jumping here via a direct write
    keeps this file focused on verify_and_release_payout/check_pending_
    order_sheets themselves."""
    hearing = await hearings.create_hearing_request(
        db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", fee, None,
        target_advocate_id=counsel["user_id"],
    )
    hearing_id = hearing["hearing_id"]
    await _hold_escrow(db, hearing_id, requester, fee, payee_user_id=counsel["user_id"])
    await db.hearing_requests.update_one(
        {"hearing_id": hearing_id},
        {"$set": {
            "status": "verification_pending", "proxy_counsel_user_id": counsel["user_id"],
            "payment_confirmed_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return hearing_id


async def _cleanup(db, hearing_ids=(), user_ids=()):
    if hearing_ids:
        await db.hearing_requests.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
        await db.escrow_transactions.delete_many({"context_id": {"$in": list(hearing_ids)}})
    if user_ids:
        await db.proxy_counsel_profiles.delete_many({"user_id": {"$in": list(user_ids)}})
        await db.notification_events.delete_many({"user_id": {"$in": list(user_ids)}})
        await db.users.delete_many({"user_id": {"$in": list(user_ids)}})


def test_verify_and_release_payout_happy_path():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = await _make_hearing_awaiting_verification(db, requester, counsel)
        try:
            await db.proxy_counsel_profiles.insert_one({"user_id": counsel["user_id"], "cases_completed": 0})
            result = await hearings.verify_and_release_payout(db, hearing_id, requester)
            assert result["status"] == "completed"
            assert result["escrow"]["status"] == "released"

            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "completed"

            profile = await db.proxy_counsel_profiles.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
            assert profile["cases_completed"] == 1

            escrow_doc = await db.escrow_transactions.find_one({"context_id": hearing_id}, {"_id": 0})
            assert escrow_doc["status"] == "released"
        finally:
            await _cleanup(db, [hearing_id], [counsel["user_id"]])
    asyncio.run(body())


def test_verify_and_release_payout_forbidden_for_non_requester():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = await _make_hearing_awaiting_verification(db, requester, counsel)
        try:
            try:
                await hearings.verify_and_release_payout(db, hearing_id, counsel)
                assert False, "expected HTTPException"
            except HTTPException as e:
                assert e.status_code == 403

            # Nothing should have moved — still awaiting verification, escrow untouched.
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "verification_pending"
            escrow_doc = await db.escrow_transactions.find_one({"context_id": hearing_id}, {"_id": 0})
            assert escrow_doc["status"] == "held"
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_verify_and_release_payout_rejected_when_not_awaiting_verification():
    async def body():
        db = _db()
        requester = _user("requester")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            )
            hearing_id = hearing["hearing_id"]  # still "requested" — nowhere near verification
            try:
                await hearings.verify_and_release_payout(db, hearing_id, requester)
                assert False, "expected HTTPException"
            except HTTPException as e:
                assert e.status_code == 400
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_check_pending_order_sheets_notifies_after_three_days():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing = await hearings.create_hearing_request(
            db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            target_advocate_id=counsel["user_id"],
        )
        hearing_id = hearing["hearing_id"]
        try:
            await db.users.insert_one({"user_id": counsel["user_id"], "name": "Test Counsel"})
            stale = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
            await db.hearing_requests.update_one(
                {"hearing_id": hearing_id},
                {"$set": {"status": "hearing_scheduled", "proxy_counsel_user_id": counsel["user_id"], "payment_confirmed_at": stale}},
            )
            count = await hearings.check_pending_order_sheets(db)
            assert count >= 1

            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["order_sheet_reminder_sent_at"] is not None

            event = await db.notification_events.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
            assert event is not None
            assert "Escrow" in event["body"]

            # Second scan must not re-notify the same hearing.
            before = event["notification_id"]
            await hearings.check_pending_order_sheets(db)
            events = await db.notification_events.find({"user_id": counsel["user_id"]}, {"_id": 0}).to_list(10)
            assert len(events) == 1
            assert events[0]["notification_id"] == before
        finally:
            await _cleanup(db, [hearing_id], [counsel["user_id"]])
    asyncio.run(body())


def test_check_pending_order_sheets_skips_recent_payment():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing = await hearings.create_hearing_request(
            db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            target_advocate_id=counsel["user_id"],
        )
        hearing_id = hearing["hearing_id"]
        try:
            await db.users.insert_one({"user_id": counsel["user_id"], "name": "Test Counsel"})
            recent = datetime.now(timezone.utc).isoformat()  # paid moments ago, well within the 3-day window
            await db.hearing_requests.update_one(
                {"hearing_id": hearing_id},
                {"$set": {"status": "hearing_scheduled", "proxy_counsel_user_id": counsel["user_id"], "payment_confirmed_at": recent}},
            )
            await hearings.check_pending_order_sheets(db)
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["order_sheet_reminder_sent_at"] is None
            event = await db.notification_events.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
            assert event is None
        finally:
            await _cleanup(db, [hearing_id], [counsel["user_id"]])
    asyncio.run(body())
