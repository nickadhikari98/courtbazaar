"""CUSTOM DATE availability vs. client search (CourtBazaar, 2026-10-14).

Reported: with these My Availability entries
    CUSTOM DATE           17 Oct 2026 (Sat)  10 AM – 1 PM
    CUSTOM DATE           25 Oct 2026 (Sun)  Full Day
    CUSTOM DATE           31 Oct 2026 (Sat)  Full Day
    HOLIDAY BLOCK         15 Oct 2026 (Thu)  Weekends
    EMERGENCY UNAVAILABLE 18 Oct 2026 (Sun)  Full Day
    RECURRING WEEKLY      Wednesday, Delhi High Court, 2 PM – 5 PM
the Wednesday slot worked but searches on the custom dates didn't find the
counsel.

Diagnosis (dev DB + dev API): every custom date is a Saturday/Sunday. The
availability check itself matched 17 Oct 10 AM – 1 PM and 25/31 Oct Full
Day; most failing searches were excluded by the time-slot *pricing* filter
(the counsel had only priced 2 PM – 5 PM), which these tests leave intact.
The one real matching bug: choosing the client's "Weekends" time slot for a
weekend date never matched a custom date, because "Weekends" was compared to
the slot's own time label ("10 AM – 1 PM", "Full Day") as if it were a time
of day. On a Saturday/Sunday it now means "any time that day".
"""
import asyncio
import os
import sys
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import counsel_matching  # noqa: E402
import practice  # noqa: E402

L = practice.PRICING_SLOT_LABELS
ALL_PRICED = {"high_court": {"morning": 1200, "afternoon": 1200, "full_day": 2000, "weekend": 3000, "urgent": 3000}}

REPORTED_SLOTS = [
    {"kind": "custom_date", "date": "2026-10-17", "start_time": L["morning"]},
    {"kind": "custom_date", "date": "2026-10-25", "start_time": L["full_day"]},
    {"kind": "custom_date", "date": "2026-10-31", "start_time": L["full_day"]},
    {"kind": "holiday_block", "date": "2026-10-15", "start_time": L["weekend"]},
    {"kind": "emergency_unavailable", "date": "2026-10-18", "start_time": L["full_day"]},
    {"kind": "recurring_weekly", "day_of_week": 2, "start_time": L["afternoon"], "court_id": "court_delhi_hc"},
]


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _search(slots, hearing_date, time_slot, pricing=ALL_PRICED):
    """Seeds one approved, verified counsel serving a test court with
    `slots`, runs the client search (list_and_recommend, what
    /public/proxy-counsels and the fallback-to-next-counsel list use) and
    returns whether that counsel was found."""
    async def body():
        db = _db()
        tag = uuid.uuid4().hex[:10]
        court_id, user_id = f"court_test_{tag}", f"test_counsel_{tag}"
        try:
            await db.courts.insert_one({"court_id": court_id, "name": "Test High Court", "type": "high_court"})
            await db.users.insert_one({"user_id": user_id, "name": "Test Counsel", "role": "proxy_counsel"})
            await db.proxy_counsel_profiles.insert_one({
                "user_id": user_id, "kyc_status": "approved", "bar_council_verified": True,
                "availability_mode": True, "courts": [court_id], "practice_areas": [], "languages": [],
                "pricing": pricing, "experience_years": 3, "rating": 0, "cases_completed": 0,
            })
            if slots:
                await db.availability_slots.insert_many([
                    {"slot_id": f"slot_{uuid.uuid4().hex[:12]}", "user_id": user_id, "day_of_week": None,
                     "date": None, "court_id": None, "end_time": None, **s}
                    for s in slots
                ])
            ranked, _ = await counsel_matching.list_and_recommend(
                db, court_id=court_id, time_slot=time_slot, hearing_date=hearing_date,
            )
            return user_id in [c["user_id"] for c in ranked]
        finally:
            await db.courts.delete_many({"court_id": court_id})
            await db.users.delete_many({"user_id": user_id})
            await db.proxy_counsel_profiles.delete_many({"user_id": user_id})
            await db.availability_slots.delete_many({"user_id": user_id})
    return asyncio.run(body())


# --- 17 Oct 2026 (Saturday), 10 AM – 1 PM --------------------------------

def test_17_oct_morning_custom_date_matches():
    assert _search(REPORTED_SLOTS, "2026-10-17", "morning") is True
    assert _search(REPORTED_SLOTS, "2026-10-17", None) is True


def test_17_oct_weekends_filter_matches_saturday_custom_date():
    # Failed before the fix: "Weekends" != "10 AM – 1 PM".
    assert _search(REPORTED_SLOTS, "2026-10-17", "weekend") is True


def test_17_oct_afternoon_does_not_match_morning_only_slot():
    assert _search(REPORTED_SLOTS, "2026-10-17", "afternoon") is False


# --- 25 and 31 Oct 2026, Full Day ----------------------------------------

def test_25_oct_full_day_custom_date_matches_every_time_slot():
    for time_slot in (None, "full_day", "morning", "afternoon", "weekend"):
        assert _search(REPORTED_SLOTS, "2026-10-25", time_slot) is True, time_slot


def test_31_oct_full_day_custom_date_matches_every_time_slot():
    for time_slot in (None, "full_day", "morning", "afternoon", "weekend"):
        assert _search(REPORTED_SLOTS, "2026-10-31", time_slot) is True, time_slot


# --- Dates/times that don't match ----------------------------------------

def test_dates_without_availability_do_not_match():
    # 24 Oct is a Saturday with no custom date; 22 Oct a Thursday.
    for date, time_slot in (("2026-10-24", None), ("2026-10-24", "weekend"), ("2026-10-22", "morning")):
        assert _search(REPORTED_SLOTS, date, time_slot) is False, (date, time_slot)


def test_weekends_filter_on_a_weekday_is_unchanged():
    # Only weekend dates get the "any time that day" reading.
    assert _search(REPORTED_SLOTS, "2026-10-21", "weekend") is False


# --- Blocks still win -----------------------------------------------------

def test_reported_holiday_and_emergency_dates_do_not_match():
    for date in ("2026-10-15", "2026-10-18"):
        for time_slot in (None, "morning", "afternoon", "full_day", "weekend"):
            assert _search(REPORTED_SLOTS, date, time_slot) is False, (date, time_slot)


def test_holiday_block_overrides_conflicting_custom_date():
    slots = [{"kind": "custom_date", "date": "2026-10-25", "start_time": L["full_day"]},
             {"kind": "holiday_block", "date": "2026-10-25", "start_time": L["full_day"]}]
    for time_slot in (None, "morning", "full_day", "weekend"):
        assert _search(slots, "2026-10-25", time_slot) is False, time_slot


def test_emergency_block_overrides_conflicting_custom_date_for_its_period():
    slots = [{"kind": "custom_date", "date": "2026-10-31", "start_time": L["full_day"]},
             {"kind": "emergency_unavailable", "date": "2026-10-31", "start_time": L["morning"]}]
    assert _search(slots, "2026-10-31", "morning") is False
    assert _search(slots, "2026-10-31", "full_day") is False
    assert _search(slots, "2026-10-31", "weekend") is False  # a weekend booking that day conflicts with the block
    assert _search(slots, "2026-10-31", "afternoon") is True  # the unblocked half of the day


def test_emergency_full_day_overrides_conflicting_custom_date():
    slots = [{"kind": "custom_date", "date": "2026-10-18", "start_time": L["full_day"]},
             {"kind": "emergency_unavailable", "date": "2026-10-18", "start_time": L["full_day"]}]
    assert _search(slots, "2026-10-18", None) is False
    assert _search(slots, "2026-10-18", "weekend") is False


# --- Recurring Wednesday still works --------------------------------------

def test_recurring_wednesday_afternoon_still_matches():
    assert _search(REPORTED_SLOTS, "2026-10-21", "afternoon") is True
    assert _search(REPORTED_SLOTS, "2026-10-14", "afternoon") is True
    assert _search(REPORTED_SLOTS, "2026-10-21", "morning") is False


# --- Eligibility gates are not weakened -----------------------------------

def test_unpriced_time_slot_still_excludes_custom_date_match():
    """The dev counsel's real situation: only 2 PM – 5 PM priced, so a
    10 AM – 1 PM / Full Day / Weekends search excludes them on price even
    though availability matches."""
    afternoon_only = {"high_court": {"afternoon": 2000, "urgent": 3800}}
    assert _search(REPORTED_SLOTS, "2026-10-17", "morning", pricing=afternoon_only) is False
    assert _search(REPORTED_SLOTS, "2026-10-25", "full_day", pricing=afternoon_only) is False
    assert _search(REPORTED_SLOTS, "2026-10-31", "weekend", pricing=afternoon_only) is False
    assert _search(REPORTED_SLOTS, "2026-10-25", "afternoon", pricing=afternoon_only) is True
