"""Bug fix: Primary Courts set on a Proxy Counsel's profile not showing up
in the Counsel's court filter/search (e.g. "Gujarat High Court" as a Primary
Court not surfacing when a Counsel searches/selects Gujarat High Court).

Root cause was on the frontend: Practice.jsx's "Courts" field was a
free-text TagInput, so a proxy counsel typed a display name ("Gujarat High
Court") which got saved verbatim into proxy_counsel_profiles.courts — but
counsel_matching.list_and_recommend (which backs both the AI recommendation
list and the public browse grid) filters that field by real court_id via a
$in query against the courts collection. Free text never matches a
court_id, so the counsel silently never surfaced. Fixed by replacing the
free-text input with a real court picker (Practice.jsx's new CourtPicker)
that stores court_id, same as every other court-aware field in the app.

This test exercises the backend half of that contract directly: a profile
whose `courts` holds the real court_id matches court_id/state_id searches;
one holding the old free-text shape does not — documenting exactly why the
frontend fix (storing ids, not names) is what makes the counsel findable.
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


async def _cleanup(db, court_ids=(), user_ids=()):
    if court_ids:
        await db.courts.delete_many({"court_id": {"$in": list(court_ids)}})
    if user_ids:
        await db.proxy_counsel_profiles.delete_many({"user_id": {"$in": list(user_ids)}})


def test_profile_courts_matches_by_real_court_id():
    async def body():
        db = _db()
        court_id = f"court_test_{uuid.uuid4().hex[:10]}"
        state_id = f"state_test_{uuid.uuid4().hex[:10]}"
        user_id = f"test_counsel_{uuid.uuid4().hex[:10]}"
        try:
            await db.courts.insert_one({
                "court_id": court_id, "name": "Test Gujarat High Court", "type": "high_court",
                "state_id": state_id, "serviceable": True,
            })
            await db.proxy_counsel_profiles.insert_one({
                "user_id": user_id, "kyc_status": "approved", "bar_council_verified": True,
                "courts": [court_id], "practice_areas": [], "languages": [],
                "pricing": {}, "availability_mode": False, "rating": 0, "cases_completed": 0,
            })

            ranked, total = await counsel_matching.list_and_recommend(db, court_id=court_id)
            assert total == 1
            assert ranked[0]["user_id"] == user_id

            # Combined with the state filter (how the browse page's
            # CourtLocationSelector actually narrows), same result.
            ranked, total = await counsel_matching.list_and_recommend(db, state_id=state_id)
            assert total == 1
            assert ranked[0]["user_id"] == user_id
        finally:
            await _cleanup(db, [court_id], [user_id])
    asyncio.run(body())


def test_profile_courts_as_free_text_does_not_match_court_search():
    """Documents the bug: a profile carrying the pre-fix free-text shape
    (a display name typed into the old TagInput, not a real court_id) is
    invisible to the exact search it should have matched."""
    async def body():
        db = _db()
        court_id = f"court_test_{uuid.uuid4().hex[:10]}"
        state_id = f"state_test_{uuid.uuid4().hex[:10]}"
        user_id = f"test_counsel_{uuid.uuid4().hex[:10]}"
        try:
            await db.courts.insert_one({
                "court_id": court_id, "name": "Test Gujarat High Court", "type": "high_court",
                "state_id": state_id, "serviceable": True,
            })
            await db.proxy_counsel_profiles.insert_one({
                "user_id": user_id, "kyc_status": "approved", "bar_council_verified": True,
                "courts": ["Test Gujarat High Court"],  # free text, not the court_id — the bug
                "practice_areas": [], "languages": [],
                "pricing": {}, "availability_mode": False, "rating": 0, "cases_completed": 0,
            })

            ranked, total = await counsel_matching.list_and_recommend(db, court_id=court_id)
            assert total == 0

            ranked, total = await counsel_matching.list_and_recommend(db, state_id=state_id)
            assert total == 0
        finally:
            await _cleanup(db, [court_id], [user_id])
    asyncio.run(body())
