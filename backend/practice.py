"""Proxy Counsel practice management — profile and availability. Follows the
same per-domain-module pattern as leads.py/reviews.py/settlements.py, and the
same "one typed collection keyed 1:1 by user_id" shape already used for
db.vendors.

Performance/ratings here stay honest placeholders until the hearing-requests
marketplace exists — real hearing counts, not fabricated activity.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import HTTPException

AVAILABILITY_KINDS = ("recurring_weekly", "custom_date", "holiday_block", "emergency_unavailable")

PROFILE_EDITABLE_FIELDS = (
    "practice_areas", "courts", "languages", "experience_years", "education",
    "bio", "office_address", "fee_structure", "availability_mode", "instant_booking",
)


async def get_or_create_profile(db, user_id: str) -> dict:
    profile = await db.proxy_counsel_profiles.find_one({"user_id": user_id}, {"_id": 0})
    if profile:
        return profile
    now = datetime.now(timezone.utc).isoformat()
    profile = {
        "user_id": user_id,
        "bar_council_number": None,
        "practice_areas": [],
        "courts": [],
        "languages": [],
        "experience_years": None,
        "education": None,
        "bio": None,
        "office_address": None,
        "fee_structure": None,
        "kyc_status": "pending",  # admin-verified, not self-settable — see PROFILE_EDITABLE_FIELDS
        "bar_council_verified": False,  # admin-verified, not self-settable — see PROFILE_EDITABLE_FIELDS
        "availability_mode": False,
        "instant_booking": False,
        "rating": 0,
        "cases_completed": 0,
        "success_rate": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.proxy_counsel_profiles.insert_one(profile)
    profile.pop("_id", None)
    return profile


async def update_profile(db, user_id: str, patch: Dict[str, Any]) -> dict:
    update = {k: v for k, v in patch.items() if k in PROFILE_EDITABLE_FIELDS and v is not None}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await get_or_create_profile(db, user_id)  # ensure a row exists before the upsert-style update
    await db.proxy_counsel_profiles.update_one({"user_id": user_id}, {"$set": update})
    return await get_or_create_profile(db, user_id)


async def approve_kyc(db, user_id: str) -> dict:
    """Admin action. Unlike update_profile, this never auto-creates a row —
    approving KYC for a user_id with no proxy_counsel_profiles row at all is
    an error (typo, or a user who never onboarded as proxy counsel), not a
    silent no-op."""
    result = await db.proxy_counsel_profiles.update_one(
        {"user_id": user_id},
        {"$set": {"kyc_status": "approved", "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Proxy counsel profile not found")
    return await db.proxy_counsel_profiles.find_one({"user_id": user_id}, {"_id": 0})


async def verify_bar_council(db, user_id: str) -> dict:
    """Admin action — same not-auto-create, 404-on-missing-profile semantics
    as approve_kyc."""
    result = await db.proxy_counsel_profiles.update_one(
        {"user_id": user_id},
        {"$set": {"bar_council_verified": True, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Proxy counsel profile not found")
    return await db.proxy_counsel_profiles.find_one({"user_id": user_id}, {"_id": 0})


def _validate_slot(kind: str, day_of_week: Optional[int], date: Optional[str]) -> None:
    if kind not in AVAILABILITY_KINDS:
        raise HTTPException(400, f"Invalid availability kind. Allowed: {', '.join(AVAILABILITY_KINDS)}")
    if kind == "recurring_weekly":
        if day_of_week is None or not 0 <= day_of_week <= 6:
            raise HTTPException(400, "day_of_week (0=Monday..6=Sunday) is required for a recurring weekly slot")
    elif not date:
        raise HTTPException(400, "date is required for this availability kind")


async def add_slot(db, user_id: str, kind: str, day_of_week: Optional[int], date: Optional[str],
                    court_id: Optional[str], start_time: Optional[str], end_time: Optional[str]) -> dict:
    _validate_slot(kind, day_of_week, date)
    slot = {
        "slot_id": f"slot_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "kind": kind,
        "day_of_week": day_of_week,
        "date": date,
        "court_id": court_id,  # null = any court
        "start_time": start_time,  # "HH:MM", null = full day
        "end_time": end_time,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.availability_slots.insert_one(slot)
    slot.pop("_id", None)
    return slot


async def list_slots(db, user_id: str) -> List[dict]:
    return await db.availability_slots.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(500)


async def remove_slot(db, user_id: str, slot_id: str) -> dict:
    result = await db.availability_slots.delete_one({"slot_id": slot_id, "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Slot not found")
    return {"ok": True}


async def performance(db, user_id: str) -> dict:
    profile = await get_or_create_profile(db, user_id)
    upcoming_hearings = await db.hearing_requests.count_documents({
        "proxy_counsel_user_id": user_id, "status": {"$in": ["accepted", "in_progress"]},
    })
    pending_requests = await db.hearing_requests.count_documents({
        "status": "broadcast", "declined_by": {"$ne": user_id},
    })
    return {
        "rating": profile.get("rating", 0),
        "cases_completed": profile.get("cases_completed", 0),
        "success_rate": profile.get("success_rate"),
        "upcoming_hearings": upcoming_hearings,
        "pending_requests": pending_requests,
    }
