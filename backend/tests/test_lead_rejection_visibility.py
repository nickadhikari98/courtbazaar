"""Rejecting (or sending back) an approved Proxy Counsel application must
withdraw the counsel from the public listing, public profile and new hearing
matching — and re-approval must restore them — without touching profile data
or an admin's independent verification.

Drives the real leads.admin_change_status end to end. Same pattern as
test_recommendations.py: plain asyncio.run() over Motor on the conftest's
throwaway DB, each test creating and cleaning up its own rows.
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
import leads as leads_svc  # noqa: E402
import practice as practice_svc  # noqa: E402
import server  # noqa: E402

ADMIN = {"user_id": "test_admin_rejvis", "name": "Test Admin", "role": "admin"}
PROFILE_DATA = {
    "bio": "About text that must survive",
    "pricing": {"district": {"morning": 750.0}},
    "availability_mode": True,
}


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


class _Emails:
    """Stands in for notifications.send_email; records every call."""
    def __init__(self):
        self.sent = []

    def __call__(self, to, subject, html, *a, **k):
        self.sent.append((to, subject))
        return {"status": "sent"}


async def _new_lead(db, role="proxy_counsel", status="submitted"):
    email = f"test_rejvis_{uuid.uuid4().hex[:10]}@example.com"
    lead = {
        "lead_id": f"lead_{uuid.uuid4().hex[:10]}", "role_applied_for": role, "status": status,
        "email": email, "email_normalized": email, "full_name": "Rejvis Applicant", "phone": None,
        "form_data": {}, "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.leads.insert_one(dict(lead))
    return lead


async def _set_status(db, lead, status, emails):
    await leads_svc.admin_change_status(db, emails, lead["lead_id"], status, None, ADMIN)
    return await db.leads.find_one({"lead_id": lead["lead_id"]}, {"_id": 0})


async def _visibility(db, user_id):
    """Every surface the fix must cover: listing, public profile, broadcast matching."""
    listed = any(c["user_id"] == user_id for c in (await counsel_matching.list_and_recommend(db, limit=500))[0])
    # server.db is bound to whichever event loop first used it; patch in this
    # test's client, same as test_decline_authorization.py.
    with unittest.mock.patch.object(server, "db", db):
        try:
            await server._advocate_profile_or_404(user_id)
            profile_ok = True
        except HTTPException as e:
            assert e.status_code == 404
            profile_ok = False
    hearing_id = f"hearing_rejvis_{uuid.uuid4().hex[:10]}"
    await db.hearing_requests.insert_one({"hearing_id": hearing_id, "target_advocate_id": None})
    try:
        matched = any(c["user_id"] == user_id for c in await counsel_matching.discover_candidates(db, hearing_id))
    finally:
        await db.hearing_requests.delete_many({"hearing_id": hearing_id})
    assert listed == profile_ok == matched, f"surfaces disagree: listed={listed} profile={profile_ok} matched={matched}"
    return listed


async def _cleanup(db, lead):
    user = await db.users.find_one({"email": lead["email"]}, {"_id": 0, "user_id": 1})
    if user:
        await db.proxy_counsel_profiles.delete_many({"user_id": user["user_id"]})
        await db.users.delete_many({"user_id": user["user_id"]})
    await db.leads.delete_many({"lead_id": lead["lead_id"]})
    await db.lead_status_history.delete_many({"lead_id": lead["lead_id"]})


async def _approved_counsel(db, emails):
    """Approve a fresh proxy counsel lead and give the profile real data."""
    lead = await _new_lead(db)
    lead = await _set_status(db, lead, "approved", emails)
    user_id = lead["converted_user_id"]
    await db.proxy_counsel_profiles.update_one({"user_id": user_id}, {"$set": PROFILE_DATA})
    return lead, user_id


@pytest.mark.parametrize("withdrawn_status", ["rejected", "more_info_requested"])
def test_approved_then_withdrawn_is_hidden_everywhere_and_profile_data_kept(withdrawn_status):
    async def body():
        db, emails = _db(), _Emails()
        lead, user_id = await _approved_counsel(db, emails)
        try:
            assert await _visibility(db, user_id) is True
            before = await db.proxy_counsel_profiles.find_one({"user_id": user_id}, {"_id": 0})

            await _set_status(db, lead, withdrawn_status, emails)

            assert await _visibility(db, user_id) is False
            after = await db.proxy_counsel_profiles.find_one({"user_id": user_id}, {"_id": 0})
            assert after["kyc_status"] == "rejected" and after["bar_council_verified"] is False
            changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
            assert changed == {"kyc_status", "bar_council_verified", "updated_at"}, f"unexpected fields changed: {changed}"
            assert await db.users.find_one({"user_id": user_id}) is not None, "account must not be deleted"
        finally:
            await _cleanup(db, lead)
    asyncio.run(body())


def test_reapproval_restores_visibility_with_same_data():
    async def body():
        db, emails = _db(), _Emails()
        lead, user_id = await _approved_counsel(db, emails)
        try:
            await _set_status(db, lead, "rejected", emails)
            assert await _visibility(db, user_id) is False
            await _set_status(db, lead, "approved", emails)
            assert await _visibility(db, user_id) is True
            profile = await db.proxy_counsel_profiles.find_one({"user_id": user_id}, {"_id": 0})
            assert {k: profile.get(k) for k in PROFILE_DATA} == PROFILE_DATA
        finally:
            await _cleanup(db, lead)
    asyncio.run(body())


@pytest.mark.parametrize("final_status", ["rejected", "more_info_requested"])
def test_never_approved_lead_creates_no_profile(final_status):
    async def body():
        db, emails = _db(), _Emails()
        lead = await _new_lead(db, status="submitted")
        try:
            lead = await _set_status(db, lead, final_status, emails)
            assert not lead.get("converted_user_id")
            assert await db.users.find_one({"email": lead["email"]}) is None
        finally:
            await _cleanup(db, lead)
    asyncio.run(body())


@pytest.mark.parametrize("start_status", ["draft", "submitted"])
def test_draft_and_submitted_leads_are_never_listed(start_status):
    async def body():
        db = _db()
        lead = await _new_lead(db, status=start_status)
        try:
            ranked, _ = await counsel_matching.list_and_recommend(db, limit=500)
            assert not lead.get("converted_user_id")
            assert await db.users.find_one({"email": lead["email"]}) is None
            assert all(c.get("user_id") is not None for c in ranked)
        finally:
            await _cleanup(db, lead)
    asyncio.run(body())


def test_admin_verified_counsel_stays_visible_when_their_application_is_rejected():
    async def body():
        db, emails = _db(), _Emails()
        lead, user_id = await _approved_counsel(db, emails)
        try:
            # An admin independently verifies (what the approve-kyc /
            # verify-bar-council endpoints now record), then the application
            # itself is rejected: the admin's verification must stand.
            await practice_svc.approve_kyc(db, user_id)
            await practice_svc.set_verification_source(db, user_id, {"type": "admin"})
            await _set_status(db, lead, "rejected", emails)
            assert await _visibility(db, user_id) is True
        finally:
            await _cleanup(db, lead)
    asyncio.run(body())


def test_already_verified_counsel_is_not_claimed_by_a_new_application():
    async def body():
        db, emails = _db(), _Emails()
        email = f"test_rejvis_{uuid.uuid4().hex[:10]}@example.com"
        user_id = f"user_rejvis_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        lead = None
        try:
            # Legacy counsel: verified before sources were recorded.
            await db.users.insert_one({"user_id": user_id, "email": email, "name": "Legacy", "role": "proxy_counsel",
                                       "password_hash": "x", "professional_profile_types": ["proxy_counsel"], "created_at": now})
            await practice_svc.get_or_create_profile(db, user_id)
            await practice_svc.approve_kyc(db, user_id)
            await practice_svc.verify_bar_council(db, user_id)
            await db.proxy_counsel_profiles.update_one({"user_id": user_id}, {"$set": PROFILE_DATA})

            lead = await _new_lead(db)
            await db.leads.update_one({"lead_id": lead["lead_id"]}, {"$set": {"email": email, "email_normalized": email}})
            lead["email"] = email
            await _set_status(db, lead, "approved", emails)
            await _set_status(db, lead, "rejected", emails)
            assert await _visibility(db, user_id) is True
        finally:
            await db.proxy_counsel_profiles.delete_many({"user_id": user_id})
            await db.users.delete_many({"user_id": user_id})
            if lead:
                await db.leads.delete_many({"lead_id": lead["lead_id"]})
                await db.lead_status_history.delete_many({"lead_id": lead["lead_id"]})
    asyncio.run(body())


def test_rejecting_another_application_does_not_revoke():
    async def body():
        db, emails = _db(), _Emails()
        lead, user_id = await _approved_counsel(db, emails)
        other = await _new_lead(db)
        try:
            # Same account, a second application (re-application) gets
            # converted to it and then rejected: the first approval stands.
            await db.leads.update_one({"lead_id": other["lead_id"]}, {"$set": {"converted_user_id": user_id, "status": "approved"}})
            await _set_status(db, other, "rejected", emails)
            assert await _visibility(db, user_id) is True
        finally:
            await _cleanup(db, lead)
            await db.leads.delete_many({"lead_id": other["lead_id"]})
            await db.lead_status_history.delete_many({"lead_id": other["lead_id"]})
    asyncio.run(body())


def test_non_proxy_counsel_lead_rejection_leaves_proxy_profiles_alone():
    async def body():
        db, emails = _db(), _Emails()
        pc_lead, pc_user = await _approved_counsel(db, emails)
        counsel_lead = await _new_lead(db, role="counsel")
        try:
            counsel_lead = await _set_status(db, counsel_lead, "approved", emails)
            await _set_status(db, counsel_lead, "rejected", emails)
            assert await _visibility(db, pc_user) is True
            assert await db.proxy_counsel_profiles.find_one({"user_id": counsel_lead["converted_user_id"]}) is None
        finally:
            await _cleanup(db, pc_lead)
            await _cleanup(db, counsel_lead)
    asyncio.run(body())


@pytest.mark.parametrize("withdrawn_status", ["rejected", "more_info_requested"])
def test_status_email_still_sent_exactly_once(withdrawn_status):
    async def body():
        db = _db()
        lead, _user_id = await _approved_counsel(db, _Emails())
        emails = _Emails()
        try:
            await _set_status(db, lead, withdrawn_status, emails)
            assert len(emails.sent) == 1 and emails.sent[0][0] == lead["email"]
        finally:
            await _cleanup(db, lead)
    asyncio.run(body())


# ---------------------------------------------------------------------------
# Targeted hearing requests: a counsel picked directly by user_id must pass the
# same verification gate as the listing and broadcast matching.
# ---------------------------------------------------------------------------
import hearings  # noqa: E402

REQUESTER = "user_rejvis_requester"


async def _targeted(db, target_id):
    return await hearings.create_hearing_request(
        db, REQUESTER, "court_tishazari", "2026-12-01", "Test case", 1500.0, None, target_advocate_id=target_id,
    )


async def _cleanup_hearings(db):
    await db.hearing_requests.delete_many({"requesting_user_id": REQUESTER})


def test_targeted_request_to_revoked_counsel_is_refused():
    async def body():
        db, emails = _db(), _Emails()
        lead, user_id = await _approved_counsel(db, emails)
        try:
            await _set_status(db, lead, "rejected", emails)
            with pytest.raises(HTTPException) as e:
                await _targeted(db, user_id)
            assert e.value.status_code == 400
            assert await db.hearing_requests.count_documents({"requesting_user_id": REQUESTER}) == 0
        finally:
            await _cleanup_hearings(db)
            await _cleanup(db, lead)
    asyncio.run(body())


@pytest.mark.parametrize("profile", [
    None,  # no proxy counsel profile at all
    {"kyc_status": "pending", "bar_council_verified": False},
    {"kyc_status": "approved", "bar_council_verified": False},
    {"kyc_status": "pending", "bar_council_verified": True},
])
def test_targeted_request_to_unverified_counsel_is_refused(profile):
    async def body():
        db = _db()
        user_id = f"user_rejvis_{uuid.uuid4().hex[:10]}"
        try:
            if profile is not None:
                await db.proxy_counsel_profiles.insert_one({"user_id": user_id, **profile})
            with pytest.raises(HTTPException) as e:
                await _targeted(db, user_id)
            assert e.value.status_code == 400
        finally:
            await _cleanup_hearings(db)
            await db.proxy_counsel_profiles.delete_many({"user_id": user_id})
    asyncio.run(body())


def test_targeted_request_to_verified_counsel_still_works_and_snapshots_negotiation():
    async def body():
        db, emails = _db(), _Emails()
        lead, user_id = await _approved_counsel(db, emails)
        try:
            await db.proxy_counsel_profiles.update_one({"user_id": user_id}, {"$set": {"negotiation_enabled": True}})
            hearing = await _targeted(db, user_id)
            assert hearing["target_advocate_id"] == user_id and hearing["negotiation_enabled"] is True
        finally:
            await _cleanup_hearings(db)
            await _cleanup(db, lead)
    asyncio.run(body())


def test_existing_targeted_hearing_to_later_revoked_counsel_matches_nobody_and_is_not_modified():
    async def body():
        db, emails = _db(), _Emails()
        lead, user_id = await _approved_counsel(db, emails)
        try:
            hearing = await _targeted(db, user_id)
            assert [c["user_id"] for c in await counsel_matching.discover_candidates(db, hearing["hearing_id"])] == [user_id]
            stored_before = await db.hearing_requests.find_one({"hearing_id": hearing["hearing_id"]}, {"_id": 0})

            await _set_status(db, lead, "rejected", emails)

            assert await counsel_matching.discover_candidates(db, hearing["hearing_id"]) == []
            stored_after = await db.hearing_requests.find_one({"hearing_id": hearing["hearing_id"]}, {"_id": 0})
            assert stored_after == stored_before, "revocation must not modify existing hearing records"
        finally:
            await _cleanup_hearings(db)
            await _cleanup(db, lead)
    asyncio.run(body())


def test_targeted_request_to_verified_counsel_without_negotiation_field_works():
    """Profiles predating the negotiation toggle have no negotiation_enabled
    field; the verified lookup must not mistake that match for "not found"."""
    async def body():
        db = _db()
        user_id = f"user_rejvis_{uuid.uuid4().hex[:10]}"
        try:
            await db.proxy_counsel_profiles.insert_one({"user_id": user_id, **counsel_matching.verified_counsel_query()})
            hearing = await _targeted(db, user_id)
            assert hearing["target_advocate_id"] == user_id and hearing["negotiation_enabled"] is False
        finally:
            await _cleanup_hearings(db)
            await db.proxy_counsel_profiles.delete_many({"user_id": user_id})
    asyncio.run(body())
