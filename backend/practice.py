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
    "practice_areas", "courts", "languages", "experience_years", "experience_bracket", "education",
    "bio", "office_address", "fee_structure", "pricing", "availability_mode", "instant_booking",
)

# Founder-set rate card (2026-08): a proxy counsel names their own price per
# slot, but never below this platform floor — "no one can hire advocates
# less than this price." Two independent tables (district vs high court,
# roughly 2x) rather than one scaled by court type, since that's how the
# founder specified it. Order matters — it's also the display order on both
# the profile form and the public profile.
PRICING_SLOTS = ["morning", "afternoon", "full_day", "weekend", "urgent"]
PRICING_SLOT_LABELS = {
    "morning": "10 AM – 1 PM",
    "afternoon": "2 PM – 5 PM",
    "full_day": "Full Day",
    "weekend": "Weekends",
    "urgent": "Urgent (same-day)",
}
PRICING_COURT_TYPES = ["district", "high_court"]
PRICING_COURT_TYPE_LABELS = {"district": "District Courts", "high_court": "High Courts"}
PRICING_MINIMUMS = {
    "district": {"morning": 499, "afternoon": 499, "full_day": 899, "weekend": 1999, "urgent": 1999},
    "high_court": {"morning": 999, "afternoon": 999, "full_day": 1499, "weekend": 2999, "urgent": 2999},
}

# Brackets, not a raw number — "in form it's named total years of practice"
# (founder direction, 2026-08). `min_years` is what a submitted bracket
# resolves to for the existing numeric experience_years field (kept in sync
# so counsel_matching.list_and_recommend's min_experience_years filter and
# any sort-by-experience keep working unchanged) — the bracket's lower bound,
# so "at least 5 years" correctly includes both the "5-7" and "10+" brackets.
EXPERIENCE_BRACKETS = [
    {"key": "0-3", "label": "0–3 yrs", "min_years": 0},
    {"key": "3-5", "label": "3–5 yrs", "min_years": 3},
    {"key": "5-7", "label": "5–7 yrs", "min_years": 5},
    {"key": "10+", "label": "10+ yrs", "min_years": 10},
]
_EXPERIENCE_BRACKET_YEARS = {b["key"]: b["min_years"] for b in EXPERIENCE_BRACKETS}
_EXPERIENCE_BRACKET_LABELS = {b["key"]: b["label"] for b in EXPERIENCE_BRACKETS}


def experience_bracket_label(bracket: Optional[str]) -> Optional[str]:
    return _EXPERIENCE_BRACKET_LABELS.get(bracket)


def validate_pricing(pricing: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """Clamps to only known court-type/slot keys and rejects anything below
    the platform floor — the one place this is enforced, so a direct API
    call can't slip a below-minimum rate in any more than the form can.
    Slots an advocate leaves out (still deciding on high-court work, say)
    simply aren't in the result — this is additive, not "fill every cell."""
    cleaned: Dict[str, Dict[str, float]] = {}
    for court_type, slots in (pricing or {}).items():
        if court_type not in PRICING_COURT_TYPES or not isinstance(slots, dict):
            continue
        cleaned_slots = {}
        for slot, amount in slots.items():
            if slot not in PRICING_SLOTS or amount in (None, ""):
                continue
            try:
                amount = float(amount)
            except (TypeError, ValueError):
                raise HTTPException(400, f"Invalid price for {PRICING_COURT_TYPE_LABELS[court_type]} / {PRICING_SLOT_LABELS[slot]}")
            minimum = PRICING_MINIMUMS[court_type][slot]
            if amount < minimum:
                raise HTTPException(
                    400,
                    f"{PRICING_COURT_TYPE_LABELS[court_type]} / {PRICING_SLOT_LABELS[slot]} must be at least ₹{minimum:g}",
                )
            cleaned_slots[slot] = amount
        if cleaned_slots:
            cleaned[court_type] = cleaned_slots
    return cleaned


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
        "experience_bracket": None,
        "education": None,
        "bio": None,
        "office_address": None,
        "fee_structure": None,
        "pricing": {},
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
    if "pricing" in update:
        update["pricing"] = validate_pricing(update["pricing"])
    if "experience_bracket" in update:
        bracket = update["experience_bracket"]
        if bracket not in _EXPERIENCE_BRACKET_YEARS:
            raise HTTPException(400, f"Invalid experience bracket. Allowed: {', '.join(_EXPERIENCE_BRACKET_YEARS)}")
        # Keeps the existing numeric experience_years in sync with the
        # bracket the advocate actually picked, so nothing downstream that
        # reads experience_years as a number (min_experience_years filtering,
        # sort-by-experience) needs to know brackets exist.
        update["experience_years"] = _EXPERIENCE_BRACKET_YEARS[bracket]
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
