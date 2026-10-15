"""Bug fixes: Proxy Counsel → My Availability (CourtBazaar meeting, 2026-10-13).

Root cause: the Availability form used to save literal clock times
(start_time "09:03", end_time "18:03"), then switched to time-of-day labels
("10 AM – 1 PM", "Full Day", ...). Rows saved before the switch were never
migrated, and practice.is_available_on_date compared start_time to a label
by exact string — so a legacy "09:03–18:03" holiday block never blocked a
morning/afternoon search, and the counsel kept showing as bookable on a day
they had blocked. Nothing on the backend restricted start_time/date either,
so the same drift could recur from a direct API call.

Also covered: dates must be real YYYY-MM-DD and not in the past, duplicates
are rejected, an existing slot can be edited in place (PUT), and past dated
slots are flagged for the Availability tab.
"""
import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import counsel_matching  # noqa: E402
import practice  # noqa: E402

MORNING = practice.PRICING_SLOT_LABELS["morning"]
AFTERNOON = practice.PRICING_SLOT_LABELS["afternoon"]
FULL_DAY = practice.PRICING_SLOT_LABELS["full_day"]


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


async def _insert_counsel_profile(db, profile):
    """Counsels are only listed/matched while their account exists
    (counsel_matching.deactivated_user_ids hides orphaned profiles), so each
    fixture profile gets a matching live users row. Upsert: never touches a
    users row a test created itself."""
    await db.users.update_one(
        {"user_id": profile["user_id"]},
        {"$setOnInsert": {"user_id": profile["user_id"], "name": "Test Counsel", "role": "proxy_counsel"}},
        upsert=True,
    )
    await db.proxy_counsel_profiles.insert_one(profile)


def _today_ist() -> date:
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).date()


def _future_date(days: int = 10) -> str:
    return (_today_ist() + timedelta(days=days)).isoformat()


def _past_date(days: int = 3) -> str:
    return (_today_ist() - timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# Matching: legacy clock-time rows
# ---------------------------------------------------------------------------

def test_legacy_clock_time_holiday_block_blocks_timed_searches():
    day = _future_date()
    legacy_block = [{"kind": "holiday_block", "date": day, "start_time": "09:03", "end_time": "18:03"}]
    # Before the fix all three returned True: "09:03" never equalled a label.
    assert practice.is_available_on_date(legacy_block, day, "morning") is False
    assert practice.is_available_on_date(legacy_block, day, "afternoon") is False
    assert practice.is_available_on_date(legacy_block, day, "full_day") is False
    assert practice.is_available_on_date(legacy_block, day, None) is False
    # Another date is untouched.
    assert practice.is_available_on_date(legacy_block, _future_date(11), "morning") is True


def test_legacy_clock_time_block_only_blocks_the_hours_it_covers():
    day = _future_date()
    evening_block = [{"kind": "holiday_block", "date": day, "start_time": "18:30", "end_time": "20:00"}]
    assert practice.is_available_on_date(evening_block, day, "morning") is True
    assert practice.is_available_on_date(evening_block, day, "afternoon") is True
    morning_block = [{"kind": "emergency_unavailable", "date": day, "start_time": "09:00", "end_time": "12:00"}]
    assert practice.is_available_on_date(morning_block, day, "morning") is False
    assert practice.is_available_on_date(morning_block, day, "afternoon") is True


def test_legacy_clock_time_recurring_slot_matches_overlapping_window():
    day = _future_date()
    weekday = date.fromisoformat(day).weekday()
    legacy_recurring = [{"kind": "recurring_weekly", "day_of_week": weekday, "start_time": "10:00", "end_time": "13:00"}]
    # Before the fix a counsel with this slot vanished from every timed search on their own day.
    assert practice.is_available_on_date(legacy_recurring, day, "morning") is True
    assert practice.is_available_on_date(legacy_recurring, day, "afternoon") is False


def test_label_rows_keep_existing_semantics():
    day = _future_date()
    weekday = date.fromisoformat(day).weekday()
    afternoon_block = [{"kind": "holiday_block", "date": day, "start_time": AFTERNOON}]
    assert practice.is_available_on_date(afternoon_block, day, "morning") is True
    assert practice.is_available_on_date(afternoon_block, day, "afternoon") is False
    assert practice.is_available_on_date(afternoon_block, day, "full_day") is False
    full_day_block = [{"kind": "holiday_block", "date": day, "start_time": FULL_DAY}]
    assert practice.is_available_on_date(full_day_block, day, "morning") is False
    mornings_only = [{"kind": "recurring_weekly", "day_of_week": weekday, "start_time": MORNING}]
    assert practice.is_available_on_date(mornings_only, day, "morning") is True
    assert practice.is_available_on_date(mornings_only, day, "afternoon") is False
    assert practice.is_available_on_date([], day, "morning") is True
    # Slot with no time at all stays permissive, as before.
    assert practice.is_available_on_date([{"kind": "holiday_block", "date": day, "start_time": None}], day, "morning") is False


def test_search_excludes_counsel_with_legacy_holiday_block():
    """End to end through the client-facing browse search
    (counsel_matching.list_and_recommend, which also backs the auto top-5
    fallback after a rejection)."""
    async def body():
        db = _db()
        court_id = f"court_test_{uuid.uuid4().hex[:10]}"
        user_id = f"test_counsel_{uuid.uuid4().hex[:10]}"
        day = _future_date()
        try:
            await _insert_counsel_profile(db, {
                "user_id": user_id, "kyc_status": "approved", "bar_council_verified": True,
                "courts": [court_id], "practice_areas": [], "languages": [],
                "pricing": {"district": {"morning": 600}}, "availability_mode": True, "rating": 0, "cases_completed": 0,
            })
            await db.availability_slots.insert_one({
                "slot_id": f"slot_{uuid.uuid4().hex[:12]}", "user_id": user_id, "kind": "holiday_block",
                "day_of_week": None, "date": day, "court_id": None, "start_time": "09:03", "end_time": "18:03",
            })
            _, total = await counsel_matching.list_and_recommend(db, court_id=court_id, hearing_date=day, time_slot="morning")
            assert total == 0
            _, total = await counsel_matching.list_and_recommend(db, court_id=court_id, hearing_date=_future_date(11), time_slot="morning")
            assert total == 1
        finally:
            await db.proxy_counsel_profiles.delete_many({"user_id": user_id})
            await db.availability_slots.delete_many({"user_id": user_id})
    asyncio.run(body())


# ---------------------------------------------------------------------------
# Create / edit / delete
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("bad_date", ["14/10/2026", "2026-13-01", "2026-02-30", "tomorrow"])
def test_add_slot_rejects_malformed_dates(bad_date):
    with pytest.raises(HTTPException) as exc:
        _run(practice.add_slot(_db(), "u_unused", "custom_date", None, bad_date, None, MORNING, None))
    assert exc.value.status_code == 400


def test_add_slot_rejects_past_dates_but_allows_today():
    user_id = f"test_avail_{uuid.uuid4().hex[:10]}"

    async def body():
        db = _db()
        try:
            with pytest.raises(HTTPException) as exc:
                await practice.add_slot(db, user_id, "holiday_block", None, _past_date(), None, FULL_DAY, None)
            assert exc.value.status_code == 400
            slot = await practice.add_slot(db, user_id, "holiday_block", None, _today_ist().isoformat(), None, FULL_DAY, None)
            assert slot["date"] == _today_ist().isoformat()
            assert slot["is_past"] is False
        finally:
            await db.availability_slots.delete_many({"user_id": user_id})
    _run(body())


@pytest.mark.parametrize("bad_time", ["09:00", "Morning", "10 AM - 1 PM", "Urgent (same-day)"])
def test_add_slot_rejects_unknown_time_labels(bad_time):
    with pytest.raises(HTTPException) as exc:
        _run(practice.add_slot(_db(), "u_unused", "recurring_weekly", 0, None, None, bad_time, None))
    assert exc.value.status_code == 400


def test_add_slot_normalizes_fields_and_rejects_duplicates():
    user_id = f"test_avail_{uuid.uuid4().hex[:10]}"

    async def body():
        db = _db()
        try:
            # A stray date on a weekly slot / court whitespace is normalized away.
            slot = await practice.add_slot(db, user_id, "recurring_weekly", 2, _future_date(), "  ", MORNING, "18:00")
            assert slot["date"] is None and slot["court_id"] is None and slot["end_time"] is None
            stored = await db.availability_slots.find_one({"slot_id": slot["slot_id"]}, {"_id": 0})
            assert stored["day_of_week"] == 2 and stored["start_time"] == MORNING
            with pytest.raises(HTTPException) as exc:
                await practice.add_slot(db, user_id, "recurring_weekly", 2, None, None, MORNING, None)
            assert exc.value.status_code == 409
            # Same day, different time is a different slot.
            await practice.add_slot(db, user_id, "recurring_weekly", 2, None, None, AFTERNOON, None)
            assert len(await practice.list_slots(db, user_id)) == 2
        finally:
            await db.availability_slots.delete_many({"user_id": user_id})
    _run(body())


def test_update_slot_edits_in_place_and_clears_stale_fields():
    user_id = f"test_avail_{uuid.uuid4().hex[:10]}"
    other_user = f"test_avail_{uuid.uuid4().hex[:10]}"

    async def body():
        db = _db()
        court_id = f"court_test_{uuid.uuid4().hex[:10]}"
        await db.courts.insert_one({"court_id": court_id, "name": "Test Delhi High Court", "type": "high_court"})
        try:
            # Free-text courts (what the old Court field saved) are rejected; a real court_id is kept.
            with pytest.raises(HTTPException) as exc:
                await practice.add_slot(db, user_id, "recurring_weekly", 0, None, "Delhi High Court", MORNING, None)
            assert exc.value.status_code == 400
            slot = await practice.add_slot(db, user_id, "recurring_weekly", 0, None, court_id, MORNING, None)
            listed = await practice.list_slots(db, user_id)
            assert listed[0]["court_name"] == "Test Delhi High Court" and listed[0]["court_known"] is True
            day = _future_date()
            updated = await practice.update_slot(db, user_id, slot["slot_id"], "holiday_block", None, day, None, FULL_DAY, None)
            assert updated["slot_id"] == slot["slot_id"]
            stored = await db.availability_slots.find_one({"slot_id": slot["slot_id"]}, {"_id": 0})
            assert stored["kind"] == "holiday_block" and stored["date"] == day
            assert stored["day_of_week"] is None and stored["court_id"] is None and stored["start_time"] == FULL_DAY
            assert stored["created_at"] == slot["created_at"] and stored.get("updated_at")
            assert len(await practice.list_slots(db, user_id)) == 1

            # Saving a slot unchanged is not a duplicate of itself...
            await practice.update_slot(db, user_id, slot["slot_id"], "holiday_block", None, day, None, FULL_DAY, None)
            # ...but editing it into a copy of another slot is.
            second = await practice.add_slot(db, user_id, "custom_date", None, day, None, MORNING, None)
            with pytest.raises(HTTPException) as exc:
                await practice.update_slot(db, user_id, second["slot_id"], "holiday_block", None, day, None, FULL_DAY, None)
            assert exc.value.status_code == 409

            # Validation applies to edits too.
            with pytest.raises(HTTPException) as exc:
                await practice.update_slot(db, user_id, slot["slot_id"], "holiday_block", None, _past_date(), None, FULL_DAY, None)
            assert exc.value.status_code == 400

            # Another counsel can't edit or delete it.
            with pytest.raises(HTTPException) as exc:
                await practice.update_slot(db, other_user, slot["slot_id"], "recurring_weekly", 1, None, None, MORNING, None)
            assert exc.value.status_code == 404
            with pytest.raises(HTTPException) as exc:
                await practice.remove_slot(db, other_user, slot["slot_id"])
            assert exc.value.status_code == 404

            assert await practice.remove_slot(db, user_id, slot["slot_id"]) == {"ok": True}
            assert [s["slot_id"] for s in await practice.list_slots(db, user_id)] == [second["slot_id"]]
        finally:
            await db.availability_slots.delete_many({"user_id": {"$in": [user_id, other_user]}})
            await db.courts.delete_many({"court_id": court_id})
    _run(body())


def test_list_slots_flags_past_dated_slots():
    user_id = f"test_avail_{uuid.uuid4().hex[:10]}"

    async def body():
        db = _db()
        try:
            await db.availability_slots.insert_many([
                {"slot_id": "slot_past_" + uuid.uuid4().hex[:6], "user_id": user_id, "kind": "holiday_block",
                 "day_of_week": None, "date": _past_date(), "start_time": "09:03", "end_time": "18:03", "created_at": "1"},
                {"slot_id": "slot_week_" + uuid.uuid4().hex[:6], "user_id": user_id, "kind": "recurring_weekly",
                 "day_of_week": 1, "date": None, "start_time": MORNING, "end_time": None, "created_at": "2"},
            ])
            flags = {s["kind"]: s["is_past"] for s in await practice.list_slots(db, user_id)}
            assert flags == {"holiday_block": True, "recurring_weekly": False}
        finally:
            await db.availability_slots.delete_many({"user_id": user_id})
    _run(body())


def test_put_endpoint_is_registered():
    from server import api_router
    routes = {(tuple(sorted(r.methods)), r.path) for r in api_router.routes if hasattr(r, "methods")}
    assert (("PUT",), "/api/practice/availability/{slot_id}") in routes or \
        (("PUT",), "/practice/availability/{slot_id}") in routes
