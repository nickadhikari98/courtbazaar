"""Notification Dispatch Engine (roadmap M9).

Unlike M6/M7/M8, dispatch_notifications does real I/O (resolves recipients
from db.users, calls notify()/record_notification_event()), so this follows
the M2/M4/M5 pattern: plain asyncio.run() wrappers against a real Mongo
instance, no pytest-asyncio needed. Each test creates its own throwaway
users/hearing_requests rows and cleans them up in a finally block.
"""
import asyncio
import os
import sys
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import counsel_matching  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


async def _make_user(db, with_contact=True):
    user_id = f"test_dispatch_user_{uuid.uuid4().hex[:10]}"
    doc = {"user_id": user_id, "name": "Test Counsel"}
    if with_contact:
        doc.update({"phone": "9123456780", "email": f"{user_id}@cbtest.in"})
    await db.users.insert_one(doc)
    return user_id


def _batch_entry(counsel_user_id, hearing_id="test_hearing_1", court_id="court_tishazari",
                  hearing_date="2026-08-01", fee=1500.0):
    return {
        "counsel_user_id": counsel_user_id, "hearing_id": hearing_id, "court_id": court_id,
        "hearing_date": hearing_date, "fee": fee, "confidence_score": 0.8, "event_type": "hearing_offer",
    }


async def _cleanup(db, user_ids=(), hearing_ids=()):
    if user_ids:
        await db.users.delete_many({"user_id": {"$in": list(user_ids)}})
        await db.notification_events.delete_many({"user_id": {"$in": list(user_ids)}})
    if hearing_ids:
        await db.hearing_requests.delete_many({"hearing_id": {"$in": list(hearing_ids)}})


def test_dispatch_empty_batch_returns_empty():
    async def body():
        db = _db()
        result = await counsel_matching.dispatch_notifications(db, [])
        assert result == []
    asyncio.run(body())


def test_dispatch_successful_delivery_for_existing_user():
    async def body():
        db = _db()
        user_id = await _make_user(db)
        try:
            batch = [_batch_entry(user_id)]
            result = await counsel_matching.dispatch_notifications(db, batch)
            assert len(result) == 1
            assert result[0]["counsel_user_id"] == user_id
            assert result[0]["status"] == "dispatched"
            assert isinstance(result[0]["channel_results"], list)
            for channel_result in result[0]["channel_results"]:
                assert channel_result["status"] in ("sent", "mocked")

            event = await db.notification_events.find_one({"user_id": user_id}, {"_id": 0})
            assert event is not None
            assert event["related_entity_type"] == "hearing"
            assert event["related_entity_id"] == "test_hearing_1"
        finally:
            await _cleanup(db, [user_id])
    asyncio.run(body())


def test_dispatch_missing_recipient_marked_failed():
    async def body():
        db = _db()
        batch = [_batch_entry("nonexistent_user_xyz")]
        result = await counsel_matching.dispatch_notifications(db, batch)
        assert len(result) == 1
        assert result[0]["status"] == "failed"
        assert "not found" in result[0]["reason"]
        assert result[0]["channel_results"] == []
    asyncio.run(body())


def test_dispatch_continues_after_one_failure():
    async def body():
        db = _db()
        good_user = await _make_user(db)
        try:
            batch = [_batch_entry("nonexistent_user_xyz"), _batch_entry(good_user)]
            result = await counsel_matching.dispatch_notifications(db, batch)
            assert len(result) == 2
            assert result[0]["status"] == "failed"
            assert result[1]["status"] == "dispatched"
            assert result[1]["counsel_user_id"] == good_user
        finally:
            await _cleanup(db, [good_user])
    asyncio.run(body())


def test_dispatch_preserves_order():
    async def body():
        db = _db()
        u1 = await _make_user(db)
        u2 = await _make_user(db)
        u3 = await _make_user(db)
        try:
            batch = [_batch_entry(u1), _batch_entry(u2), _batch_entry(u3)]
            result = await counsel_matching.dispatch_notifications(db, batch)
            assert [r["counsel_user_id"] for r in result] == [u1, u2, u3]
        finally:
            await _cleanup(db, [u1, u2, u3])
    asyncio.run(body())


def test_dispatch_never_touches_hearing_status():
    async def body():
        db = _db()
        user_id = await _make_user(db)
        hearing_id = f"test_hearing_{uuid.uuid4().hex[:10]}"
        try:
            await db.hearing_requests.insert_one({
                "hearing_id": hearing_id, "status": "broadcast", "proxy_counsel_user_id": None,
            })
            batch = [_batch_entry(user_id, hearing_id=hearing_id)]
            await counsel_matching.dispatch_notifications(db, batch)

            hearing_after = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert hearing_after["status"] == "broadcast"
            assert hearing_after["proxy_counsel_user_id"] is None
        finally:
            await _cleanup(db, [user_id], [hearing_id])
    asyncio.run(body())


def test_dispatch_recipient_with_no_contact_info_still_dispatched_with_empty_channels():
    async def body():
        db = _db()
        user_id = await _make_user(db, with_contact=False)
        try:
            batch = [_batch_entry(user_id)]
            result = await counsel_matching.dispatch_notifications(db, batch)
            assert result[0]["status"] == "dispatched"
            assert result[0]["channel_results"] == []  # no phone/email -> notify() attempts nothing
        finally:
            await _cleanup(db, [user_id])
    asyncio.run(body())
