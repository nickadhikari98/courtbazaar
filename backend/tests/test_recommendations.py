"""Proxy Counsel Page — AI Recommendations + Filters (founder follow-up,
post-roadmap) and the lead-approval KYC sync fix.

Same rationale/pattern as test_counsel_matching_discovery.py: no pytest
fixtures, plain asyncio.run() wrappers over Motor, each test creates its own
throwaway rows and cleans them up in a finally block.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import counsel_matching  # noqa: E402
import leads as leads_svc  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _profile(user_id, **overrides):
    profile = {
        "user_id": user_id,
        "kyc_status": "approved",
        "bar_council_verified": True,
        "availability_mode": True,
        "practice_areas": [], "courts": [],
        "experience_years": 0, "rating": 0, "cases_completed": 0,
        "fee_structure": None, "instant_booking": False,
    }
    profile.update(overrides)
    return profile


async def _cleanup(db, user_ids=()):
    if user_ids:
        await db.proxy_counsel_profiles.delete_many({"user_id": {"$in": list(user_ids)}})


# ---------------------------------------------------------------------------
# extract_fee_amount
# ---------------------------------------------------------------------------

def test_extract_fee_amount_parses_leading_number():
    assert counsel_matching.extract_fee_amount("Rs.2,000 per appearance") == 2000.0
    assert counsel_matching.extract_fee_amount("₹1500") == 1500.0


def test_extract_fee_amount_none_when_unparseable_or_absent():
    assert counsel_matching.extract_fee_amount(None) is None
    assert counsel_matching.extract_fee_amount("") is None
    assert counsel_matching.extract_fee_amount("Negotiable") is None


# ---------------------------------------------------------------------------
# list_and_recommend — filters + AI ranking (Task 2 + Task 3)
# ---------------------------------------------------------------------------

def test_list_and_recommend_ranks_highest_score_first():
    async def body():
        db = _db()
        low = f"test_counsel_{uuid.uuid4().hex[:8]}"
        high = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            await db.proxy_counsel_profiles.insert_one(_profile(low, rating=1, cases_completed=0, experience_years=0))
            await db.proxy_counsel_profiles.insert_one(_profile(high, rating=5, cases_completed=50, experience_years=20))
            ranked, total = await counsel_matching.list_and_recommend(db)
            ids = [c["user_id"] for c in ranked]
            assert high in ids and low in ids
            assert ids.index(high) < ids.index(low)
            assert ranked[0]["confidence_score"] >= ranked[-1]["confidence_score"]
            assert total >= 2
        finally:
            await _cleanup(db, [low, high])
    asyncio.run(body())


def test_list_and_recommend_excludes_unverified():
    async def body():
        db = _db()
        pending = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            await db.proxy_counsel_profiles.insert_one(_profile(pending, kyc_status="pending"))
            ranked, _ = await counsel_matching.list_and_recommend(db)
            assert not any(c["user_id"] == pending for c in ranked)
        finally:
            await _cleanup(db, [pending])
    asyncio.run(body())


def test_list_and_recommend_does_not_hard_gate_on_availability():
    """Unlike discover_candidates (hearing-time), the browse/recommend page
    should still surface a currently-unavailable counsel — availability is
    only a filter here (available_only), not a baked-in requirement."""
    async def body():
        db = _db()
        unavailable = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            await db.proxy_counsel_profiles.insert_one(_profile(unavailable, availability_mode=False))
            ranked, _ = await counsel_matching.list_and_recommend(db)
            assert any(c["user_id"] == unavailable for c in ranked)
            ranked_filtered, _ = await counsel_matching.list_and_recommend(db, available_only=True)
            assert not any(c["user_id"] == unavailable for c in ranked_filtered)
        finally:
            await _cleanup(db, [unavailable])
    asyncio.run(body())


def test_list_and_recommend_specialization_filter_is_case_insensitive():
    async def body():
        db = _db()
        criminal = f"test_counsel_{uuid.uuid4().hex[:8]}"
        civil = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            await db.proxy_counsel_profiles.insert_one(_profile(criminal, practice_areas=["Criminal"]))
            await db.proxy_counsel_profiles.insert_one(_profile(civil, practice_areas=["Civil"]))
            ranked, total = await counsel_matching.list_and_recommend(db, specialization="criminal")
            ids = {c["user_id"] for c in ranked}
            assert criminal in ids
            assert civil not in ids
            # >=1 rather than ==1: this queries the real shared dev collection,
            # not an isolated fixture, so other "Criminal" specialists may
            # legitimately exist alongside this test's own throwaway rows.
            assert total >= 1
        finally:
            await _cleanup(db, [criminal, civil])
    asyncio.run(body())


def test_list_and_recommend_experience_and_rating_filters():
    async def body():
        db = _db()
        junior = f"test_counsel_{uuid.uuid4().hex[:8]}"
        senior = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            await db.proxy_counsel_profiles.insert_one(_profile(junior, experience_years=2, rating=2))
            await db.proxy_counsel_profiles.insert_one(_profile(senior, experience_years=15, rating=4.8))
            ranked, _ = await counsel_matching.list_and_recommend(db, min_experience_years=10, min_rating=4)
            ids = {c["user_id"] for c in ranked}
            assert senior in ids
            assert junior not in ids
        finally:
            await _cleanup(db, [junior, senior])
    asyncio.run(body())


def test_list_and_recommend_fee_range_filter():
    async def body():
        db = _db()
        cheap = f"test_counsel_{uuid.uuid4().hex[:8]}"
        pricey = f"test_counsel_{uuid.uuid4().hex[:8]}"
        unparseable = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            await db.proxy_counsel_profiles.insert_one(_profile(cheap, fee_structure="Rs.500 per appearance"))
            await db.proxy_counsel_profiles.insert_one(_profile(pricey, fee_structure="Rs.10,000 per appearance"))
            await db.proxy_counsel_profiles.insert_one(_profile(unparseable, fee_structure="Negotiable"))
            ranked, _ = await counsel_matching.list_and_recommend(db, fee_min=1000, fee_max=20000)
            ids = {c["user_id"] for c in ranked}
            assert pricey in ids
            assert cheap not in ids
            assert unparseable not in ids  # unparseable fee can't be verified in-range
        finally:
            await _cleanup(db, [cheap, pricey, unparseable])
    asyncio.run(body())


def test_list_and_recommend_experience_bracket_filter():
    """Founder follow-up (2026-08): the browse page filters by exact bracket
    ("0-3"/"3-5"/"5-7"/"10+"), not an open-ended "at least N years" number —
    a "5-7" filter must exclude a "10+" counsel, not just anyone below 5."""
    async def body():
        db = _db()
        junior = f"test_counsel_{uuid.uuid4().hex[:8]}"
        mid = f"test_counsel_{uuid.uuid4().hex[:8]}"
        senior = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            await db.proxy_counsel_profiles.insert_one(_profile(junior, experience_bracket="0-3"))
            await db.proxy_counsel_profiles.insert_one(_profile(mid, experience_bracket="5-7"))
            await db.proxy_counsel_profiles.insert_one(_profile(senior, experience_bracket="10+"))
            ranked, _ = await counsel_matching.list_and_recommend(db, experience_bracket="5-7")
            ids = {c["user_id"] for c in ranked}
            assert mid in ids
            assert junior not in ids
            assert senior not in ids
        finally:
            await _cleanup(db, [junior, mid, senior])
    asyncio.run(body())


def test_list_and_recommend_experience_bracket_rejects_invalid_value():
    async def body():
        db = _db()
        try:
            await counsel_matching.list_and_recommend(db, experience_bracket="not-a-bracket")
            assert False, "expected HTTPException for an invalid bracket"
        except Exception as e:
            assert getattr(e, "status_code", None) == 400
    asyncio.run(body())


def test_list_and_recommend_time_slot_filter():
    """A counsel who hasn't priced the "morning" slot at all hasn't said
    they take that kind of work — filtering by time_slot="morning" must
    exclude them, matching only counsels with that slot priced under either
    court type."""
    async def body():
        db = _db()
        morning_only = f"test_counsel_{uuid.uuid4().hex[:8]}"
        afternoon_only = f"test_counsel_{uuid.uuid4().hex[:8]}"
        high_court_morning = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            await db.proxy_counsel_profiles.insert_one(_profile(morning_only, pricing={"district": {"morning": 500}}))
            await db.proxy_counsel_profiles.insert_one(_profile(afternoon_only, pricing={"district": {"afternoon": 500}}))
            await db.proxy_counsel_profiles.insert_one(_profile(high_court_morning, pricing={"high_court": {"morning": 1000}}))
            ranked, _ = await counsel_matching.list_and_recommend(db, time_slot="morning")
            ids = {c["user_id"] for c in ranked}
            assert morning_only in ids
            assert high_court_morning in ids
            assert afternoon_only not in ids
        finally:
            await _cleanup(db, [morning_only, afternoon_only, high_court_morning])
    asyncio.run(body())


def test_list_and_recommend_time_slot_rejects_invalid_value():
    async def body():
        db = _db()
        try:
            await counsel_matching.list_and_recommend(db, time_slot="not-a-slot")
            assert False, "expected HTTPException for an invalid time slot"
        except Exception as e:
            assert getattr(e, "status_code", None) == 400
    asyncio.run(body())


def test_list_and_recommend_court_id_filter():
    async def body():
        db = _db()
        at_court = f"test_counsel_{uuid.uuid4().hex[:8]}"
        elsewhere = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            await db.proxy_counsel_profiles.insert_one(_profile(at_court, courts=["court_tishazari"]))
            await db.proxy_counsel_profiles.insert_one(_profile(elsewhere, courts=["court_saket"]))
            ranked, _ = await counsel_matching.list_and_recommend(db, court_id="court_tishazari")
            ids = {c["user_id"] for c in ranked}
            assert at_court in ids
            assert elsewhere not in ids
        finally:
            await _cleanup(db, [at_court, elsewhere])
    asyncio.run(body())


def test_list_and_recommend_court_id_combines_with_location_not_overrides_it():
    """Regression for the founder's Step 3 flow: a court filter applied on
    top of an already-selected state/city must narrow *within* that
    location, not silently override it. court_saket is in Delhi's "South"
    district, not "Central" — asking for state_delhi + Central + court_saket
    together is a contradictory combination and must match nothing, not
    fall back to matching on court_saket alone."""
    async def body():
        db = _db()
        counsel_id = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            await db.proxy_counsel_profiles.insert_one(_profile(counsel_id, courts=["court_saket"]))
            contradictory, _ = await counsel_matching.list_and_recommend(
                db, state_id="state_delhi", district="Central", court_id="court_saket",
            )
            assert not any(c["user_id"] == counsel_id for c in contradictory)

            consistent, _ = await counsel_matching.list_and_recommend(
                db, state_id="state_delhi", district="South", court_id="court_saket",
            )
            assert any(c["user_id"] == counsel_id for c in consistent)
        finally:
            await _cleanup(db, [counsel_id])
    asyncio.run(body())


def test_list_and_recommend_limit_truncates_but_total_reflects_all_matches():
    async def body():
        db = _db()
        ids = [f"test_counsel_{uuid.uuid4().hex[:8]}" for _ in range(3)]
        try:
            for uid in ids:
                await db.proxy_counsel_profiles.insert_one(_profile(uid))
            ranked, total = await counsel_matching.list_and_recommend(db, limit=1)
            assert len(ranked) == 1
            assert total >= 3
        finally:
            await _cleanup(db, ids)
    asyncio.run(body())


# ---------------------------------------------------------------------------
# Task 1 — Admin KYC Approval Sync: approving a proxy_counsel lead now flips
# kyc_status to "approved" via the existing practice.approve_kyc, instead of
# leaving it "pending" after get_or_create_profile.
# ---------------------------------------------------------------------------

def test_activate_professional_sets_kyc_approved_for_new_account():
    async def body():
        db = _db()
        email = f"test_lead_{uuid.uuid4().hex[:10]}@example.test"
        lead = {
            "lead_id": f"lead_{uuid.uuid4().hex[:10]}",
            "role_applied_for": "proxy_counsel",
            "email": email, "email_normalized": email,
            "full_name": "Test Applicant", "phone": None,
        }
        try:
            await leads_svc._activate_professional(db, lead)
            user = await db.users.find_one({"email": email}, {"_id": 0})
            assert user is not None
            profile = await db.proxy_counsel_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
            assert profile is not None
            assert profile["kyc_status"] == "approved", f"expected kyc_status approved, got {profile['kyc_status']}"
            assert profile["bar_council_verified"] is True, "bar_council_verified must also be set, or the counsel still fails verified_counsel_query()"

            # Closes the loop: an approved lead must actually be matchable,
            # not just carry the right flags in isolation.
            ranked, _ = await counsel_matching.list_and_recommend(db)
            assert any(c["user_id"] == user["user_id"] for c in ranked), "newly-approved counsel did not appear in recommendations"
        finally:
            user = await db.users.find_one({"email": email}, {"_id": 0})
            if user:
                await db.proxy_counsel_profiles.delete_many({"user_id": user["user_id"]})
                await db.users.delete_many({"email": email})
    asyncio.run(body())


def test_activate_professional_sets_kyc_approved_for_existing_account():
    async def body():
        db = _db()
        email = f"test_lead_{uuid.uuid4().hex[:10]}@example.test"
        user_id = f"user_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        try:
            await db.users.insert_one({
                "user_id": user_id, "email": email, "name": "Existing User",
                "role": "customer", "password_hash": "x", "professional_profile_types": [],
                "created_at": now,
            })
            lead = {
                "lead_id": f"lead_{uuid.uuid4().hex[:10]}",
                "role_applied_for": "proxy_counsel",
                "email": email, "email_normalized": email,
                "full_name": "Existing User", "phone": None,
            }
            await leads_svc._activate_professional(db, lead)
            profile = await db.proxy_counsel_profiles.find_one({"user_id": user_id}, {"_id": 0})
            assert profile is not None
            assert profile["kyc_status"] == "approved"
            assert profile["bar_council_verified"] is True
        finally:
            await db.proxy_counsel_profiles.delete_many({"user_id": user_id})
            await db.users.delete_many({"user_id": user_id})
    asyncio.run(body())


def test_activate_professional_does_not_touch_kyc_for_counsel_role():
    """role_applied_for == "counsel" maps to the "advocate" account role, not
    proxy_counsel — there's no proxy_counsel_profiles row to sync KYC onto,
    and this must not create one."""
    async def body():
        db = _db()
        email = f"test_lead_{uuid.uuid4().hex[:10]}@example.test"
        lead = {
            "lead_id": f"lead_{uuid.uuid4().hex[:10]}",
            "role_applied_for": "counsel",
            "email": email, "email_normalized": email,
            "full_name": "Test Counsel Applicant", "phone": None,
        }
        try:
            await leads_svc._activate_professional(db, lead)
            user = await db.users.find_one({"email": email}, {"_id": 0})
            assert user is not None
            assert user["role"] == "advocate"
            profile = await db.proxy_counsel_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
            assert profile is None
        finally:
            user = await db.users.find_one({"email": email}, {"_id": 0})
            if user:
                await db.users.delete_many({"email": email})
    asyncio.run(body())
