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
    "state_bar_council", "bar_council_number", "practice_areas", "courts", "languages", "experience_years",
    "experience_bracket", "professional_status", "max_travel_distance", "schedule_type", "matters_handled",
    "education", "bio", "office_address", "fee_structure", "pricing", "availability_mode", "instant_booking",
    "negotiation_enabled",
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
# `max_years` (None for the open-ended "10+") is the bracket's inclusive
# upper bound, used by list_and_recommend to fall back to a numeric
# experience_years range for profiles that have experience_years but no
# self-selected experience_bracket (e.g. backfilled from a lead's "total
# years of practice" bucket — see leads._derive_practice_profile_patch).
EXPERIENCE_BRACKETS = [
    {"key": "0-3", "label": "0–3 yrs", "min_years": 0, "max_years": 3},
    {"key": "3-5", "label": "3–5 yrs", "min_years": 3, "max_years": 5},
    {"key": "5-7", "label": "5–7 yrs", "min_years": 5, "max_years": 7},
    {"key": "7-10", "label": "7–10 yrs", "min_years": 7, "max_years": 10},
    {"key": "10+", "label": "10+ yrs", "min_years": 10, "max_years": None},
]
_EXPERIENCE_BRACKET_YEARS = {b["key"]: b["min_years"] for b in EXPERIENCE_BRACKETS}
_EXPERIENCE_BRACKET_MAX_YEARS = {b["key"]: b["max_years"] for b in EXPERIENCE_BRACKETS}
_EXPERIENCE_BRACKET_LABELS = {b["key"]: b["label"] for b in EXPERIENCE_BRACKETS}
_EXPERIENCE_BRACKET_INDEX = {b["key"]: i for i, b in enumerate(EXPERIENCE_BRACKETS)}

# Founder direction (2026-09, revised): the rate-card floor scales with
# experience — "0-3" pays the base PRICING_MINIMUMS rate unchanged; each
# bracket step above that adds another flat surcharge to every slot's floor,
# same surcharge amount at every step (so "high_court" 3-5/5-7/7-10/10+ are
# +200/+400/+600/+800), but the step size itself differs by court type —
# ₹100/step for district, ₹200/step for high_court, per the founder's
# correction that the original single ₹100-for-both was wrong for high
# courts specifically. Unset/unrecognized bracket (a counsel who hasn't
# picked one yet) falls back to bracket index 0 — i.e. the unmodified base
# rate, never a penalty.
EXPERIENCE_PRICING_SURCHARGE = {"district": 100, "high_court": 200}


def experience_bracket_label(bracket: Optional[str]) -> Optional[str]:
    return _EXPERIENCE_BRACKET_LABELS.get(bracket)


def pricing_minimum(court_type: str, slot: str, experience_bracket: Optional[str] = None) -> float:
    """The actual floor for one (court_type, slot), after the experience
    surcharge — the one place this math happens, so validate_pricing and
    anything that needs to display "Min ₹X" (Practice.jsx's own mirrored
    copy in config/proxyCounselPricing.js) can't drift apart."""
    base = PRICING_MINIMUMS[court_type][slot]
    bracket_index = _EXPERIENCE_BRACKET_INDEX.get(experience_bracket, 0)
    return base + EXPERIENCE_PRICING_SURCHARGE[court_type] * bracket_index


def validate_pricing(pricing: Dict[str, Any], experience_bracket: Optional[str] = None) -> Dict[str, Dict[str, float]]:
    """Clamps to only known court-type/slot keys and rejects anything below
    the platform floor — the one place this is enforced, so a direct API
    call can't slip a below-minimum rate in any more than the form can.
    Slots an advocate leaves out (still deciding on high-court work, say)
    simply aren't in the result — this is additive, not "fill every cell."
    `experience_bracket` shifts the floor itself — see pricing_minimum."""
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
            minimum = pricing_minimum(court_type, slot, experience_bracket)
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
        "state_bar_council": None,
        "bar_council_number": None,
        "practice_areas": [],
        "courts": [],
        "languages": [],
        "experience_years": None,
        "experience_bracket": None,
        "professional_status": None,
        "max_travel_distance": None,
        "schedule_type": None,
        "matters_handled": None,
        "education": None,
        "bio": None,
        "office_address": None,
        "fee_structure": None,
        "pricing": {},
        "kyc_status": "pending",  # admin-verified, not self-settable — see PROFILE_EDITABLE_FIELDS
        "bar_council_verified": False,  # admin-verified, not self-settable — see PROFILE_EDITABLE_FIELDS
        "availability_mode": False,
        "instant_booking": False,
        # Fee negotiation toggle (founder direction, 2026-09): default OFF —
        # a hearing request created against this counsel then carries a
        # fixed price (this counsel's own listed rate for the court type/
        # urgency, same number CounselCard already shows before selection)
        # instead of opening the Negotiation Module at all. See
        # hearings.create_hearing_request's snapshot of this field onto the
        # hearing itself, and negotiation.propose_offer's gate.
        "negotiation_enabled": False,
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
    # Also ensures a row exists before the upsert-style update below, and is
    # the source of the experience_bracket pricing validates against when
    # this same call isn't also changing the bracket.
    current = await get_or_create_profile(db, user_id)
    update = {k: v for k, v in patch.items() if k in PROFILE_EDITABLE_FIELDS and v is not None}
    if "experience_bracket" in update:
        bracket = update["experience_bracket"]
        if bracket not in _EXPERIENCE_BRACKET_YEARS:
            raise HTTPException(400, f"Invalid experience bracket. Allowed: {', '.join(_EXPERIENCE_BRACKET_YEARS)}")
        # Keeps the existing numeric experience_years in sync with the
        # bracket the advocate actually picked, so nothing downstream that
        # reads experience_years as a number (min_experience_years filtering,
        # sort-by-experience) needs to know brackets exist.
        update["experience_years"] = _EXPERIENCE_BRACKET_YEARS[bracket]
    if "pricing" in update:
        # The bracket this same save is also setting, if any — otherwise
        # whatever's already on the profile. Practice.jsx's save() always
        # sends both together, but a direct API call touching only
        # `pricing` must still be checked against the advocate's actual
        # bracket on file, not silently treated as the unmodified "0-3"
        # floor — the surcharge follows the advocate, not the request.
        effective_bracket = update.get("experience_bracket", current.get("experience_bracket"))
        update["pricing"] = validate_pricing(update["pricing"], effective_bracket)
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
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


def is_available_on_date(slots: List[dict], date_str: str) -> bool:
    """Whether a counsel's own availability_slots say they're free on
    `date_str` ("YYYY-MM-DD") — the actual check the browse page's Hearing
    Date filter needs (founder direction, 2026-09): a client who's already
    picked a date shouldn't be shown counsels who can't actually take it.

    No slots configured at all -> permissive default (True). Most counsels
    today have never touched the granular Availability tab at all; treating
    "no schedule" as "unavailable everywhere" would empty out every
    date-filtered search instead of just narrowing it, so this only ever
    excludes on actual evidence of unavailability:
      - an explicit holiday_block/emergency_unavailable for this exact date
        always wins, regardless of anything else, or
      - once a counsel HAS opted into recurring_weekly/custom_date
        scheduling at all, this date has to be one of the ones they
        actually picked (a counsel who only ever set up Mondays is exactly
        who a Wednesday search should exclude)."""
    if not slots:
        return True
    try:
        weekday = datetime.fromisoformat(date_str).weekday()  # 0=Monday..6=Sunday, matches day_of_week's own convention
    except (TypeError, ValueError):
        return True  # unparseable date filter shouldn't hide every counsel
    if any(s.get("kind") in ("holiday_block", "emergency_unavailable") and s.get("date") == date_str for s in slots):
        return False
    positive = [s for s in slots if s.get("kind") in ("recurring_weekly", "custom_date")]
    if not positive:
        return True
    return any(
        (s["kind"] == "custom_date" and s.get("date") == date_str)
        or (s["kind"] == "recurring_weekly" and s.get("day_of_week") == weekday)
        for s in positive
    )


def _validate_slot(kind: str, day_of_week: Optional[int], date: Optional[str], start_time: Optional[str]) -> None:
    if kind not in AVAILABILITY_KINDS:
        raise HTTPException(400, f"Invalid availability kind. Allowed: {', '.join(AVAILABILITY_KINDS)}")
    if kind == "recurring_weekly":
        if day_of_week is None or not 0 <= day_of_week <= 6:
            raise HTTPException(400, "day_of_week (0=Monday..6=Sunday) is required for a recurring weekly slot")
    elif not date:
        raise HTTPException(400, "date is required for this availability kind")
    # Founder direction (2026-09): Practice.jsx's "Time Slot" field is no
    # longer optional-with-a-silent-full-day-default — a counsel must pick
    # one of TIME_OF_DAY_OPTIONS explicitly (Court stays the one genuinely
    # optional field). Enforced here too, not just in the form, so a direct
    # API call can't slip a slotless row in any more than the UI can.
    if not start_time:
        raise HTTPException(400, "A time slot is required")


async def add_slot(db, user_id: str, kind: str, day_of_week: Optional[int], date: Optional[str],
                    court_id: Optional[str], start_time: Optional[str], end_time: Optional[str]) -> dict:
    _validate_slot(kind, day_of_week, date, start_time)
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
