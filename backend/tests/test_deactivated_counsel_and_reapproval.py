"""Two fixes, tested end to end on the conftest's throwaway DB (same pattern
as test_lead_rejection_visibility.py — plain asyncio.run() over Motor):

1. A deactivated account (users.deleted = True) is offered nowhere: public
   listing, public profile, broadcast / targeted / fallback matching, and new
   targeted hearing requests. A missing or false `deleted` field stays
   eligible. Nothing about the account or profile is changed.
2. The application form seeds the practice profile on FIRST activation only:
   re-approval (after reject / more-info, or a repeated Approve) restores
   verification but keeps everything the counsel has since edited.
"""
import asyncio
import os
import sys
import unittest.mock
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import counsel_matching  # noqa: E402
import hearings  # noqa: E402
import leads as leads_svc  # noqa: E402
import practice as practice_svc  # noqa: E402
import server  # noqa: E402

ADMIN = {"user_id": "test_admin_deact", "name": "Test Admin", "role": "admin"}
REQUESTER = "user_deact_requester"


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _emails(*_a, **_k):
    return {"status": "sent"}


# ---------------------------------------------------------------------------
# 1. Deactivated accounts
# ---------------------------------------------------------------------------

DELETED_STATES = {
    "deleted": {"deleted": True},
    "active_false": {"deleted": False},
    "active_missing_field": {},
}


async def _counsel(db, user_fields):
    user_id = f"user_deact_{uuid.uuid4().hex[:10]}"
    await db.users.insert_one({"user_id": user_id, "name": "Deact Test", "role": "proxy_counsel", **user_fields})
    await db.proxy_counsel_profiles.insert_one({
        "user_id": user_id, **counsel_matching.verified_counsel_query(), "availability_mode": True,
        "courts": [], "practice_areas": [], "bio": "kept", "pricing": {"district": {"morning": 800.0}},
    })
    return user_id


async def _snapshot(db, user_id):
    return (await db.users.find_one({"user_id": user_id}, {"_id": 0}),
            await db.proxy_counsel_profiles.find_one({"user_id": user_id}, {"_id": 0}))


async def _offered_everywhere(db, user_id):
    """{surface: offered?} for every path that hands a counsel to a client or to matching."""
    out = {}
    ranked, _ = await counsel_matching.list_and_recommend(db, limit=500)
    out["listing"] = any(c["user_id"] == user_id for c in ranked)
    with unittest.mock.patch.object(server, "db", db):
        try:
            await server._advocate_profile_or_404(user_id)
            out["public_profile"] = True
        except HTTPException as e:
            assert e.status_code == 404
            out["public_profile"] = False
    broadcast_id, targeted_id = f"hearing_deact_{uuid.uuid4().hex[:8]}", f"hearing_deact_{uuid.uuid4().hex[:8]}"
    await db.hearing_requests.insert_many([
        {"hearing_id": broadcast_id, "target_advocate_id": None, "requesting_user_id": REQUESTER},
        {"hearing_id": targeted_id, "target_advocate_id": user_id, "requesting_user_id": REQUESTER},
    ])
    out["broadcast_matching"] = any(c["user_id"] == user_id for c in await counsel_matching.discover_candidates(db, broadcast_id))
    out["existing_targeted_matching"] = any(c["user_id"] == user_id for c in await counsel_matching.discover_candidates(db, targeted_id))
    fallback = await counsel_matching.top_fallback_candidates(db, {"hearing_id": broadcast_id, "court_id": None}, set())
    out["fallback_candidates"] = any(c["user_id"] == user_id for c in fallback)
    try:
        await hearings.create_hearing_request(db, REQUESTER, "court_tishazari", "2026-12-01", "x", 1500.0, None,
                                              target_advocate_id=user_id)
        out["new_targeted_request"] = True
    except HTTPException as e:
        assert e.status_code == 400
        out["new_targeted_request"] = False
    return out


async def _cleanup_counsel(db, user_id):
    await db.users.delete_many({"user_id": user_id})
    await db.proxy_counsel_profiles.delete_many({"user_id": user_id})
    await db.hearing_requests.delete_many({"requesting_user_id": REQUESTER})


@pytest.mark.parametrize("state", list(DELETED_STATES))
def test_deactivated_counsel_offered_nowhere_and_active_ones_everywhere(state):
    async def body():
        db = _db()
        user_id = await _counsel(db, DELETED_STATES[state])
        try:
            before = await _snapshot(db, user_id)
            offered = await _offered_everywhere(db, user_id)
            expected = state != "deleted"
            assert offered == {k: expected for k in offered}, offered
            assert await _snapshot(db, user_id) == before, "no account or profile data may change"
        finally:
            await _cleanup_counsel(db, user_id)
    asyncio.run(body())


def test_reactivated_counsel_is_offered_again():
    async def body():
        db = _db()
        user_id = await _counsel(db, {"deleted": True})
        try:
            assert not any((await _offered_everywhere(db, user_id)).values())
            await db.users.update_one({"user_id": user_id}, {"$set": {"deleted": False}})
            await db.hearing_requests.delete_many({"requesting_user_id": REQUESTER})
            assert all((await _offered_everywhere(db, user_id)).values())
        finally:
            await _cleanup_counsel(db, user_id)
    asyncio.run(body())


def test_deactivating_one_counsel_does_not_hide_another():
    async def body():
        db = _db()
        gone = await _counsel(db, {"deleted": True})
        kept = await _counsel(db, {})
        try:
            offered = await _offered_everywhere(db, kept)
            assert all(offered.values()), offered
        finally:
            await _cleanup_counsel(db, gone)
            await _cleanup_counsel(db, kept)
    asyncio.run(body())


def test_eligible_counsel_query_keeps_verification_gate():
    async def body():
        db = _db()
        user_id = await _counsel(db, {})
        try:
            await db.proxy_counsel_profiles.update_one({"user_id": user_id}, {"$set": {"kyc_status": "pending"}})
            offered = await _offered_everywhere(db, user_id)
            assert not any(offered.values()), offered
        finally:
            await _cleanup_counsel(db, user_id)
    asyncio.run(body())


# ---------------------------------------------------------------------------
# 2. Re-approval keeps counsel-edited profile data
# ---------------------------------------------------------------------------

FORM = {
    "bar_council_information__state_bar_council": "Bar Council of Delhi",
    "bar_council_information__bar_council_enrollment_number": "D/123/2020",
    "professional_details__total_years_of_practice": "3-5 Years",
    "professional_details__primary_area_of_practice": ["Civil Matters"],
    "professional_details__language": "Both",
    "professional_details__primary_court_of_practice": ["Not A Seeded Court Name"],
    "professional_details__current_professional_status": "Independent Practice",
    "professional_details__maximum_distance_you_are_willing_to_travel_for_appearance": "10 km",
    "professional_details__availability": "Weekdays",
}
# What the counsel later changes in My Practice — every field the form also sets.
EDITS = {
    "state_bar_council": "Bar Council of Maharashtra & Goa", "bar_council_number": "MAH/999/2019",
    "experience_bracket": "7-10", "practice_areas": ["Criminal Matters", "Arbitration Matters"],
    "languages": ["English"], "courts": ["court_edited"], "professional_status": "Edited Status",
    "max_travel_distance": "50 km", "schedule_type": "Weekends", "matters_handled": 42,
}
USER_MANAGED = {"bio": "My own About text", "pricing": {"district": {"morning": 1200.0}}, "availability_mode": True}


async def _new_lead(db, email=None):
    email = email or f"test_reappr_{uuid.uuid4().hex[:10]}@example.com"
    lead = {"lead_id": f"lead_{uuid.uuid4().hex[:10]}", "role_applied_for": "proxy_counsel", "status": "submitted",
            "email": email, "email_normalized": email, "full_name": "Reapproval Applicant", "phone": None,
            "form_data": dict(FORM), "submitted_at": datetime.now(timezone.utc).isoformat()}
    await db.leads.insert_one(dict(lead))
    return lead


async def _set(db, lead, status):
    await leads_svc.admin_change_status(db, _emails, lead["lead_id"], status, None, ADMIN)
    return await db.leads.find_one({"lead_id": lead["lead_id"]}, {"_id": 0})


async def _profile(db, user_id):
    return await db.proxy_counsel_profiles.find_one({"user_id": user_id}, {"_id": 0})


async def _approved_and_edited(db):
    """First activation, then the counsel edits their profile and availability."""
    lead = await _set(db, await _new_lead(db), "approved")
    user_id = lead["converted_user_id"]
    await practice_svc.update_profile(db, user_id, {**EDITS, **{k: v for k, v in USER_MANAGED.items() if k != "pricing"}})
    await practice_svc.update_profile(db, user_id, {"pricing": USER_MANAGED["pricing"]})
    slot = await practice_svc.add_slot(db, user_id, "recurring_weekly", 2, None, None, "morning", None)
    return lead, user_id, slot


async def _cleanup_lead(db, lead):
    user = await db.users.find_one({"email": lead["email"]}, {"_id": 0, "user_id": 1})
    if user:
        await db.proxy_counsel_profiles.delete_many({"user_id": user["user_id"]})
        await db.availability_slots.delete_many({"user_id": user["user_id"]})
        await db.users.delete_many({"user_id": user["user_id"]})
    await db.leads.delete_many({"lead_id": lead["lead_id"]})
    await db.lead_status_history.delete_many({"lead_id": lead["lead_id"]})


def _assert_edits_kept(profile, expected_experience_years=None):
    for k, v in {**EDITS, **USER_MANAGED}.items():
        assert profile.get(k) == v, f"{k} was overwritten: {profile.get(k)!r} != {v!r}"
    if expected_experience_years is not None:
        assert profile.get("experience_years") == expected_experience_years


def test_first_activation_still_populates_profile_from_application():
    async def body():
        db = _db()
        lead = await _new_lead(db)
        try:
            lead = await _set(db, lead, "approved")
            profile = await _profile(db, lead["converted_user_id"])
            expected = leads_svc._derive_practice_profile_patch(FORM)
            assert expected, "fixture must exercise the form mapping"
            for k, v in expected.items():
                assert profile.get(k) == v, f"{k}: {profile.get(k)!r} != {v!r}"
            assert profile["kyc_status"] == "approved" and profile["bar_council_verified"] is True
        finally:
            await _cleanup_lead(db, lead)
    asyncio.run(body())


@pytest.mark.parametrize("withdrawn", ["rejected", "more_info_requested"])
def test_reapproval_restores_verification_and_keeps_edits_about_pricing_availability(withdrawn):
    async def body():
        db = _db()
        lead, user_id, slot = await _approved_and_edited(db)
        try:
            edited_years = (await _profile(db, user_id))["experience_years"]
            await _set(db, lead, withdrawn)
            assert (await _profile(db, user_id))["bar_council_verified"] is False
            await _set(db, lead, "approved")
            profile = await _profile(db, user_id)
            assert profile["kyc_status"] == "approved" and profile["bar_council_verified"] is True
            _assert_edits_kept(profile, edited_years)
            slots = await practice_svc.list_slots(db, user_id)
            assert [s["slot_id"] for s in slots] == [slot["slot_id"]]
            ranked, _ = await counsel_matching.list_and_recommend(db, limit=500)
            assert any(c["user_id"] == user_id for c in ranked)
        finally:
            await _cleanup_lead(db, lead)
    asyncio.run(body())


def test_repeated_approval_is_idempotent():
    async def body():
        db = _db()
        lead, user_id, _slot = await _approved_and_edited(db)
        try:
            before = await _profile(db, user_id)
            await _set(db, lead, "approved")
            await _set(db, lead, "approved")
            after = await _profile(db, user_id)
            changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
            assert changed <= {"updated_at"}, f"repeated approval changed: {changed}"
            assert after["verification_source"] == {"type": "lead", "lead_id": lead["lead_id"]}
            assert await db.users.count_documents({"email": lead["email"]}) == 1
        finally:
            await _cleanup_lead(db, lead)
    asyncio.run(body())


def test_existing_profile_is_not_overwritten_by_a_first_application_approval():
    """An account that already has a practice profile (e.g. set up before it
    applied) is not a first activation: its data stays as it is."""
    async def body():
        db = _db()
        email = f"test_reappr_{uuid.uuid4().hex[:10]}@example.com"
        user_id = f"user_reappr_{uuid.uuid4().hex[:10]}"
        await db.users.insert_one({"user_id": user_id, "email": email, "name": "Existing", "role": "client",
                                   "professional_profile_types": ["client"], "password_hash": "x"})
        await practice_svc.get_or_create_profile(db, user_id)
        await practice_svc.update_profile(db, user_id, {**EDITS, "bio": USER_MANAGED["bio"]})
        lead = await _new_lead(db, email=email)
        try:
            await _set(db, lead, "approved")
            profile = await _profile(db, user_id)
            for k, v in EDITS.items():
                assert profile.get(k) == v, f"{k} was overwritten"
            assert profile["kyc_status"] == "approved" and profile["bar_council_verified"] is True
        finally:
            await _cleanup_lead(db, lead)
    asyncio.run(body())


def test_admin_verification_still_survives_rejection_and_reapproval_keeps_admin_source():
    async def body():
        db = _db()
        lead, user_id, _slot = await _approved_and_edited(db)
        try:
            await practice_svc.set_verification_source(db, user_id, {"type": "admin"})
            await _set(db, lead, "rejected")
            profile = await _profile(db, user_id)
            assert profile["kyc_status"] == "approved" and profile["bar_council_verified"] is True
            await _set(db, lead, "approved")
            assert (await _profile(db, user_id))["verification_source"] == {"type": "admin"}
        finally:
            await _cleanup_lead(db, lead)
    asyncio.run(body())
