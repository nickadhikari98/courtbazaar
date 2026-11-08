"""Hearing request creation: past-date and duplicate validation.

- hearing_date is strict YYYY-MM-DD and may not be before India's today
  (fixed UTC+05:30); today and later are allowed.
- One active request per requester + targeted counsel + court + date,
  enforced by the uniq_active_dedupe_key partial unique index on dedupe_key.
  _transition unsets the key on cancelled/rejected/expired/completed; every
  other status keeps it.
- A counsel rejecting a request whose date has passed gets no fallback round;
  the requester is told instead.

Same direct-call pattern as test_ineligible_counsel_broadcast_access.py,
against conftest's throwaway DB (whose seeding builds the real indexes).
"""
import asyncio
import os
import sys
import unittest.mock
import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import counsel_matching  # noqa: E402
import hearings  # noqa: E402
import practice  # noqa: E402
import server  # noqa: E402
from tests._verified_counsel import verify_counsel  # noqa: E402

REAL_INDIA_TODAY = hearings.india_today  # before conftest's autouse pin replaces it
TODAY = date(2026, 6, 15)
PAST, FUTURE = "2026-06-14", "2026-06-20"
COURT, OTHER_COURT = "court_tishazari", "court_saket"


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr(hearings, "india_today", lambda: TODAY)


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _uid(prefix):
    return f"test_dedupe_{prefix}_{uuid.uuid4().hex[:10]}"


class _Ctx:
    def __init__(self, db):
        self.db = db
        self.user_ids = []

    def client(self):
        user = {"user_id": _uid("client"), "role": "client", "name": "Dedupe Client",
                "capabilities": ["can_hire_proxy_counsel"]}
        self.user_ids.append(user["user_id"])
        return user

    async def counsel(self):
        user = {"user_id": _uid("counsel"), "role": "proxy_counsel",
                "capabilities": ["can_practice_proxy_counsel", "can_hire_proxy_counsel"]}
        self.user_ids.append(user["user_id"])
        await verify_counsel(self.db, user["user_id"])
        return user

    async def create(self, requester, target, court=COURT, hearing_date=FUTURE, **kw):
        return await hearings.create_hearing_request(
            self.db, requester["user_id"], court, hearing_date, "Dedupe case", None, None,
            target_advocate_id=target["user_id"] if target else None, **kw,
        )

    async def requests_of(self, requester):
        return await self.db.hearing_requests.find(
            {"requesting_user_id": requester["user_id"]}, {"_id": 0}).to_list(50)

    async def cleanup(self):
        db, ids = self.db, self.user_ids
        hearing_ids = [h["hearing_id"] for h in await db.hearing_requests.find(
            {"requesting_user_id": {"$in": ids}}, {"hearing_id": 1}).to_list(500)]
        await db.hearing_requests.delete_many({"hearing_id": {"$in": hearing_ids}})
        await db.negotiations.delete_many({"hearing_id": {"$in": hearing_ids}})
        await db.notification_events.delete_many({"user_id": {"$in": ids}})
        await db.proxy_counsel_profiles.delete_many({"user_id": {"$in": ids}})
        await db.users.delete_many({"user_id": {"$in": ids}})


def _run(body):
    async def wrapper():
        db = _db()
        ctx = _Ctx(db)
        with unittest.mock.patch.object(server, "db", db):
            try:
                await body(db, ctx)
            finally:
                await ctx.cleanup()
    asyncio.run(wrapper())


async def _expect(status_code, coro):
    with pytest.raises(HTTPException) as exc_info:
        await coro
    assert exc_info.value.status_code == status_code
    return exc_info.value.detail


async def _move(db, hearing_id, from_status, action):
    """Drive one real status change through hearings._transition, the path
    every status change takes; from_status is written first as test setup."""
    await db.hearing_requests.update_one({"hearing_id": hearing_id}, {"$set": {"status": from_status}})
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
    sm = hearings.StateMachine(hearings.HEARING_TRANSITIONS, hearings._make_timeline_hook(db))
    return await hearings._transition(db, sm, hearing, from_status, action, None)


# --- past dates ----------------------------------------------------------------
def test_past_date_rejected_and_nothing_saved():
    async def body(db, ctx):
        requester, counsel = ctx.client(), await ctx.counsel()
        assert await _expect(400, ctx.create(requester, counsel, hearing_date=PAST)) == hearings.PAST_HEARING_DATE_MESSAGE
        assert await _expect(400, ctx.create(requester, None, hearing_date=PAST)) == hearings.PAST_HEARING_DATE_MESSAGE
        assert await ctx.requests_of(requester) == []
    _run(body)


@pytest.mark.parametrize("hearing_date", [TODAY.isoformat(), FUTURE])
def test_today_and_future_dates_allowed(hearing_date):
    async def body(db, ctx):
        requester, counsel = ctx.client(), await ctx.counsel()
        hearing = await ctx.create(requester, counsel, hearing_date=hearing_date)
        assert hearing["status"] == "requested" and hearing["hearing_date"] == hearing_date
    _run(body)


@pytest.mark.parametrize("bad", ["not-a-date", "2026-13-01", "2026-02-30", "20260620", "2026-W25-6",
                                 "2026-06-20T10:00", "20-06-2026", " 2026-06-20", 20260620])
def test_malformed_date_rejected(bad):
    async def body(db, ctx):
        requester, counsel = ctx.client(), await ctx.counsel()
        assert await _expect(400, ctx.create(requester, counsel, hearing_date=bad)) == hearings.INVALID_HEARING_DATE_MESSAGE
        assert await ctx.requests_of(requester) == []
    _run(body)


def test_india_today_uses_ist_not_utc(monkeypatch):
    # 18:29:59 UTC is 23:59:59 IST, still the same day; 18:30 UTC is IST midnight.
    monkeypatch.setattr(hearings, "_utcnow", lambda: datetime(2026, 6, 14, 18, 29, 59, tzinfo=timezone.utc))
    assert REAL_INDIA_TODAY() == date(2026, 6, 14)
    monkeypatch.setattr(hearings, "_utcnow", lambda: datetime(2026, 6, 14, 18, 30, tzinfo=timezone.utc))
    assert REAL_INDIA_TODAY() == date(2026, 6, 15)


def test_create_at_ist_midnight_boundary(monkeypatch):
    """End to end through create_hearing_request with the real india_today:
    14 June is "today" until 23:59:59 IST and "past" from 00:00 IST."""
    monkeypatch.setattr(hearings, "india_today", REAL_INDIA_TODAY)

    async def body(db, ctx):
        requester, counsel = ctx.client(), await ctx.counsel()
        monkeypatch.setattr(hearings, "_utcnow", lambda: datetime(2026, 6, 14, 18, 29, 59, tzinfo=timezone.utc))
        await ctx.create(requester, counsel, hearing_date="2026-06-14")
        monkeypatch.setattr(hearings, "_utcnow", lambda: datetime(2026, 6, 14, 18, 30, tzinfo=timezone.utc))
        assert await _expect(400, ctx.create(requester, counsel, hearing_date="2026-06-14", court=OTHER_COURT)) \
            == hearings.PAST_HEARING_DATE_MESSAGE
        await ctx.create(requester, counsel, hearing_date="2026-06-15", court=OTHER_COURT)
    _run(body)


# --- duplicates ----------------------------------------------------------------
def test_active_duplicate_returns_409_and_keeps_one_request():
    async def body(db, ctx):
        requester, counsel = ctx.client(), await ctx.counsel()
        first = await ctx.create(requester, counsel)
        assert await _expect(409, ctx.create(requester, counsel)) == hearings.DUPLICATE_HEARING_MESSAGE
        assert [h["hearing_id"] for h in await ctx.requests_of(requester)] == [first["hearing_id"]]
        # Untargeted (broadcast) requests follow the same rule.
        await ctx.create(requester, None)
        await _expect(409, ctx.create(requester, None))
    _run(body)


@pytest.mark.parametrize("differs", ["counsel", "court", "date", "requester"])
def test_any_differing_field_is_not_a_duplicate(differs):
    async def body(db, ctx):
        requester, counsel = ctx.client(), await ctx.counsel()
        await ctx.create(requester, counsel)
        if differs == "counsel":
            await ctx.create(requester, await ctx.counsel())
        elif differs == "court":
            await ctx.create(requester, counsel, court=OTHER_COURT)
        elif differs == "date":
            await ctx.create(requester, counsel, hearing_date="2026-06-21")
        else:
            await ctx.create(ctx.client(), counsel)
    _run(body)


@pytest.mark.parametrize("from_status,action,closed", [
    ("requested", "cancel", "cancelled"),
    ("requested", "reject", "rejected"),
    ("broadcast", "expire", "expired"),
    ("verified", "release_payout", "completed"),
])
def test_closed_request_releases_its_slot(from_status, action, closed):
    async def body(db, ctx):
        requester, counsel = ctx.client(), await ctx.counsel()
        first = await ctx.create(requester, counsel)
        assert await _move(db, first["hearing_id"], from_status, action) == closed
        assert "dedupe_key" not in await db.hearing_requests.find_one({"hearing_id": first["hearing_id"]})
        second = await ctx.create(requester, counsel)
        assert second["hearing_id"] != first["hearing_id"]
        await _expect(409, ctx.create(requester, counsel))  # the new one holds the slot now
    _run(body)


def test_public_cancel_releases_slot():
    async def body(db, ctx):
        requester, counsel = ctx.client(), await ctx.counsel()
        first = await ctx.create(requester, counsel)
        await hearings.cancel_hearing_request(db, first["hearing_id"], requester)
        await ctx.create(requester, counsel)
    _run(body)


def test_active_and_in_progress_statuses_keep_blocking():
    """Walks every non-closing status change through the real _transition;
    the slot stays held at each step (accepted and everything after it)."""
    chain = [("requested", "initiate_payment"), ("payment_pending", "confirm_payment"), ("broadcast", "accept"),
             ("accepted", "accept"), ("documents_shared", "share_documents"), ("preparation", "schedule"),
             ("hearing_scheduled", "conduct"), ("hearing_completed", "upload_order_sheet"),
             ("verification_pending", "reject_verification"), ("disputed", "resubmit"),
             ("verification_pending", "verify")]

    async def body(db, ctx):
        requester, counsel = ctx.client(), await ctx.counsel()
        first = await ctx.create(requester, counsel)
        await _expect(409, ctx.create(requester, counsel))
        for from_status, action in chain:
            reached = await _move(db, first["hearing_id"], from_status, action)
            assert (await db.hearing_requests.find_one({"hearing_id": first["hearing_id"]})).get("dedupe_key"), reached
            await _expect(409, ctx.create(requester, counsel))
        assert reached == "verified"
    _run(body)


def test_concurrent_creates_exactly_one_succeeds():
    async def body(db, ctx):
        requester, counsel = ctx.client(), await ctx.counsel()
        results = await asyncio.gather(*(ctx.create(requester, counsel) for _ in range(8)), return_exceptions=True)
        assert sum(isinstance(r, dict) for r in results) == 1
        assert all(r.status_code == 409 for r in results if not isinstance(r, dict))
        assert len(await ctx.requests_of(requester)) == 1
    _run(body)


def test_ineligible_counsel_error_takes_precedence_over_duplicate():
    async def body(db, ctx):
        requester, counsel = ctx.client(), await ctx.counsel()
        await ctx.create(requester, counsel)
        await practice.revoke_verification(db, counsel["user_id"])
        detail = await _expect(400, ctx.create(requester, counsel))
        assert detail == "This counsel isn't available for new requests. Please choose another counsel."
    _run(body)


def test_legacy_requests_without_dedupe_key_unaffected():
    async def body(db, ctx):
        requester, counsel = ctx.client(), await ctx.counsel()
        # Two pre-existing rows with no dedupe_key (as every row created before
        # this field existed): they coexist under the partial unique index.
        legacy = []
        for _ in range(2):
            h = await ctx.create(requester, counsel)
            await db.hearing_requests.update_one({"hearing_id": h["hearing_id"]}, {"$unset": {"dedupe_key": ""}})
            legacy.append(h["hearing_id"])
        assert len(await ctx.requests_of(requester)) == 2
        # ...still go through the lifecycle normally...
        await hearings.cancel_hearing_request(db, legacy[0], requester)
        assert (await db.hearing_requests.find_one({"hearing_id": legacy[0]}))["status"] == "cancelled"
        # ...and, having no key, don't block (no backfill: accepted limitation).
        await ctx.create(requester, counsel)
    _run(body)


def test_route_returns_409_and_400():
    async def body(db, ctx):
        requester, counsel = ctx.client(), await ctx.counsel()
        payload = server.HearingRequestCreate(court_id=COURT, hearing_date=FUTURE, case_details="",
                                              target_advocate_id=counsel["user_id"])
        assert (await server.create_hearing_request(payload, requester))["status"] == "requested"
        await _expect(409, server.create_hearing_request(payload, requester))
        past = payload.model_copy(update={"hearing_date": PAST})
        await _expect(400, server.create_hearing_request(past, requester))
    _run(body)


# --- fallback after a reject -----------------------------------------------------
def test_fallback_copies_to_other_counsel_still_created():
    async def body(db, ctx):
        requester, target, b, c = ctx.client(), await ctx.counsel(), await ctx.counsel(), await ctx.counsel()
        original = await ctx.create(requester, target)

        async def candidates(_db, _hearing, exclude):
            return [p for p in ({"user_id": b["user_id"]}, {"user_id": c["user_id"]}) if p["user_id"] not in exclude]
        with unittest.mock.patch.object(counsel_matching, "top_fallback_candidates", candidates):
            await hearings.reject_hearing_request(db, original["hearing_id"], target)

        rows = {h["hearing_id"]: h for h in await ctx.requests_of(requester)}
        assert rows[original["hearing_id"]]["status"] == "rejected"
        copies = [h for h in rows.values() if h.get("is_fallback")]
        assert sorted(h["target_advocate_id"] for h in copies) == sorted([b["user_id"], c["user_id"]])
        assert all(h["status"] == "requested" and h["hearing_date"] == FUTURE for h in copies)
    _run(body)


def test_past_date_fallback_skipped_and_requester_told(monkeypatch):
    async def body(db, ctx):
        requester, target, b = ctx.client(), await ctx.counsel(), await ctx.counsel()
        await db.users.insert_one({"user_id": requester["user_id"], "name": requester["name"]})  # notify target
        original = await ctx.create(requester, target, hearing_date=TODAY.isoformat())
        monkeypatch.setattr(hearings, "india_today", lambda: date(2026, 6, 16))  # the hearing day has passed
        finder = unittest.mock.AsyncMock(return_value=[{"user_id": b["user_id"]}])
        with unittest.mock.patch.object(counsel_matching, "top_fallback_candidates", finder):
            assert (await hearings.reject_hearing_request(db, original["hearing_id"], target))["status"] == "rejected"

        finder.assert_not_called()
        rows = await ctx.requests_of(requester)
        assert [(h["hearing_id"], h["status"]) for h in rows] == [(original["hearing_id"], "rejected")]
        notes = await db.notification_events.find({"user_id": requester["user_id"]}, {"_id": 0}).to_list(10)
        assert [n["body"] for n in notes] == [hearings.FALLBACK_SKIPPED_PAST_DATE_MESSAGE]
        assert notes[0]["related_entity_id"] == original["hearing_id"]
    _run(body)
