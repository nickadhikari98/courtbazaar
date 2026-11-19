"""Proxy Counsel availability vs. client search (CourtBazaar, 2026-10-14).

Reported: a counsel saved a recurring Wednesday, Delhi High Court, 2 PM – 5 PM
slot ("Availability added"), but a client searching High Court / Delhi /
Delhi High Court / Wed 14 Oct 2026 / 2 PM – 5 PM got "No counsels match".

Diagnosis on the dev DB: the slot itself matched (practice.is_available_on_date
was True). The counsel was excluded earlier, by three profile gates the page
never mentioned: KYC pending / bar council unverified (trust gate), profile
Courts not containing court_delhi_hc (free-text names), and no price for the
afternoon slot (time_slot filter). These tests pin the exact scenario for a
properly set-up counsel, each exclusion on its own, the new "Visible to
clients?" self-check that reports those gates, and the deactivated-account
fix (users.deleted counsels used to stay listed).
"""
import asyncio
import os
import sys
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import counsel_matching  # noqa: E402
import practice  # noqa: E402
import server  # noqa: E402
from fastapi import HTTPException  # noqa: E402

WEDNESDAY = "2026-10-14"  # the reported hearing date; weekday() == 2 == Wednesday
THURSDAY = "2026-10-15"
AFTERNOON = practice.PRICING_SLOT_LABELS["afternoon"]  # "2 PM – 5 PM"


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


class Scenario:
    """A counsel set up exactly as reported, but fully eligible: approved,
    verified, active account, Delhi High Court on the profile, afternoon (and
    morning, so a morning search is excluded only by availability) priced,
    and a recurring Wednesday 2 PM – 5 PM slot at that court."""

    def __init__(self, db):
        self.db = db
        tag = uuid.uuid4().hex[:10]
        self.court_id = f"court_test_dhc_{tag}"
        self.state_id = f"state_test_delhi_{tag}"
        self.user_id = f"test_counsel_{tag}"

    async def create(self, profile_overrides=None, user_overrides=None, slot=True):
        db = self.db
        await db.courts.insert_one({
            "court_id": self.court_id, "name": "Delhi High Court (test)", "type": "high_court",
            "state_id": self.state_id, "serviceable": True,
        })
        await db.users.insert_one({
            "user_id": self.user_id, "name": "Test Counsel", "role": "proxy_counsel",
            "deleted": False, **(user_overrides or {}),
        })
        await db.proxy_counsel_profiles.insert_one({
            "user_id": self.user_id, "kyc_status": "approved", "bar_council_verified": True,
            "availability_mode": True, "courts": [self.court_id], "practice_areas": [], "languages": [],
            "pricing": {"high_court": {"morning": 1200, "afternoon": 1200}},
            "experience_years": 3, "rating": 0, "cases_completed": 0, **(profile_overrides or {}),
        })
        if slot:
            await practice.add_slot(db, self.user_id, "recurring_weekly", 2, None, self.court_id, AFTERNOON, None)
        return self

    async def search(self, hearing_date=WEDNESDAY, time_slot="afternoon"):
        """Same filters the Hire Proxy Counsel page sends for the reported search."""
        ranked, _total = await counsel_matching.list_and_recommend(
            self.db, court_id=self.court_id, state_id=self.state_id,
            time_slot=time_slot, experience_bracket=None, hearing_date=hearing_date,
        )
        return [c["user_id"] for c in ranked]

    async def cleanup(self):
        db = self.db
        await db.courts.delete_many({"court_id": self.court_id})
        await db.users.delete_many({"user_id": self.user_id})
        await db.proxy_counsel_profiles.delete_many({"user_id": self.user_id})
        await db.availability_slots.delete_many({"user_id": self.user_id})


def _run(test_body, **create_kwargs):
    async def body():
        sc = Scenario(_db())
        try:
            await sc.create(**create_kwargs)
            await test_body(sc)
        finally:
            await sc.cleanup()
    asyncio.run(body())


# ---------------------------------------------------------------------------
# The reported scenario
# ---------------------------------------------------------------------------

def test_recurring_wednesday_delhi_hc_afternoon_matches_same_client_search():
    async def body(sc):
        assert await sc.search() == [sc.user_id]
        # Also through the public (no-login) endpoint's card shape.
        ranked, _ = await counsel_matching.list_and_recommend(
            sc.db, court_id=sc.court_id, state_id=sc.state_id, time_slot="afternoon", hearing_date=WEDNESDAY,
        )
        assert counsel_matching.public_advocate_card(
            counsel_matching.build_advocate_card(ranked[0], "Test Counsel", {}),
        )["advocate_id"] == sc.user_id
    _run(body)


def test_different_weekday_does_not_match():
    async def body(sc):
        assert await sc.search(hearing_date=THURSDAY) == []
    _run(body)


def test_incompatible_time_slot_does_not_match():
    async def body(sc):
        # Morning is priced, so only the afternoon-only availability excludes it.
        assert await sc.search(time_slot="morning") == []
    _run(body)


def test_unapproved_profile_does_not_match():
    async def body(sc):
        assert await sc.search() == []
    _run(body, profile_overrides={"kyc_status": "pending"})


def test_unverified_bar_council_does_not_match():
    async def body(sc):
        assert await sc.search() == []
    _run(body, profile_overrides={"bar_council_verified": None})


def test_profile_without_the_court_does_not_match_even_if_slot_names_it():
    async def body(sc):
        assert await sc.search() == []
    _run(body, profile_overrides={"courts": ["pune high court"]})


def test_unpriced_time_slot_does_not_match():
    async def body(sc):
        assert await sc.search() == []
    _run(body, profile_overrides={"pricing": None})


# ---------------------------------------------------------------------------
# Deactivated ("inactive") accounts — failed before the fix
# ---------------------------------------------------------------------------

def test_deactivated_account_is_excluded_from_search_profile_and_matching():
    async def body(sc):
        # Before: deactivation only set users.deleted, which nothing here read.
        assert await sc.search() == []
        ranked, total = await counsel_matching.list_and_recommend(sc.db, court_id=sc.court_id)
        assert total == 0 and ranked == []

        # server.db is a shared module-level client; using it inside this
        # test's own event loop would bind it to a loop that's about to close,
        # so the lookup runs against this test's client instead.
        shared_db, server.db = server.db, sc.db
        try:
            await server._advocate_profile_or_404(sc.user_id)
            raise AssertionError("deactivated counsel's public profile should 404")
        except HTTPException as exc:
            assert exc.status_code == 404
        finally:
            server.db = shared_db

        # Hearing-time discovery (broadcast pool and a targeted request).
        hearing_ids = [f"hearing_test_{uuid.uuid4().hex[:8]}" for _ in range(2)]
        await sc.db.hearing_requests.insert_many([
            {"hearing_id": hearing_ids[0], "court_id": sc.court_id, "hearing_date": WEDNESDAY},
            {"hearing_id": hearing_ids[1], "court_id": sc.court_id, "hearing_date": WEDNESDAY,
             "target_advocate_id": sc.user_id},
        ])
        try:
            broadcast = await counsel_matching.discover_candidates(sc.db, hearing_ids[0])
            assert sc.user_id not in [c["user_id"] for c in broadcast]
            assert await counsel_matching.discover_candidates(sc.db, hearing_ids[1]) == []
            # Fallback-to-next-counsel after a rejection uses the same search.
            fallback = await counsel_matching.top_fallback_candidates(
                sc.db, {"court_id": sc.court_id, "hearing_date": WEDNESDAY}, set(),
            )
            assert sc.user_id not in [c["user_id"] for c in fallback]
        finally:
            await sc.db.hearing_requests.delete_many({"hearing_id": {"$in": hearing_ids}})
    _run(body, user_overrides={"deleted": True})


def test_active_account_is_still_found_by_discovery_and_fallback():
    async def body(sc):
        hearing_id = f"hearing_test_{uuid.uuid4().hex[:8]}"
        await sc.db.hearing_requests.insert_one({"hearing_id": hearing_id, "target_advocate_id": sc.user_id})
        try:
            assert [c["user_id"] for c in await counsel_matching.discover_candidates(sc.db, hearing_id)] == [sc.user_id]
            fallback = await counsel_matching.top_fallback_candidates(
                sc.db, {"court_id": sc.court_id, "hearing_date": WEDNESDAY}, set(),
            )
            assert sc.user_id in [c["user_id"] for c in fallback]
        finally:
            await sc.db.hearing_requests.delete_many({"hearing_id": hearing_id})
    _run(body)


# ---------------------------------------------------------------------------
# "Visible to clients?" self-check
# ---------------------------------------------------------------------------

def _by_key(result):
    return {c["key"]: c for c in result["checks"]}


def test_visibility_reports_the_three_gaps_from_the_reported_counsel():
    """The dev-DB counsel's exact shape: pending, unverified, free-text courts,
    no pricing, and a slot at a court that isn't on the profile."""
    async def body(sc):
        result = await practice.client_visibility(sc.db, sc.user_id)
        checks = _by_key(result)
        assert result["visible"] is False
        assert checks["kyc_approved"]["ok"] is False
        assert checks["bar_council_verified"]["ok"] is False
        assert checks["courts"]["ok"] is False
        assert "pune high court" in checks["courts_unrecognized"]["message"]
        assert "Delhi High Court (test)" in checks["availability_courts"]["message"]
        assert "2 PM – 5 PM" in checks["availability_pricing"]["message"]
    _run(body, profile_overrides={
        "kyc_status": "pending", "bar_council_verified": None,
        "courts": ["pune high court", "Ahmadabad high Court"], "pricing": None,
    })


def test_visibility_is_clean_for_a_fully_set_up_counsel():
    async def body(sc):
        result = await practice.client_visibility(sc.db, sc.user_id)
        assert result["visible"] is True
        assert [c for c in result["checks"] if not c["ok"]] == []
        assert "Delhi High Court (test)" in _by_key(result)["courts"]["message"]
    _run(body)


def test_visibility_endpoint_is_registered():
    paths = {r.path for r in server.api_router.routes if "GET" in getattr(r, "methods", set())}
    assert any(p.endswith("/practice/visibility") for p in paths)
