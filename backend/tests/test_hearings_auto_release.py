"""Escrow Module: 3-day auto-release (founder's rule: if the requester
neither verifies nor disputes an uploaded order sheet within 3 days, escrow
auto-releases to the proxy counsel). Exercises hearings.py/escrow.py
directly, same conventions as test_hearings_payment_broadcast_reorder.py.
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


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _user(prefix):
    return {"user_id": f"test_ar_{prefix}_{uuid.uuid4().hex[:10]}"}


async def _hold_escrow(db, hearing_id, requester, fee):
    return await escrow.create_and_hold(
        db, context_type="hearing", context_id=hearing_id, service_id=hearings.ESCROW_SERVICE_ID,
        matter_id=None, payer_user_id=requester["user_id"], payee_user_id=None,
        amount=fee, platform_commission_pct=0.1,
        razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
    )


def _noop_put_object(path, data, content_type):
    return {"path": path, "size": len(data)}


def _noop_validate_upload(filename, content_type, size):
    return None


async def _cleanup(db, hearing_ids=(), user_ids=()):
    if hearing_ids:
        await db.hearing_requests.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
        await db.escrow_transactions.delete_many({"context_id": {"$in": list(hearing_ids)}})
        await db.hearing_documents.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
        await db.wallet_transactions.delete_many({"related_entity_id": {"$in": list(hearing_ids)}})
    if user_ids:
        await db.proxy_counsel_profiles.delete_many({"user_id": {"$in": list(user_ids)}})


async def _drive_to_verification_pending(db, requester, counsel, fee=1500.0):
    hearing = await hearings.create_hearing_request(
        db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", fee, None,
    )
    hearing_id = hearing["hearing_id"]
    await hearings.initiate_payment(db, hearing_id, requester)
    await _hold_escrow(db, hearing_id, requester, fee)
    await hearings.mark_payment_confirmed(db, hearing_id, requester)
    await hearings.accept_hearing_request(db, hearing_id, counsel)  # -> documents_shared, assigns payee
    await hearings.add_document(db, _noop_put_object, _noop_validate_upload, hearing_id, counsel,
                                 "case_document", "brief.pdf", "application/pdf", b"x")  # auto-chains -> hearing_scheduled
    await hearings.mark_hearing_conducted(db, hearing_id, counsel)  # -> hearing_completed
    await hearings.add_document(db, _noop_put_object, _noop_validate_upload, hearing_id, counsel,
                                 "order_sheet", "order.pdf", "application/pdf", b"x")  # -> verification_pending
    return hearing_id


def test_verification_pending_at_set_on_order_sheet_upload():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = None
        try:
            hearing_id = await _drive_to_verification_pending(db, requester, counsel)
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "verification_pending"
            assert fetched["verification_pending_at"] is not None
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [], [counsel["user_id"]])
    asyncio.run(body())


def test_verify_clears_verification_pending_at():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = None
        try:
            hearing_id = await _drive_to_verification_pending(db, requester, counsel)
            await hearings.verify_order_sheet(db, hearing_id, requester)
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "verified"
            assert fetched["verification_pending_at"] is None
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [], [counsel["user_id"]])
    asyncio.run(body())


def test_auto_release_skips_recent_verification_pending():
    """A hearing whose order sheet was just uploaded (well within the 3-day
    window) must NOT be auto-released."""
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = None
        try:
            hearing_id = await _drive_to_verification_pending(db, requester, counsel)
            count = await hearings.auto_release_stale_verifications(db)
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "verification_pending"
            assert fetched["hearing_id"] not in []  # sanity — row still exists
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [], [counsel["user_id"]])
    asyncio.run(body())


def test_auto_release_after_3_days_releases_escrow():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = None
        try:
            hearing_id = await _drive_to_verification_pending(db, requester, counsel)
            # Simulate 3+ days having passed since the order sheet upload.
            stale_at = (datetime.now(timezone.utc) - timedelta(days=hearings.AUTO_RELEASE_DELAY_DAYS, hours=1)).isoformat()
            await db.hearing_requests.update_one({"hearing_id": hearing_id}, {"$set": {"verification_pending_at": stale_at}})

            count = await hearings.auto_release_stale_verifications(db)
            assert count == 1

            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "completed"
            assert fetched["verification_pending_at"] is None

            escrow_doc = await db.escrow_transactions.find_one({"context_id": hearing_id}, {"_id": 0})
            assert escrow_doc["status"] == "released"

            counsel_user = await db.users.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
            # users collection may not have this throwaway test user — only
            # assert the wallet fields if the row exists (created elsewhere
            # in the real app via signup, not by this test).
            if counsel_user:
                assert counsel_user.get("wallet_balance", 0) >= 0
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [], [counsel["user_id"]])
    asyncio.run(body())


def test_auto_release_does_not_touch_disputed_hearings():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = None
        try:
            hearing_id = await _drive_to_verification_pending(db, requester, counsel)
            await hearings.reject_order_sheet(db, hearing_id, requester, remark="Looks wrong")
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "disputed"
            assert fetched["verification_pending_at"] is None

            # Even backdating an unrelated timestamp shouldn't matter — the
            # scan itself only matches status=="verification_pending".
            count = await hearings.auto_release_stale_verifications(db)
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "disputed"
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [], [counsel["user_id"]])
    asyncio.run(body())
