"""Bug fix: My Practice → Proxy Counsel Profile losing Availability & Pricing
(pricing grid) and experience_bracket on the second edit.

Root cause: ProxyCounselProfileUpdate (server.py) declared neither
`pricing` nor `experience_bracket`, even though both are in
practice.PROFILE_EDITABLE_FIELDS and sent by Practice.jsx's save() on every
submit. Pydantic silently drops fields a model doesn't declare, so the PUT
looked successful (no error, "Profile saved") while those two fields were
never actually written to the DB — the next time the profile loaded fresh,
they appeared cleared.

This test exercises both halves: the request model actually keeps the
fields (regression guard against re-dropping them), and practice.update_profile
persists + returns them across what simulates two separate profile loads.
"""
import asyncio
import os
import sys
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import practice  # noqa: E402
from server import ProxyCounselProfileUpdate  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def test_request_model_declares_pricing_and_experience_bracket():
    payload = ProxyCounselProfileUpdate(
        pricing={"district": {"urgent": 2500}}, experience_bracket="5-7", bio="Test bio",
    )
    dumped = payload.model_dump(exclude_unset=True)
    assert dumped.get("pricing") == {"district": {"urgent": 2500}}
    assert dumped.get("experience_bracket") == "5-7"


def test_pricing_and_experience_bracket_survive_a_second_load():
    async def body():
        db = _db()
        user_id = f"test_practice_{uuid.uuid4().hex[:10]}"
        try:
            # First "edit": what Practice.jsx's save() actually sends —
            # through the same Pydantic model server.py's endpoint uses.
            payload = ProxyCounselProfileUpdate(
                pricing={"district": {"urgent": 2500}, "high_court": {"full_day": 1900}},
                experience_bracket="5-7",
                bio="Handles urgent matters",
            )
            updated = await practice.update_profile(db, user_id, payload.model_dump(exclude_unset=True))
            assert updated["pricing"] == {"district": {"urgent": 2500}, "high_court": {"full_day": 1900}}
            assert updated["experience_bracket"] == "5-7"

            # Second "edit": simulates the page being reopened — a fresh
            # fetch (Practice.jsx remounts ProfileTab with the profile
            # freshly loaded from GET /practice/profile), then only the bio
            # is changed, same as a user editing one field.
            reloaded = await practice.get_or_create_profile(db, user_id)
            assert reloaded["pricing"] == {"district": {"urgent": 2500}, "high_court": {"full_day": 1900}}
            assert reloaded["experience_bracket"] == "5-7"

            payload2 = ProxyCounselProfileUpdate(
                pricing=reloaded["pricing"], experience_bracket=reloaded["experience_bracket"],
                bio="Updated bio only",
            )
            updated2 = await practice.update_profile(db, user_id, payload2.model_dump(exclude_unset=True))
            assert updated2["pricing"] == {"district": {"urgent": 2500}, "high_court": {"full_day": 1900}}
            assert updated2["experience_bracket"] == "5-7"
            assert updated2["bio"] == "Updated bio only"
        finally:
            await db.proxy_counsel_profiles.delete_many({"user_id": user_id})
    asyncio.run(body())
