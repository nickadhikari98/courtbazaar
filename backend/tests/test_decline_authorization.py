"""PUT /hearing-requests/{id}/decline — only a counsel the request was
actually offered to may decline it.

QA finding: decline_hearing_request did a bare $addToSet on any hearing_id
for any proxy counsel, so a counsel could "decline" requests never sent to
them (and arbitrary/closed hearings). Authorization now reads the existing
notification record — hearing.notified_counsel_ids (current tier) plus
counsel_matching_log.tiers[].notified_counsel_ids (earlier tiers) — rather
than inventing a new one.

Notification state is written directly, in exactly the shape notify_tier
writes it: candidate discovery isn't court-scoped, so running the real
waterfall against a shared test DB would notify whichever leftover counsel
score highest. Never lets every notified counsel decline, so
maybe_early_advance never escalates/notifies anyone else.

Same pattern as test_escrow_notifications.py: server.py endpoint functions
called directly with server.db patched to a per-test client.
"""
import asyncio
import os
import sys
import unittest.mock
import uuid

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hearings  # noqa: E402
import server  # noqa: E402

COUNSEL_CAPS = ["can_practice_proxy_counsel"]


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _counsel(prefix):
    return {"user_id": f"test_decline_{prefix}_{uuid.uuid4().hex[:10]}", "role": "advocate", "capabilities": list(COUNSEL_CAPS)}


def _client(prefix="client"):
    return {"user_id": f"test_decline_{prefix}_{uuid.uuid4().hex[:10]}", "role": "customer", "capabilities": []}


class _Setup:
    """A broadcast (untargeted) hearing whose tier-1 notification went to
    `notified_a` and `notified_b`."""

    def __init__(self):
        self.requester = _client("requester")
        self.notified_a = _counsel("notified_a")
        self.notified_b = _counsel("notified_b")
        self.unrelated = _counsel("unrelated")
        self.hearing_ids = []

    async def hearing(self, db, status="broadcast", target=None, tiers=None, current_tier_ids=None):
        hearing_id = f"test_decline_hearing_{uuid.uuid4().hex[:10]}"
        tier1 = [self.notified_a["user_id"], self.notified_b["user_id"]]
        await db.hearing_requests.insert_one({
            "hearing_id": hearing_id, "requesting_user_id": self.requester["user_id"], "proxy_counsel_user_id": None,
            "court_id": "court_tishazari", "hearing_date": "2026-08-01", "case_details": "Test case", "fee": 1500.0,
            "status": status, "declined_by": [], "target_advocate_id": target,
            "match_tier": 1, "notified_counsel_ids": tier1 if current_tier_ids is None else current_tier_ids,
            "timeline": [],
        })
        await db.counsel_matching_log.insert_one({
            "match_id": f"test_decline_match_{uuid.uuid4().hex[:10]}", "hearing_id": hearing_id,
            "tiers": tiers if tiers is not None else [{"tier": 1, "notified_counsel_ids": tier1}],
        })
        self.hearing_ids.append(hearing_id)
        return hearing_id

    async def cleanup(self, db):
        if self.hearing_ids:
            await db.hearing_requests.delete_many({"hearing_id": {"$in": self.hearing_ids}})
            await db.counsel_matching_log.delete_many({"hearing_id": {"$in": self.hearing_ids}})
            await db.audit_log.delete_many({"details.hearing_id": {"$in": self.hearing_ids}})


def _run(body):
    async def wrapper():
        db = _db()
        setup = _Setup()
        with unittest.mock.patch.object(server, "db", db):
            try:
                await body(db, setup)
            finally:
                await setup.cleanup(db)
    asyncio.run(wrapper())


async def _declined_by(db, hearing_id):
    return (await db.hearing_requests.find_one({"hearing_id": hearing_id}))["declined_by"]


async def _expect(status_code, coro):
    with pytest.raises(HTTPException) as exc_info:
        await coro
    assert exc_info.value.status_code == status_code
    return exc_info.value.detail


def test_notified_counsel_can_decline_and_request_leaves_their_pool():
    async def body(db, s):
        hearing_id = await s.hearing(db)
        pool = {h["hearing_id"]: h for h in await hearings.list_hearing_requests(db, s.notified_a)}
        assert pool[hearing_id]["viewer_can_decline"] is True
        assert await server.decline_hearing_request(hearing_id, s.notified_a) == {"ok": True}
        assert await _declined_by(db, hearing_id) == [s.notified_a["user_id"]]
        pool = {h["hearing_id"] for h in await hearings.list_hearing_requests(db, s.notified_a)}
        assert hearing_id not in pool
        # Personal, not global: the other notified counsel still sees it.
        assert hearing_id in {h["hearing_id"] for h in await hearings.list_hearing_requests(db, s.notified_b)}
    _run(body)


def test_counsel_notified_in_an_earlier_tier_can_still_decline():
    async def body(db, s):
        tier2 = [_counsel("tier2")["user_id"]]
        hearing_id = await s.hearing(db, tiers=[
            {"tier": 1, "notified_counsel_ids": [s.notified_a["user_id"]]},
            {"tier": 2, "notified_counsel_ids": tier2},
        ], current_tier_ids=tier2)  # notify_tier overwrote the hearing's list with tier 2
        assert (await hearings.get_hearing_request(db, hearing_id, s.notified_a))["viewer_can_decline"] is True
        assert await server.decline_hearing_request(hearing_id, s.notified_a) == {"ok": True}
    _run(body)


def test_unrelated_counsel_gets_403_and_nothing_is_recorded():
    async def body(db, s):
        hearing_id = await s.hearing(db)
        # They can still see it in the open pool (unchanged) — but not decline it.
        seen = await hearings.get_hearing_request(db, hearing_id, s.unrelated)
        assert seen["viewer_can_decline"] is False
        await _expect(403, server.decline_hearing_request(hearing_id, s.unrelated))
        assert await _declined_by(db, hearing_id) == []
    _run(body)


def test_counsel_never_notified_gets_403_even_with_no_matching_session():
    async def body(db, s):
        hearing_id = await s.hearing(db, tiers=[], current_tier_ids=[])
        for counsel in (s.notified_a, s.unrelated):
            await _expect(403, server.decline_hearing_request(hearing_id, counsel))
        await db.counsel_matching_log.delete_many({"hearing_id": hearing_id})
        await _expect(403, server.decline_hearing_request(hearing_id, s.notified_a))
        assert await _declined_by(db, hearing_id) == []
    _run(body)


def test_client_and_ordinary_users_get_403():
    async def body(db, s):
        hearing_id = await s.hearing(db)
        for user in (s.requester, _client("ordinary"), {**_client("admin"), "role": "admin"}):
            await _expect(403, server.decline_hearing_request(hearing_id, user))
        # Even the requester holding the counsel capability isn't a notified counsel.
        requester_with_cap = {**s.requester, "capabilities": list(COUNSEL_CAPS)}
        await _expect(403, server.decline_hearing_request(hearing_id, requester_with_cap))
        assert await _declined_by(db, hearing_id) == []
    _run(body)


def test_invalid_hearing_is_404():
    async def body(db, s):
        await _expect(404, server.decline_hearing_request("hearing_does_not_exist", s.notified_a))
    _run(body)


@pytest.mark.parametrize("status", ["accepted", "documents_shared", "cancelled", "rejected", "expired", "requested"])
def test_decline_outside_broadcast_is_refused_and_records_nothing(status):
    async def body(db, s):
        hearing_id = await s.hearing(db, status=status)
        detail = await _expect(400, server.decline_hearing_request(hearing_id, s.notified_a))
        assert detail == "This request is no longer open"
        assert await _declined_by(db, hearing_id) == []
        # ...and an unrelated counsel still gets 403, not the state message.
        await _expect(403, server.decline_hearing_request(hearing_id, s.unrelated))
    _run(body)


def test_targeted_request_decline():
    async def body(db, s):
        hearing_id = await s.hearing(db, target=s.notified_a["user_id"], tiers=[], current_tier_ids=[])
        detail = await _expect(400, server.decline_hearing_request(hearing_id, s.notified_a))
        assert "use Reject" in detail
        await _expect(403, server.decline_hearing_request(hearing_id, s.notified_b))
        assert await _declined_by(db, hearing_id) == []
    _run(body)


def test_repeated_decline_is_idempotent():
    async def body(db, s):
        hearing_id = await s.hearing(db)
        for _ in range(3):
            assert await server.decline_hearing_request(hearing_id, s.notified_a) == {"ok": True}
        assert await _declined_by(db, hearing_id) == [s.notified_a["user_id"]]
        hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
        assert hearing["status"] == "broadcast" and hearing["match_tier"] == 1  # no early advance: b hasn't declined
    _run(body)
