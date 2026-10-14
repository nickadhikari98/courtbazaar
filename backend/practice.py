"""Proxy Counsel practice management — profile and availability. Follows the
same per-domain-module pattern as leads.py/reviews.py/settlements.py, and the
same "one typed collection keyed 1:1 by user_id" shape already used for
db.vendors.

Performance/ratings here stay honest placeholders until the hearing-requests
marketplace exists — real hearing counts, not fabricated activity.
"""
import uuid
from datetime import datetime, timedelta, timezone
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


# The four time-of-day labels Practice.jsx's Availability "Time Slot" picker
# offers (TIME_OF_DAY_OPTIONS — every PRICING_SLOT_LABELS entry except
# "urgent"). The only start_time values a slot may be saved with.
AVAILABILITY_TIME_LABELS = [PRICING_SLOT_LABELS[s] for s in PRICING_SLOTS if s != "urgent"]
_LABEL_TO_PRICING_SLOT = {PRICING_SLOT_LABELS[s]: s for s in PRICING_SLOTS}
# Clock windows (minutes since midnight) behind the two timed labels, used
# only to place legacy clock-time rows — see _slot_windows.
_CLOCK_WINDOWS = {"morning": (10 * 60, 13 * 60), "afternoon": (14 * 60, 17 * 60)}
# Courts and counsels are in India (no DST), so "today" for a dated slot is
# the IST calendar date, not the server's UTC one.
_IST = timezone(timedelta(hours=5, minutes=30))
_DATED_KINDS = ("custom_date", "holiday_block", "emergency_unavailable")


def _today_ist() -> str:
    return datetime.now(_IST).date().isoformat()


def _parse_clock(value: Optional[str]) -> Optional[int]:
    try:
        hours, minutes = (int(part) for part in str(value).split(":")[:2])
    except (TypeError, ValueError):
        return None
    if 0 <= hours <= 23 and 0 <= minutes <= 59:
        return hours * 60 + minutes
    return None


def _slot_windows(slot: dict) -> Optional[frozenset]:
    """Which PRICING_SLOTS a saved availability row actually covers, or None
    for "the whole day / any slot".

    Bug fix (2026-10, My Availability): the Availability form used to save
    literal clock times (start_time "09:03", end_time "18:03"), then switched
    to the time-of-day labels above — but rows saved before the switch were
    never migrated, and matching compared start_time to a label by exact
    string. A legacy "09:03–18:03" holiday block therefore matched neither
    "10 AM – 1 PM" nor "2 PM – 5 PM" and never blocked a timed search: the
    counsel kept showing as bookable on a day they had blocked. Legacy rows
    are now mapped onto the label windows they overlap (and count for a
    weekend search too, since they name real hours on that day); a missing
    or unreadable start_time stays permissive, as before."""
    start = slot.get("start_time")
    if not start:
        return None
    pricing_slot = _LABEL_TO_PRICING_SLOT.get(start)
    if pricing_slot == "full_day":
        return None
    if pricing_slot:
        return frozenset({pricing_slot})
    start_min = _parse_clock(start)
    if start_min is None:
        return None
    end_min = _parse_clock(slot.get("end_time"))
    if end_min is None or end_min <= start_min:
        end_min = 24 * 60
    covered = {key for key, (lo, hi) in _CLOCK_WINDOWS.items() if start_min < hi and end_min > lo}
    if covered:
        covered.add("weekend")
    return frozenset(covered)


def _slot_overlaps_time(slot: dict, time_slot: Optional[str]) -> bool:
    """Bug fix (2026-09): is_available_on_date used to only compare
    kind+date, ignoring each row's own time of day — so a holiday_block
    scoped to just "2 PM – 5 PM" excluded a counsel from every search on
    that date, including an unrelated 10 AM – 1 PM one. "Full Day" on either
    side always overlaps (it covers/needs the whole day); no time_slot
    filter ("Any time slot") or a row with no time stays permissive — only
    an explicit, differing time-of-day pair is distinguished."""
    windows = _slot_windows(slot)
    if windows is None or not time_slot:
        return True
    if time_slot == "full_day":
        return bool(windows)
    return time_slot in windows


def is_available_on_date(slots: List[dict], date_str: str, time_slot: Optional[str] = None) -> bool:
    """Whether a counsel's own availability_slots say they're free on
    `date_str` ("YYYY-MM-DD"), optionally narrowed to the browse page's own
    Time Slot filter (`time_slot`, one of practice.PRICING_SLOTS minus
    "urgent" — see _slot_overlaps_time) — the actual check the browse
    page's Hearing Date filter needs (founder direction, 2026-09): a client
    who's already picked a date shouldn't be shown counsels who can't
    actually take it.

    No slots configured at all -> permissive default (True). Most counsels
    today have never touched the granular Availability tab at all; treating
    "no schedule" as "unavailable everywhere" would empty out every
    date-filtered search instead of just narrowing it, so this only ever
    excludes on actual evidence of unavailability:
      - an explicit holiday_block/emergency_unavailable for this exact date
        AND whose own time-of-day actually overlaps `time_slot` wins,
        regardless of anything else, or
      - once a counsel HAS opted into recurring_weekly/custom_date
        scheduling at all, this date has to be one of the ones they
        actually picked, with an overlapping time-of-day too (a counsel who
        only ever set up Mondays is exactly who a Wednesday search should
        exclude; one who only opened up mornings is exactly who an
        afternoon search should exclude)."""
    if not slots:
        return True
    try:
        weekday = datetime.fromisoformat(date_str).weekday()  # 0=Monday..6=Sunday, matches day_of_week's own convention
    except (TypeError, ValueError):
        return True  # unparseable date filter shouldn't hide every counsel
    if any(
        s.get("kind") in ("holiday_block", "emergency_unavailable") and s.get("date") == date_str
        and _slot_overlaps_time(s, time_slot)
        for s in slots
    ):
        return False
    positive = [s for s in slots if s.get("kind") in ("recurring_weekly", "custom_date")]
    if not positive:
        return True
    return any(
        ((s["kind"] == "custom_date" and s.get("date") == date_str)
         or (s["kind"] == "recurring_weekly" and s.get("day_of_week") == weekday))
        and _slot_overlaps_time(s, time_slot)
        for s in positive
    )


def _validated_slot_fields(kind: str, day_of_week: Optional[int], date: Optional[str],
                           court_id: Optional[str], start_time: Optional[str]) -> dict:
    """The one place a slot's fields are checked and normalized, for both
    add_slot and update_slot. Only the field the kind actually uses is kept
    (day_of_week for recurring_weekly, date otherwise), so switching a slot's
    kind on edit can't leave a stale date/day behind that matching would
    still read."""
    if kind not in AVAILABILITY_KINDS:
        raise HTTPException(400, f"Invalid availability kind. Allowed: {', '.join(AVAILABILITY_KINDS)}")
    if kind == "recurring_weekly":
        if day_of_week is None or not 0 <= day_of_week <= 6:
            raise HTTPException(400, "day_of_week (0=Monday..6=Sunday) is required for a recurring weekly slot")
        date = None
    else:
        if not date:
            raise HTTPException(400, "date is required for this availability kind")
        # Matching compares this string to the browse page's YYYY-MM-DD
        # hearing date verbatim, so any other shape could never match.
        try:
            date = datetime.strptime(date, "%Y-%m-%d").date().isoformat()
        except (TypeError, ValueError):
            raise HTTPException(400, "date must be a valid date in YYYY-MM-DD format")
        if date < _today_ist():
            raise HTTPException(400, "That date has already passed. Pick today or a future date.")
        day_of_week = None
    # Founder direction (2026-09): a counsel must pick one of the time-of-day
    # labels explicitly (Court stays the one genuinely optional field) —
    # enforced here too, and restricted to the known labels, so a direct API
    # call can't save a time that matching would never recognize.
    if not start_time:
        raise HTTPException(400, "A time slot is required")
    if start_time not in AVAILABILITY_TIME_LABELS:
        raise HTTPException(400, f"Invalid time slot. Allowed: {', '.join(AVAILABILITY_TIME_LABELS)}")
    return {
        "kind": kind,
        "day_of_week": day_of_week,
        "date": date,
        "court_id": (court_id or "").strip() or None,  # null = any court
        "start_time": start_time,  # one of AVAILABILITY_TIME_LABELS
        "end_time": None,  # only legacy clock-time rows have one, see _slot_windows
    }


async def _reject_duplicate(db, user_id: str, fields: dict, exclude_slot_id: Optional[str] = None) -> None:
    query = {"user_id": user_id, **{k: fields[k] for k in ("kind", "day_of_week", "date", "court_id", "start_time")}}
    if exclude_slot_id:
        query["slot_id"] = {"$ne": exclude_slot_id}
    if await db.availability_slots.find_one(query, {"_id": 1}):
        raise HTTPException(409, "You've already added this availability")


async def _require_known_court(db, court_id: Optional[str]) -> None:
    """A slot's court must be a real courts row (Practice.jsx now picks it
    from court search). It used to be free text ("Delhi High Court"), which
    looked like it scoped the slot to a court but was never comparable to
    the court_id a client searches by."""
    if court_id and not await db.courts.find_one({"court_id": court_id}, {"_id": 1}):
        raise HTTPException(400, "Unknown court. Pick a court from the search results.")


async def _court_names(db, court_ids: List[str]) -> Dict[str, str]:
    ids = sorted({c for c in court_ids if c})
    if not ids:
        return {}
    rows = await db.courts.find({"court_id": {"$in": ids}}, {"_id": 0, "court_id": 1, "name": 1}).to_list(len(ids))
    return {r["court_id"]: r["name"] for r in rows}


def _with_status(slot: dict) -> dict:
    """Adds `is_past` (a dated slot whose date is before today, IST) so the
    Availability tab can mark it instead of listing it as current."""
    slot["is_past"] = bool(slot.get("kind") in _DATED_KINDS and slot.get("date") and slot["date"] < _today_ist())
    return slot


async def add_slot(db, user_id: str, kind: str, day_of_week: Optional[int], date: Optional[str],
                    court_id: Optional[str], start_time: Optional[str], end_time: Optional[str] = None) -> dict:
    # end_time stays in the signature for request-shape compatibility only;
    # new slots are time-of-day labels and never carry one.
    fields = _validated_slot_fields(kind, day_of_week, date, court_id, start_time)
    await _require_known_court(db, fields["court_id"])
    await _reject_duplicate(db, user_id, fields)
    slot = {
        "slot_id": f"slot_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        **fields,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.availability_slots.insert_one(slot)
    slot.pop("_id", None)
    return _with_status(slot)


async def update_slot(db, user_id: str, slot_id: str, kind: str, day_of_week: Optional[int], date: Optional[str],
                      court_id: Optional[str], start_time: Optional[str], end_time: Optional[str] = None) -> dict:
    """Edit an existing slot in place (same slot_id, same rules as add_slot).
    Scoped to user_id, so one counsel can never edit another's slot."""
    existing = await db.availability_slots.find_one({"slot_id": slot_id, "user_id": user_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Slot not found")
    fields = _validated_slot_fields(kind, day_of_week, date, court_id, start_time)
    await _require_known_court(db, fields["court_id"])
    await _reject_duplicate(db, user_id, fields, exclude_slot_id=slot_id)
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.availability_slots.update_one({"slot_id": slot_id, "user_id": user_id}, {"$set": fields})
    return _with_status({**existing, **fields})


async def list_slots(db, user_id: str) -> List[dict]:
    rows = await db.availability_slots.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    names = await _court_names(db, [r.get("court_id") for r in rows])
    for row in rows:
        # court_known False = a legacy free-text court from before the picker.
        row["court_name"] = names.get(row.get("court_id"), row.get("court_id"))
        row["court_known"] = not row.get("court_id") or row["court_id"] in names
    return [_with_status(row) for row in rows]


async def client_visibility(db, user_id: str) -> dict:
    """Why a counsel would or wouldn't appear in client search — the same
    gates counsel_matching.list_and_recommend applies, read back for this one
    counsel so My Practice can say so (Practice.jsx's ClientVisibilityCard).

    Added after a counsel saved a Wednesday, Delhi High Court, 2 PM – 5 PM
    slot, got "Availability added", and was still missing from that exact
    client search — not because of the slot, which matched, but because the
    profile was not yet approved, its Courts didn't include Delhi High Court
    (the slot's own Court field is not what search filters on), and 2 PM –
    5 PM had no price. None of that was visible anywhere on the page.

    `blocking` checks hide the counsel from every client search; `warning`
    checks only hide them from some (a court or time slot)."""
    profile = await get_or_create_profile(db, user_id)
    slots = [s for s in await list_slots(db, user_id) if not s.get("is_past")]
    checks: List[dict] = []

    def check(key: str, ok: bool, severity: str, message: str) -> None:
        checks.append({"key": key, "ok": ok, "severity": severity, "message": message})

    check("kyc_approved", profile.get("kyc_status") == "approved", "blocking",
          "Your KYC is approved" if profile.get("kyc_status") == "approved"
          else "Your KYC is still pending admin approval")
    check("bar_council_verified", profile.get("bar_council_verified") is True, "blocking",
          "Your Bar Council enrolment is verified" if profile.get("bar_council_verified") is True
          else "Your Bar Council enrolment hasn't been verified yet")

    profile_courts = profile.get("courts") or []
    known = await _court_names(db, profile_courts)
    unrecognized = [c for c in profile_courts if c not in known]
    check("courts", bool(known), "blocking",
          f"Clients searching {', '.join(known.values())} can find you" if known
          else "Add the courts you appear in under Profile → Courts, picked from search")
    if unrecognized:
        check("courts_unrecognized", False, "warning",
              f"Re-pick from search, these courts aren't recognized: {', '.join(unrecognized)}")

    slot_court_ids = sorted({s["court_id"] for s in slots if s.get("court_id") and s.get("court_known")})
    missing = [cid for cid in slot_court_ids if cid not in known]
    if missing:
        names = await _court_names(db, missing)
        check("availability_courts", False, "warning",
              f"Your availability mentions {', '.join(names.get(c, c) for c in missing)}, but it isn't in "
              "Profile → Courts, so clients searching that court won't see you")

    pricing = profile.get("pricing") or {}
    slot_keys = {_LABEL_TO_PRICING_SLOT.get(s.get("start_time")) for s in slots} - {None}
    unpriced = [k for k in PRICING_SLOTS if k in slot_keys
                and not any(k in (pricing.get(ct) or {}) for ct in PRICING_COURT_TYPES)]
    if unpriced:
        check("availability_pricing", False, "warning",
              f"No price set for {', '.join(PRICING_SLOT_LABELS[k] for k in unpriced)}, so clients filtering "
              "by that time won't see you. Add it under Profile → Pricing")

    if not profile.get("availability_mode"):
        check("availability_mode", False, "warning",
              "\"Available for hearings\" is off, so you won't be offered new hearing requests")

    return {"visible": all(c["ok"] for c in checks if c["severity"] == "blocking"), "checks": checks}


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
