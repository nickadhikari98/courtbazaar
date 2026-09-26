"""A4 — targeted request to a counsel with negotiation switched off.

The frontend now routes that counsel's "Respond" to the Hearing Detail
(Accept at listed rate / Reject) instead of the Negotiation Module. These
pin the backend side of that flow, which had no direct coverage: the fixed
price is still enforced server-side, and only the targeted counsel can act.

Same conventions as test_negotiation.py (Motor directly, asyncio.run()).
"""
import asyncio
import os
import sys
import uuid

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hearings  # noqa: E402
import negotiation  # noqa: E402

LISTED_RATE = 2500.0


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _user(prefix):
    return {"user_id": f"test_negoff_{prefix}_{uuid.uuid4().hex[:10]}", "capabilities": ["can_practice_proxy_counsel"]}


class _Setup:
    def __init__(self):
        self.requester = _user("requester")
        self.counsel = _user("counsel")
        self.other_counsel = _user("other")
        self.hearing_ids = []
        self.profile_ids = []

    async def hearing(self, db, negotiation_enabled):
        """Targeted request; create_hearing_request snapshots the counsel's
        profile toggle onto hearing.negotiation_enabled. The profile's
        pricing is what accept_at_listed_rate reads (cheapest slot)."""
        await db.proxy_counsel_profiles.update_one(
            {"user_id": self.counsel["user_id"]},
            {"$set": {"negotiation_enabled": negotiation_enabled,
                      "pricing": {"district": {"morning": LISTED_RATE, "full_day": 4000.0}}}},
            upsert=True,
        )
        self.profile_ids.append(self.counsel["user_id"])
        hearing = await hearings.create_hearing_request(
            db, self.requester["user_id"], "court_tishazari", "2026-10-01", "Test case", 1500.0, None,
            target_advocate_id=self.counsel["user_id"],
        )
        assert hearing["negotiation_enabled"] is negotiation_enabled
        self.hearing_ids.append(hearing["hearing_id"])
        return hearing["hearing_id"]

    async def cleanup(self, db):
        if self.hearing_ids:
            await db.hearing_requests.delete_many({"hearing_id": {"$in": self.hearing_ids}})
            await db.negotiations.delete_many({"hearing_id": {"$in": self.hearing_ids}})
            await db.notification_events.delete_many({"related_entity_id": {"$in": self.hearing_ids}})
        if self.profile_ids:
            await db.proxy_counsel_profiles.delete_many({"user_id": {"$in": self.profile_ids}})


def _run(body):
    async def wrapper():
        db, s = _db(), _Setup()
        try:
            await body(db, s)
        finally:
            await s.cleanup(db)
    asyncio.run(wrapper())


async def _hearing(db, hearing_id):
    return await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})


async def _expect(status_code, coro):
    with pytest.raises(HTTPException) as exc_info:
        await coro
    assert exc_info.value.status_code == status_code
    return exc_info.value.detail


def test_negotiation_off_accept_locks_the_listed_rate():
    async def body(db, s):
        hearing_id = await s.hearing(db, negotiation_enabled=False)
        result = await hearings.accept_at_listed_rate(db, hearing_id, s.counsel)
        assert result == {"ok": True, "fee": LISTED_RATE}
        h = await _hearing(db, hearing_id)
        assert h["commercially_locked"] is True and h["fee"] == LISTED_RATE and h["status"] == "requested"
        # Nothing was negotiated: no negotiations doc was created by the shortcut.
        assert await db.negotiations.count_documents({"hearing_id": hearing_id}) == 0
        # Once locked it can't be accepted again or rejected.
        await _expect(400, hearings.accept_at_listed_rate(db, hearing_id, s.counsel))
        await _expect(400, hearings.reject_hearing_request(db, hearing_id, s.counsel))
    _run(body)


def test_negotiation_off_reject_works():
    async def body(db, s):
        hearing_id = await s.hearing(db, negotiation_enabled=False)
        await hearings.reject_hearing_request(db, hearing_id, s.counsel)
        assert (await _hearing(db, hearing_id))["status"] == "rejected"
    _run(body)


def test_negotiation_off_blocks_counter_offers_from_either_side():
    async def body(db, s):
        hearing_id = await s.hearing(db, negotiation_enabled=False)
        for who in (s.requester, s.counsel):
            detail = await _expect(400, negotiation.propose_offer(db, hearing_id, who, 3000.0, "counter"))
            assert "doesn't negotiate" in detail
        h = await _hearing(db, hearing_id)
        assert not h.get("commercially_locked") and h["fee"] == 1500.0
    _run(body)


def test_other_counsel_and_requester_cannot_accept_or_reject():
    async def body(db, s):
        for enabled in (False, True):
            hearing_id = await s.hearing(db, negotiation_enabled=enabled)
            before = await _hearing(db, hearing_id)
            for intruder in (s.other_counsel, s.requester):
                await _expect(403, hearings.accept_at_listed_rate(db, hearing_id, intruder))
                await _expect(403, hearings.reject_hearing_request(db, hearing_id, intruder))
            after = await _hearing(db, hearing_id)
            assert after["status"] == before["status"] and after.get("commercially_locked") == before.get("commercially_locked")
    _run(body)


def test_negotiation_on_still_offers_and_counters():
    """Unchanged ON path: opening offer, counsel's counter (propose_offer from
    the other side), then agreement locks the countered amount."""
    async def body(db, s):
        hearing_id = await s.hearing(db, negotiation_enabled=True)
        await negotiation.propose_offer(db, hearing_id, s.requester, 3000.0, "opening")
        await negotiation.propose_offer(db, hearing_id, s.counsel, 3500.0, "counter")
        neg = await negotiation.get_negotiation(db, hearing_id)
        assert neg["status"] == "open" and len(neg["offers"]) == 2
        await negotiation.accept_offer(db, hearing_id, neg["current_offer_id"], s.requester)
        h = await _hearing(db, hearing_id)
        assert h["commercially_locked"] is True and h["fee"] == 3500.0
    _run(body)


def test_listed_rate_shown_to_participants_of_a_fixed_price_offer_only():
    """hearing.fee is empty until Accept, so get/list attach the amount
    accept_at_listed_rate would lock — for the targeted counsel and the
    requester only, and only while the offer is still open."""
    async def body(db, s):
        hearing_id = await s.hearing(db, negotiation_enabled=False)
        for viewer in (s.counsel, s.requester):
            assert (await hearings.get_hearing_request(db, hearing_id, viewer))["listed_rate"] == LISTED_RATE
        listed = {h["hearing_id"]: h for h in await hearings.list_hearing_requests(db, s.counsel)}
        assert listed[hearing_id]["listed_rate"] == LISTED_RATE
        # Stored record is untouched — display only.
        assert "listed_rate" not in await _hearing(db, hearing_id)

        # Unpriced counsel: None, not an error.
        await db.proxy_counsel_profiles.update_one({"user_id": s.counsel["user_id"]}, {"$set": {"pricing": {}}})
        assert (await hearings.get_hearing_request(db, hearing_id, s.counsel))["listed_rate"] is None
        await db.proxy_counsel_profiles.update_one(
            {"user_id": s.counsel["user_id"]}, {"$set": {"pricing": {"district": {"morning": LISTED_RATE}}}})

        # Once accepted the real fee takes over and listed_rate is no longer attached.
        await hearings.accept_at_listed_rate(db, hearing_id, s.counsel)
        after = await hearings.get_hearing_request(db, hearing_id, s.counsel)
        assert "listed_rate" not in after and after["fee"] == LISTED_RATE
    _run(body)


def test_listed_rate_not_attached_for_negotiable_offers():
    async def body(db, s):
        hearing_id = await s.hearing(db, negotiation_enabled=True)
        assert "listed_rate" not in await hearings.get_hearing_request(db, hearing_id, s.counsel)
    _run(body)
