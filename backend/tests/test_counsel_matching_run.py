"""Matching Orchestration — Tier 1 (roadmap M10).

run_matching/notify_tier only compose the already-tested M4-M9 pipeline
(session ledger, discover_candidates, score_candidates,
select_top_candidates, prepare_notification_batch, dispatch_notifications) —
this file exercises the new orchestration/persistence glue only, not
re-verifying pipeline-stage correctness already covered by
test_counsel_matching_discovery.py / _scoring.py / _selection.py /
_notification_batch.py / _dispatch.py.

Same asyncio.run()-against-real-Mongo pattern as the M9 dispatch tests
(plain asyncio, no pytest-asyncio) since run_matching does real I/O.
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


async def _make_counsel(db, court_id="court_tishazari", rating=4.5, cases_completed=10):
    user_id = f"test_run_counsel_{uuid.uuid4().hex[:10]}"
    await db.users.insert_one({
        "user_id": user_id, "name": "Test Counsel", "phone": "9123456780", "email": f"{user_id}@cbtest.in",
    })
    await db.proxy_counsel_profiles.insert_one({
        "user_id": user_id, "kyc_status": "approved", "bar_council_verified": True,
        "availability_mode": True, "rating": rating, "cases_completed": cases_completed,
        "experience_years": 5, "instant_booking": False, "courts": [court_id],
    })
    return user_id


async def _make_hearing(db, court_id="court_tishazari", fee=1500.0, status="broadcast"):
    hearing_id = f"test_run_hearing_{uuid.uuid4().hex[:10]}"
    doc = {
        "hearing_id": hearing_id, "requesting_user_id": "test_run_requester", "proxy_counsel_user_id": None,
        "court_id": court_id, "hearing_date": "2026-08-01", "case_details": "Test case", "fee": fee,
        "status": status, "declined_by": [],
    }
    await db.hearing_requests.insert_one(dict(doc))
    return doc


async def _cleanup(db, user_ids=(), hearing_ids=(), match_ids=()):
    if user_ids:
        await db.users.delete_many({"user_id": {"$in": list(user_ids)}})
        await db.proxy_counsel_profiles.delete_many({"user_id": {"$in": list(user_ids)}})
        await db.notification_events.delete_many({"user_id": {"$in": list(user_ids)}})
    if hearing_ids:
        await db.hearing_requests.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
        await db.audit_log.delete_many({"details.hearing_id": {"$in": list(hearing_ids)}})
    if match_ids:
        await db.counsel_matching_log.delete_many({"match_id": {"$in": list(match_ids)}})


def test_run_matching_notifies_top_5_of_8_eligible():
    async def body():
        db = _db()
        hearing = await _make_hearing(db)
        counsel_ids = [await _make_counsel(db) for _ in range(8)]
        match_id = None
        try:
            result = await counsel_matching.run_matching(db, hearing)
            match_id = result["match_id"]
            assert result["status"] == "notified"
            assert result["tier"] == 1
            assert len(result["notified_counsel_ids"]) == 5
            assert result["match_confidence"] is not None
            assert result["match_tier_deadline_at"] is not None
            assert len(result["dispatch_results"]) == 5

            hearing_after = await db.hearing_requests.find_one({"hearing_id": hearing["hearing_id"]}, {"_id": 0})
            assert hearing_after["match_id"] == match_id
            assert hearing_after["match_tier"] == 1
            assert len(hearing_after["notified_counsel_ids"]) == 5
            assert hearing_after["match_confidence"] == result["match_confidence"]
            assert hearing_after["match_tier_deadline_at"] == result["match_tier_deadline_at"]
            # Isolation: M10 must never touch status or assignment.
            assert hearing_after["status"] == "broadcast"
            assert hearing_after["proxy_counsel_user_id"] is None

            session = await db.counsel_matching_log.find_one({"match_id": match_id}, {"_id": 0})
            assert session["status"] == "in_progress"
            assert session["hearing_id"] == hearing["hearing_id"]
            assert len(session["tiers"]) == 1
            assert session["tiers"][0]["tier"] == 1
            assert len(session["tiers"][0]["notified_counsel_ids"]) == 5
            assert any(e["event"] == "tier_notified" for e in session["timeline"])

            audit_entry = await db.audit_log.find_one({"action": "matching.tier_notified", "details.hearing_id": hearing["hearing_id"]})
            assert audit_entry is not None
        finally:
            await _cleanup(db, counsel_ids, [hearing["hearing_id"]], [match_id] if match_id else [])
    asyncio.run(body())


def test_run_matching_notifies_all_of_smaller_pool():
    async def body():
        db = _db()
        hearing = await _make_hearing(db)
        counsel_ids = [await _make_counsel(db) for _ in range(3)]
        match_id = None
        try:
            result = await counsel_matching.run_matching(db, hearing)
            match_id = result["match_id"]
            assert result["status"] == "notified"
            assert result["tier"] == 1
            assert len(result["notified_counsel_ids"]) == 3
            assert set(result["notified_counsel_ids"]) == set(counsel_ids)

            hearing_after = await db.hearing_requests.find_one({"hearing_id": hearing["hearing_id"]}, {"_id": 0})
            assert len(hearing_after["notified_counsel_ids"]) == 3
        finally:
            await _cleanup(db, counsel_ids, [hearing["hearing_id"]], [match_id] if match_id else [])
    asyncio.run(body())


def test_run_matching_zero_eligible_escalates_without_touching_hearing():
    async def body():
        db = _db()
        hearing = await _make_hearing(db)
        match_id = None
        try:
            result = await counsel_matching.run_matching(db, hearing)
            match_id = result["match_id"]
            assert result["status"] == "escalated"
            assert result["tier"] is None
            assert result["notified_counsel_ids"] == []
            assert result["dispatch_results"] == []

            session = await db.counsel_matching_log.find_one({"match_id": match_id}, {"_id": 0})
            assert session["status"] == "escalated"
            assert session["final_decision"] == "no_eligible_candidates"
            assert session["tiers"] == []

            # No tier/notification fields should appear on the hearing at all.
            hearing_after = await db.hearing_requests.find_one({"hearing_id": hearing["hearing_id"]}, {"_id": 0})
            assert "match_tier" not in hearing_after
            assert "notified_counsel_ids" not in hearing_after
            assert "match_confidence" not in hearing_after
            assert hearing_after["status"] == "broadcast"
            assert hearing_after["proxy_counsel_user_id"] is None

            audit_entry = await db.audit_log.find_one({"action": "matching.escalated", "details.hearing_id": hearing["hearing_id"]})
            assert audit_entry is not None
        finally:
            await _cleanup(db, [], [hearing["hearing_id"]], [match_id] if match_id else [])
    asyncio.run(body())


def test_notify_tier_rejects_tier_beyond_one():
    async def body():
        db = _db()
        hearing = await _make_hearing(db)
        counsel_ids = [await _make_counsel(db)]
        match_id = None
        try:
            session = await counsel_matching.get_or_create_matching_session(db, hearing["hearing_id"])
            match_id = session["match_id"]
            ranked = counsel_matching.score_candidates(
                hearing, await db.proxy_counsel_profiles.find({"user_id": {"$in": counsel_ids}}, {"_id": 0}).to_list(10),
            )
            try:
                await counsel_matching.notify_tier(db, hearing, ranked, tier=2, tier_size=5)
                assert False, "expected NotImplementedError"
            except NotImplementedError:
                pass
        finally:
            await _cleanup(db, counsel_ids, [hearing["hearing_id"]], [match_id] if match_id else [])
    asyncio.run(body())
