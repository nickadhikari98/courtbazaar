"""Leads pipeline — anonymous applicant submissions from the landing page's
"Join as..." forms (Proxy Counsel, Counsel, Vendor, Partner, Agent).

Leads are intentionally isolated from the `users` collection while still a
draft/submission. Approving a `proxy_counsel`/`counsel` lead now runs the
Lead->Professional workflow (`_activate_professional`, wired through
`workflow.StateMachine` in `admin_change_status`): it links to an existing
account (matched by normalized email) or creates a new one, seeds a
`proxy_counsel_profiles` row for proxy counsel specifically, and emails a
one-time set-password link for a brand-new account. Vendor/partner/agent
leads are unaffected — those still go through the pre-existing vendor
onboarding flow once the applicant registers/logs in themselves.

Applicants aren't logged in while filling the form, so there's no
`get_current_user` to scope a draft to. Ownership of an in-progress draft is
instead proven by a `draft_token` (a separate random secret from `lead_id`,
returned once at creation time and required on every later call) — the
lighter-weight anonymous-capability equivalent of the JWT-based auth used
everywhere else in this app. Only a hash of the token is ever stored.

Duplicate-submission prevention: one applicant may submit each role
("form") only once, identified by normalized email OR normalized phone.
Enforced at *submit* time (not draft-creation time) — a visitor is always
free to start/abandon/restart a draft (that's just local scratch space),
but converting a second draft to `submitted` for the same role+identity is
blocked. See `check_duplicate` and `ensure_indexes`.
"""
import hashlib
import logging
import os
import re
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from rate_limiter import get_limiter
from workflow import StateMachine, IllegalTransition

logger = logging.getLogger(__name__)

LEAD_ROLES = ["proxy_counsel", "counsel", "vendor", "partner", "agent"]
LEAD_STATUSES = ["draft", "submitted", "approved", "rejected", "more_info_requested"]
EDITABLE_STATUSES = ("draft", "more_info_requested")
# Statuses that count as "this form has already been submitted" for the
# purposes of duplicate detection. Rejected applications intentionally still
# block a resubmission under the same identity+role — an applicant who was
# rejected talks to the CourtBazaar team to be reinstated, they don't get a
# silent second attempt.
SUBMITTED_STATUSES = ("submitted", "approved", "rejected", "more_info_requested")

# Statuses an admin can move a lead to via admin_change_status, and the
# transition table wiring that through workflow.StateMachine. Every one of
# the 5 LEAD_STATUSES is a legal "from" state for each of these — matching
# today's actual (fully permissive) admin behavior exactly: the admin UI's
# Approve/Reject/Request-More-Info buttons are always available regardless
# of current status, so narrowing this table would be a behavior change,
# not just a refactor.
ADMIN_SETTABLE_STATUSES = ("approved", "rejected", "more_info_requested")
LEAD_ADMIN_TRANSITIONS = {
    (from_status, to_status): to_status
    for from_status in LEAD_STATUSES
    for to_status in ADMIN_SETTABLE_STATUSES
}

# leads.py's role_applied_for vocabulary isn't identical to the users
# collection's role vocabulary — "counsel" (empanelled advocate) maps onto
# the existing "advocate" role rather than inventing a redundant parallel
# role string; "proxy_counsel" is the one genuinely new role/profile type.
LEAD_ROLE_TO_ACCOUNT_ROLE = {"proxy_counsel": "proxy_counsel", "counsel": "advocate"}

DRAFT_EXPIRY_DAYS = 90
EMAIL_VERIFY_TOKEN_TTL_DAYS = 7

DRAFT_CREATE_RATE_LIMIT = 8
DRAFT_CREATE_RATE_WINDOW_SECONDS = 3600

DUPLICATE_SUBMISSION_MESSAGE = "You have already submitted this form. Our team will contact you shortly."

# Indian mobile numbers: 10 digits, first digit 6-9 (after normalization
# strips country code / punctuation). Deliberately not using the
# `phonenumbers` library to avoid a new dependency for a single-country
# product; revisit if international applicants become a real scenario.
_PHONE_DIGITS_RE = re.compile(r"\D+")
_PHONE_VALID_RE = re.compile(r"^[6-9]\d{9}$")
_EMAIL_VALID_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def check_draft_rate_limit(client_ip: str) -> None:
    get_limiter(
        "lead_draft_create",
        limit=DRAFT_CREATE_RATE_LIMIT,
        window_seconds=DRAFT_CREATE_RATE_WINDOW_SECONDS,
        message="Too many applications started from this network. Please try again later.",
    ).check(client_ip)


def normalize_email(email: Optional[str]) -> Optional[str]:
    if not email or not isinstance(email, str):
        return None
    normalized = email.strip().lower()
    return normalized or None


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """Strips all non-digit characters, then drops a leading "91" country
    code (with or without a "+") or a leading "0" trunk prefix, leaving a
    bare 10-digit number. Returns None if the result isn't a plausible
    10-digit Indian mobile number, so callers can distinguish "no phone
    given" from "phone given but unparseable" only by combining this with
    `is_valid_phone` on the raw input."""
    if not phone or not isinstance(phone, str):
        return None
    digits = _PHONE_DIGITS_RE.sub("", phone)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and _PHONE_VALID_RE.match(digits):
        return digits
    return None


def is_valid_email(email: Optional[str]) -> bool:
    return bool(email) and bool(_EMAIL_VALID_RE.match(email.strip()))


def is_valid_phone(phone: Optional[str]) -> bool:
    """True if `phone` normalizes to a plausible Indian mobile number.
    Empty/missing phone is not on its own invalid — phone is optional
    wherever the role schema doesn't mark it required — but a *non-empty*
    value that fails to normalize is rejected."""
    return normalize_phone(phone) is not None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_lead_id() -> str:
    return f"lead_{uuid.uuid4().hex[:12]}"


def new_draft_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


def _extract_contact_fields(form_data: dict) -> dict:
    """Best-effort name/email/phone extraction out of the flat fieldKey-keyed
    form_data dict (e.g. "personal_information__email_address") for admin
    search/listing — works across all 5 role schemas without needing to know
    each one's exact field keys.

    Also computes normalized email/phone alongside the raw values — these
    are what duplicate-detection and the unique indexes key off, so two
    applicants who typed "A@X.com" / "a@x.com" or "+91 98765-43210" /
    "9876543210" are recognized as the same identity."""
    name = email = phone = None
    for key, value in (form_data or {}).items():
        if not isinstance(value, str) or not value.strip():
            continue
        lk = key.lower()
        if email is None and "email" in lk:
            email = value.strip()
        elif phone is None and ("mobile" in lk or "phone" in lk):
            phone = value.strip()
        elif name is None and "full_name" in lk:
            name = value.strip()
    return {
        "full_name": name,
        "email": email,
        "phone": phone,
        "email_normalized": normalize_email(email),
        "phone_normalized": normalize_phone(phone),
    }


def _required_field_count(form_data: dict) -> int:
    count = 0
    for v in (form_data or {}).values():
        if isinstance(v, str) and v.strip():
            count += 1
        elif isinstance(v, list) and v:
            count += 1
    return count


async def ensure_indexes(db) -> None:
    """Creates the indexes duplicate-prevention and admin search rely on.
    Safe to call on every startup — Mongo no-ops recreating an identical
    index.

    The uniqueness rule ("one submission per role, per email-or-phone") is
    expressed as two *partial* unique indexes rather than one combined
    index, because Mongo unique indexes enforce "this exact key
    combination is unique", not an OR across two independent keys — so
    "same email OR same phone" needs one unique index per identity field.
    Each index is partial (`submitted_at` actually set + the identity field
    actually present) so:
      - in-progress drafts never collide with each other or with a real
        submission while someone is still filling the form out, and
      - a lead with no phone captured yet doesn't collide with every other
        phone-less lead under a null-equals-null match.

    The filter is expressed via `submitted_at: {$type: "string"}` rather
    than the more literal `status: {$ne: "draft"}` because Mongo partial
    indexes only support a small operator set in partialFilterExpression
    (equality, $exists: true, $gt/$gte/$lt/$lte, $type, top-level $and) —
    $ne is rejected outright with "Expression not supported in partial
    index: $not" at index-creation time, on every Mongo version, which
    previously made this index impossible to create at all and silently
    aborted the rest of seed_initial_data() (states/courts never got
    seeded) every time this ran against a fresh database. `submitted_at`
    is None on a draft and an ISO timestamp the instant `submit_lead` runs
    (see below), so `$type: "string"` picks out exactly the same documents
    $ne: "draft" was meant to for the normal submit flow.

    This is the actual race-condition-proof guarantee: two concurrent
    `submit` calls for the same email+role will have exactly one succeed
    and one hit a DuplicateKeyError at the database layer, regardless of
    any earlier application-level check having raced.
    """
    await db.leads.create_index(
        [("role_applied_for", 1), ("email_normalized", 1)],
        unique=True,
        partialFilterExpression={"submitted_at": {"$type": "string"}, "email_normalized": {"$type": "string"}},
        name="uniq_role_email_submitted",
    )
    await db.leads.create_index(
        [("role_applied_for", 1), ("phone_normalized", 1)],
        unique=True,
        partialFilterExpression={"submitted_at": {"$type": "string"}, "phone_normalized": {"$type": "string"}},
        name="uniq_role_phone_submitted",
    )
    # Supports admin search/listing (leads.py:list_leads) and the
    # duplicate pre-check below without a full collection scan.
    await db.leads.create_index([("status", 1), ("role_applied_for", 1)], name="status_role")
    await db.leads.create_index([("created_at", -1)], name="created_at_desc")


async def check_duplicate(db, role_applied_for: str, email_normalized: Optional[str],
                           phone_normalized: Optional[str], exclude_lead_id: Optional[str] = None) -> Optional[dict]:
    """Returns the existing submitted lead this would collide with, or None.
    This is a friendly pre-check for a clean error message — the unique
    indexes in `ensure_indexes` are what actually close the race condition,
    this call alone is not sufficient under concurrent submissions."""
    or_clauses = []
    if email_normalized:
        or_clauses.append({"email_normalized": email_normalized})
    if phone_normalized:
        or_clauses.append({"phone_normalized": phone_normalized})
    if not or_clauses:
        return None
    query: Dict[str, Any] = {
        "role_applied_for": role_applied_for,
        "status": {"$in": list(SUBMITTED_STATUSES)},
        "$or": or_clauses,
    }
    if exclude_lead_id:
        query["lead_id"] = {"$ne": exclude_lead_id}
    return await db.leads.find_one(query, {"_id": 0, "lead_id": 1})


async def create_draft(db, role_applied_for: str, form_data: dict, current_step: int,
                        client_ip: Optional[str] = None) -> dict:
    if role_applied_for not in LEAD_ROLES:
        raise HTTPException(400, "Invalid role_applied_for")
    lead_id = new_lead_id()
    draft_token = new_draft_token()
    now = datetime.now(timezone.utc)
    doc = {
        "lead_id": lead_id,
        "role_applied_for": role_applied_for,
        "status": "draft",
        "form_data": form_data or {},
        "current_step": current_step or 0,
        **_extract_contact_fields(form_data),
        "document_ids": [],
        "email_verified": False,
        "email_verify_token": None,
        "email_verify_token_expires_at": None,
        "admin_remarks": [],
        "reviewed_by": None,
        "draft_token_hash": hash_token(draft_token),
        "draft_expires_at": (now + timedelta(days=DRAFT_EXPIRY_DAYS)).isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "submitted_at": None,
    }
    await db.leads.insert_one(doc)
    from audit_log import log_audit
    await log_audit(db, "lead.created", None, {"lead_id": lead_id, "role_applied_for": role_applied_for, "ip": client_ip})
    return {"lead_id": lead_id, "draft_token": draft_token}


async def get_draft_lead(db, lead_id: str, draft_token: str) -> dict:
    """Anonymous-capability lookup. Deliberately 404s the same way whether the
    lead doesn't exist or the token is wrong, so this can't be used as an
    enumeration oracle to discover valid lead_ids."""
    lead = await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})
    if not lead or lead.get("draft_token_hash") != hash_token(draft_token):
        raise HTTPException(404, "Draft not found")
    return lead


async def update_draft(db, lead_id: str, draft_token: str, form_data: dict, current_step: Optional[int]) -> dict:
    lead = await get_draft_lead(db, lead_id, draft_token)
    if lead["status"] not in EDITABLE_STATUSES:
        raise HTTPException(400, "This application can no longer be edited")
    update = {"form_data": form_data, "updated_at": datetime.now(timezone.utc).isoformat()}
    update.update(_extract_contact_fields(form_data))
    if current_step is not None:
        update["current_step"] = current_step
    try:
        await db.leads.update_one({"lead_id": lead_id}, {"$set": update})
    except DuplicateKeyError:
        # Only reachable while this lead is in "more_info_requested" — already
        # non-draft, so already covered by the unique indexes — and the edit
        # changes email/phone to match another submitted lead for the same
        # role. Same message/status as submit_lead's identical underlying
        # condition, so duplicate-handling is consistent everywhere instead
        # of leaking a raw database error here.
        raise HTTPException(409, DUPLICATE_SUBMISSION_MESSAGE)
    return {"ok": True}


async def add_document(db, put_object_fn, validate_upload_fn, lead_id: str, draft_token: str,
                        field_key: str, filename: str, content_type: str, data: bytes) -> dict:
    lead = await get_draft_lead(db, lead_id, draft_token)
    if lead["status"] not in EDITABLE_STATUSES:
        raise HTTPException(400, "This application can no longer accept documents")
    validate_upload_fn(filename, content_type, len(data))
    doc_id = str(uuid.uuid4())
    ext = filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else "bin"
    path = f"leads/{lead_id}/{doc_id}.{ext}"
    result = put_object_fn(path, data, content_type)
    record = {
        "doc_id": doc_id,
        "lead_id": lead_id,
        "field_key": field_key,
        "original_filename": filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "storage_path": result["path"],
        "is_deleted": False,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.lead_documents.insert_one(record)
    await db.leads.update_one(
        {"lead_id": lead_id},
        {"$push": {"document_ids": doc_id}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    record.pop("_id", None)
    return record


async def remove_document(db, delete_object_fn, lead_id: str, draft_token: str, doc_id: str) -> dict:
    await get_draft_lead(db, lead_id, draft_token)
    rec = await db.lead_documents.find_one({"doc_id": doc_id, "lead_id": lead_id, "is_deleted": False})
    if not rec:
        raise HTTPException(404, "Document not found")
    delete_object_fn(rec["storage_path"])
    await db.lead_documents.update_one({"doc_id": doc_id}, {"$set": {"is_deleted": True}})
    await db.leads.update_one({"lead_id": lead_id}, {"$pull": {"document_ids": doc_id}})
    return {"ok": True}


async def log_status_change(db, lead_id: str, from_status: str, to_status: str,
                             changed_by: str, note: Optional[str]) -> None:
    await db.lead_status_history.insert_one({
        "history_id": f"lsh_{uuid.uuid4().hex[:14]}",
        "lead_id": lead_id,
        "from_status": from_status,
        "to_status": to_status,
        "changed_by": changed_by,
        "note": note,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def submit_lead(db, send_email_fn, verify_base_url: str, lead_id: str, draft_token: str) -> dict:
    lead = await get_draft_lead(db, lead_id, draft_token)
    if lead["status"] not in EDITABLE_STATUSES:
        if lead["status"] == "submitted":
            # Already fully submitted — most likely this same request racing
            # a concurrent call that already won (see the matched_count==0
            # branch below), or a stale retry. Same lead, same outcome: report
            # success rather than an error, so a double-click never surfaces
            # as a failure to the applicant.
            return {"ok": True, "lead_id": lead_id, "status": "submitted"}
        raise HTTPException(400, "This application has already been submitted")
    if not lead.get("email"):
        raise HTTPException(400, "An email address is required before submitting")
    if not is_valid_email(lead["email"]):
        raise HTTPException(400, "Please provide a valid email address")
    if lead.get("phone") and not is_valid_phone(lead["phone"]):
        raise HTTPException(400, "Please provide a valid 10-digit mobile number")
    if _required_field_count(lead.get("form_data", {})) < 5:
        raise HTTPException(400, "Please complete the application before submitting")

    email_normalized = normalize_email(lead["email"])
    phone_normalized = normalize_phone(lead.get("phone"))
    role_applied_for = lead["role_applied_for"]

    dup = await check_duplicate(db, role_applied_for, email_normalized, phone_normalized, exclude_lead_id=lead_id)
    if dup:
        from audit_log import log_audit
        await log_audit(db, "lead.duplicate_blocked", None, {
            "lead_id": lead_id, "role_applied_for": role_applied_for,
            "conflicting_lead_id": dup["lead_id"],
        })
        raise HTTPException(409, DUPLICATE_SUBMISSION_MESSAGE)

    verify_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    try:
        # The status filter here (not just on lead_id) is what makes
        # concurrent submits of the *same* lead idempotent: two racing
        # requests both pass the in-memory check above, but Mongo only lets
        # one of these conditional updates actually match+modify — whichever
        # commits first flips status away from EDITABLE_STATUSES, so the
        # other's update_one matches zero documents instead of re-applying
        # the same $set a second time.
        result = await db.leads.update_one(
            {"lead_id": lead_id, "status": {"$in": list(EDITABLE_STATUSES)}},
            {"$set": {
                "status": "submitted",
                "email_normalized": email_normalized,
                "phone_normalized": phone_normalized,
                "submitted_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "email_verify_token": verify_token,
                "email_verify_token_expires_at": (now + timedelta(days=EMAIL_VERIFY_TOKEN_TTL_DAYS)).isoformat(),
            }},
        )
    except DuplicateKeyError:
        # The pre-check above raced with a concurrent submission for the same
        # role+identity and lost — the unique index is the real guarantee,
        # this pre-check only makes the common case return a clean message.
        from audit_log import log_audit
        await log_audit(db, "lead.duplicate_blocked", None, {
            "lead_id": lead_id, "role_applied_for": role_applied_for, "race": True,
        })
        raise HTTPException(409, DUPLICATE_SUBMISSION_MESSAGE)

    if result.matched_count == 0:
        # Lost a concurrent race against another submit call for this exact
        # lead — the other request already completed the transition. Skip
        # the status-history entry, audit log, and confirmation email
        # entirely (they already happened for the winning request) and
        # report the same success the winner reports.
        return {"ok": True, "lead_id": lead_id, "status": "submitted"}

    await log_status_change(db, lead_id, lead["status"], "submitted", "system", None)

    verify_url = f"{verify_base_url}?token={verify_token}"
    from notifications import tmpl_lead_submitted
    tmpl = tmpl_lead_submitted(lead, verify_url)
    send_email_fn(lead["email"], tmpl["email_subject"], tmpl["email_html"])
    return {"ok": True, "lead_id": lead_id, "status": "submitted"}


async def verify_email(db, token: str) -> dict:
    lead = await db.leads.find_one({"email_verify_token": token})
    if not lead:
        raise HTTPException(400, "Invalid or expired verification link")
    expires_at = lead.get("email_verify_token_expires_at")
    if expires_at and datetime.now(timezone.utc) > datetime.fromisoformat(expires_at):
        raise HTTPException(400, "This verification link has expired")
    await db.leads.update_one(
        {"lead_id": lead["lead_id"]},
        {"$set": {"email_verified": True, "email_verify_token": None}},
    )
    return {"ok": True}


async def list_leads(db, status: Optional[str], role: Optional[str], q: Optional[str]) -> List[dict]:
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if role:
        query["role_applied_for"] = role
    if q:
        query["$or"] = [
            {"full_name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"phone": {"$regex": q, "$options": "i"}},
        ]
    return await db.leads.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


async def get_lead_detail(db, lead_id: str) -> dict:
    lead = await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(404, "Lead not found")
    documents = await db.lead_documents.find({"lead_id": lead_id, "is_deleted": False}, {"_id": 0}).to_list(100)
    history = await db.lead_status_history.find({"lead_id": lead_id}, {"_id": 0}).sort("created_at", 1).to_list(200)
    linked_account_deactivated = False
    if lead.get("converted_user_id"):
        linked_user = await db.users.find_one({"user_id": lead["converted_user_id"]}, {"_id": 0, "deleted": 1})
        linked_account_deactivated = bool(linked_user and linked_user.get("deleted"))
    return {**lead, "documents": documents, "status_history": history, "linked_account_deactivated": linked_account_deactivated}


# Bucketed "Total Years of Practice" radio (see frontend roleFormData.js's
# proxy_counsel/counsel "Professional Details" section) -> a
# practice.EXPERIENCE_BRACKETS key. "Less than 1 Year" and "1-3 Years" both
# collapse into "0-3" since that's the coarsest bracket the profile side
# offers. Passing experience_bracket (not a raw number) through
# practice.update_profile also derives experience_years from the bracket's
# min_years automatically, so this stays the single source of truth instead
# of a second, driftable years table.
_YEARS_OF_PRACTICE_TO_BRACKET = {
    "Less than 1 Year": "0-3",
    "1-3 Years": "0-3",
    "3-5 Years": "3-5",
    "5-7 Years": "5-7",
    "7-10 Years": "7-10",
    "More than 10 Years": "10+",
}

# "Language" radio's specify-a-second-language options (see languageOptions
# in roleFormData.js) -> the base language implied by the choice itself,
# before the free-text "__other" companion field is appended.
_LANGUAGE_OTHER_TRIGGER_BASE = {
    "Hindi & Other (Specify)": "Hindi",
    "English & Other (Specify)": "English",
}


def _derive_practice_profile_patch(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort mapping from a proxy_counsel lead's form_data (frontend
    roleFormData.js's "Bar Council Information" and "Professional Details"
    sections — bar council enrollment number, total years of practice,
    primary area of practice, language, primary court of practice, current
    professional status, max travel distance, availability schedule, matters
    handled) onto proxy_counsel_profiles fields. Called once, right after
    lead approval creates the profile row (see _activate_professional) —
    without this, everything the applicant already typed into the lead form
    just sat unused: recommendations_advocates/CounselProfileDialog read
    straight from proxy_counsel_profiles, which get_or_create_profile always
    seeds blank, so an approved counsel's marketplace-facing profile and
    their own My Practice dashboard both stayed empty until they separately
    re-typed the same information themselves.

    bio/education/office_address/fee_structure/pricing have no equivalent
    field anywhere in the lead form — intentionally left unset here (not
    invented) for the counsel to fill in themselves later via Practice.

    Field keys/value shapes here are load-bearing on roleFormData.js's exact
    section titles and labels (fieldKey() slugifies "<Section Title>__<field
    label>") — a relabel there without a matching update here silently stops
    mapping, same failure mode _extract_contact_fields above already accepts
    for contact fields."""
    patch: Dict[str, Any] = {}

    state_bar_council = form_data.get("bar_council_information__state_bar_council")
    if isinstance(state_bar_council, str) and state_bar_council.strip():
        if state_bar_council == "Other":
            other_council = form_data.get("bar_council_information__state_bar_council__other")
            state_bar_council = other_council.strip() if isinstance(other_council, str) and other_council.strip() else None
        if state_bar_council:
            patch["state_bar_council"] = state_bar_council

    bar_council_number = form_data.get("bar_council_information__bar_council_enrollment_number")
    if isinstance(bar_council_number, str) and bar_council_number.strip():
        patch["bar_council_number"] = bar_council_number.strip()

    years_bucket = form_data.get("professional_details__total_years_of_practice")
    if years_bucket in _YEARS_OF_PRACTICE_TO_BRACKET:
        patch["experience_bracket"] = _YEARS_OF_PRACTICE_TO_BRACKET[years_bucket]

    practice_areas = form_data.get("professional_details__primary_area_of_practice")
    if isinstance(practice_areas, list) and practice_areas:
        areas = [a for a in practice_areas if a != "Other"]
        other_area = form_data.get("professional_details__primary_area_of_practice__other")
        if "Other" in practice_areas and isinstance(other_area, str) and other_area.strip():
            areas.append(other_area.strip())
        if areas:
            patch["practice_areas"] = areas

    language = form_data.get("professional_details__language")
    if isinstance(language, str) and language.strip():
        if language == "Both":
            languages = ["Hindi", "English"]
        elif language in _LANGUAGE_OTHER_TRIGGER_BASE or language == "Other (Specify)":
            base = _LANGUAGE_OTHER_TRIGGER_BASE.get(language)
            other_lang = form_data.get("professional_details__language__other")
            other_lang = other_lang.strip() if isinstance(other_lang, str) and other_lang.strip() else None
            languages = [l for l in (base, other_lang) if l]
        else:
            languages = [language]
        if languages:
            patch["languages"] = languages

    courts = form_data.get("professional_details__primary_court_of_practice")
    if isinstance(courts, list) and courts:
        # Court *names* as typed on the form, not court_ids — resolved to
        # real court_ids in _activate_professional (needs a db lookup this
        # pure function doesn't have); falls back to the raw name for any
        # court that doesn't resolve, same as build_advocate_card's own
        # court_names_by_id.get(cid, cid) fallback.
        patch["courts"] = courts

    professional_status = form_data.get("professional_details__current_professional_status")
    if isinstance(professional_status, str) and professional_status.strip():
        if professional_status == "Other":
            other_status = form_data.get("professional_details__current_professional_status__other")
            professional_status = other_status.strip() if isinstance(other_status, str) and other_status.strip() else None
        if professional_status:
            patch["professional_status"] = professional_status

    max_travel_distance = form_data.get("professional_details__maximum_distance_you_are_willing_to_travel_for_appearance")
    if isinstance(max_travel_distance, str) and max_travel_distance.strip():
        patch["max_travel_distance"] = max_travel_distance

    schedule_type = form_data.get("professional_details__availability")
    if isinstance(schedule_type, str) and schedule_type.strip():
        patch["schedule_type"] = schedule_type

    matters_handled = form_data.get("professional_details__approximate_number_of_matters_handled")
    if isinstance(matters_handled, (int, float)) or (isinstance(matters_handled, str) and matters_handled.strip()):
        try:
            patch["matters_handled"] = int(matters_handled)
        except (TypeError, ValueError):
            pass

    return patch


async def _resolve_court_names_to_ids(db, court_names: List[str]) -> List[str]:
    """Best-effort court-name -> court_id resolution for
    _derive_practice_profile_patch's "courts" patch — an unresolved name is
    kept as-is rather than dropped, so it still renders as a plain-text badge
    via build_advocate_card's court_names_by_id.get(cid, cid) fallback
    instead of silently disappearing."""
    if not court_names:
        return []
    docs = await db.courts.find(
        {"name": {"$in": court_names}}, {"_id": 0, "court_id": 1, "name": 1},
    ).to_list(len(court_names))
    id_by_name = {d["name"]: d["court_id"] for d in docs}
    return [id_by_name.get(name, name) for name in court_names]


async def _activate_professional(db, lead: dict) -> None:
    """Side effect of an approved proxy_counsel/counsel lead: link to an
    existing account (matched by normalized email) or create a new one,
    then ensure a proxy_counsel_profiles row exists for proxy counsel
    specifically. This is the Lead->Professional bridge — an approved
    application now produces a usable, logged-in professional account
    instead of just a lead-status change (see module docstring).

    Approving this lead is the applicant's KYC approval — their submitted
    documents (lead.document_ids) live under this same lead record and are
    reviewed by the admin before this status change is made, there's no
    separate per-document approval step. So this also flips the profile's
    kyc_status to "approved" via practice.approve_kyc, reusing that
    function unchanged rather than setting the field here directly, so
    every kyc_status write in the app (this path, and the standalone
    admin/practice/{user_id}/approve-kyc toggle) goes through the one
    place — kyc_status then reads consistently everywhere that already
    trusts it (counsel_matching.discover_candidates's eligibility gate,
    the counsel's own /practice/profile view, etc.) without those call
    sites needing to know which path set it.

    counsel_matching.verified_counsel_query() gates on kyc_status AND
    bar_council_verified together — a single approved lead is this
    applicant's one review step for the whole application (including
    whatever bar council credential they submitted with it), so this also
    calls practice.verify_bar_council here for the same reason as above:
    without it, a newly-approved proxy counsel would still fail the
    eligibility gate and stay invisible to both hearing-time matching and
    the recommendations page despite having just been approved."""
    account_role = LEAD_ROLE_TO_ACCOUNT_ROLE.get(lead["role_applied_for"])
    if not account_role:
        return
    email_normalized = lead.get("email_normalized") or normalize_email(lead.get("email"))
    existing = await db.users.find_one({"email": email_normalized}) if email_normalized else None

    if existing:
        user_id = existing["user_id"]
        await db.users.update_one({"user_id": user_id}, {"$addToSet": {"professional_profile_types": account_role}})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        set_password_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        await db.users.insert_one({
            "user_id": user_id,
            "email": lead.get("email"),
            "name": lead.get("full_name") or "New Professional",
            "phone": lead.get("phone"),
            "role": account_role,
            "password_hash": "",  # unusable until set via the emailed token link
            "verified": True,  # already came through lead email verification
            "wallet_balance": 0.0,
            "subscription": "free",
            "professional_profile_types": [account_role],
            "set_password_token_hash": hash_token(set_password_token),
            "set_password_token_expires_at": (now + timedelta(days=EMAIL_VERIFY_TOKEN_TTL_DAYS)).isoformat(),
            "created_at": now.isoformat(),
        })
        from notifications import tmpl_set_password, send_email
        frontend_base = (os.environ.get("CORS_ORIGINS", "").split(",")[0] or "").strip() or "https://courtbazaar.com"
        set_password_url = f"{frontend_base}/auth/set-password?token={set_password_token}"
        tmpl = tmpl_set_password(lead, set_password_url)
        send_email(lead["email"], tmpl["email_subject"], tmpl["email_html"])

    if account_role == "proxy_counsel":
        import practice as practice_svc
        await practice_svc.get_or_create_profile(db, user_id)
        profile_patch = _derive_practice_profile_patch(lead.get("form_data") or {})
        if profile_patch.get("courts"):
            profile_patch["courts"] = await _resolve_court_names_to_ids(db, profile_patch["courts"])
        if profile_patch:
            await practice_svc.update_profile(db, user_id, profile_patch)
        await practice_svc.approve_kyc(db, user_id)
        await practice_svc.verify_bar_council(db, user_id)

    await db.leads.update_one({"lead_id": lead["lead_id"]}, {"$set": {"converted_user_id": user_id}})


async def admin_change_status(db, send_email_fn, lead_id: str, new_status: str,
                               remark: Optional[str], admin_user: dict) -> dict:
    if new_status not in ADMIN_SETTABLE_STATUSES:
        raise HTTPException(400, "Invalid status")
    lead = await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(404, "Lead not found")
    old_status = lead["status"]

    async def on_transition(entity: dict, from_status: str, to_status: str, actor: Optional[dict]) -> None:
        # Single hook point: applicant email (existing behavior, now
        # centralized here instead of inline) + the Lead->Professional
        # activation side effect, both driven by the same status change.
        if entity.get("email"):
            from notifications import tmpl_lead_approved, tmpl_lead_rejected, tmpl_lead_more_info_requested
            tmpl_fn = {
                "approved": tmpl_lead_approved,
                "rejected": tmpl_lead_rejected,
                "more_info_requested": tmpl_lead_more_info_requested,
            }[to_status]
            tmpl = tmpl_fn(entity, remark)
            send_email_fn(entity["email"], tmpl["email_subject"], tmpl["email_html"])
        if to_status == "approved":
            await _activate_professional(db, entity)

    sm = StateMachine(LEAD_ADMIN_TRANSITIONS, on_transition)
    try:
        await sm.apply(lead, old_status, new_status, admin_user)
    except IllegalTransition:
        raise HTTPException(400, "Invalid status")

    now = datetime.now(timezone.utc).isoformat()
    update: Dict[str, Any] = {"status": new_status, "updated_at": now, "reviewed_by": admin_user["user_id"]}
    if not lead.get("submitted_at"):
        # An admin can move a lead straight out of "draft" without the
        # applicant ever calling submit_lead (see LEAD_ADMIN_TRANSITIONS —
        # every status is a legal "from" state). Backfill submitted_at so
        # this lead is still covered by ensure_indexes's uniqueness check,
        # which keys off submitted_at rather than status (see ensure_indexes).
        update["submitted_at"] = now
    if remark:
        update["admin_remarks"] = lead.get("admin_remarks", []) + [{
            "text": remark, "admin_id": admin_user["user_id"],
            "admin_name": admin_user.get("name"), "created_at": now,
        }]
    await db.leads.update_one({"lead_id": lead_id}, {"$set": update})
    await log_status_change(db, lead_id, old_status, new_status, admin_user["user_id"], remark)
    return {"ok": True, "status": new_status}


async def add_note(db, lead_id: str, note: str, admin_user: dict) -> dict:
    lead = await db.leads.find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(404, "Lead not found")
    entry = {
        "text": note, "admin_id": admin_user["user_id"],
        "admin_name": admin_user.get("name"), "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.leads.update_one(
        {"lead_id": lead_id},
        {"$push": {"admin_remarks": entry}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True}


async def resend_set_password_email(db, send_email_fn, lead_id: str) -> dict:
    """Manual recovery for the one welcome email `_activate_professional`
    sends exactly once on account creation: `send_email` is fail-soft (see
    notifications.py) so a provider-side rejection (unverified sender,
    quota, transient network error) is only ever logged server-side —
    neither the admin nor the applicant ever finds out the account exists
    but is unreachable. Re-issues a fresh token (the original may have
    expired) and surfaces a real failure to the admin this time instead of
    swallowing it, so a repeat failure is at least visible."""
    lead = await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(404, "Lead not found")
    user_id = lead.get("converted_user_id")
    if not user_id:
        raise HTTPException(400, "This application hasn't been converted to an account yet.")
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(404, "Linked account not found.")
    if user.get("deleted"):
        # Deliberately not auto-reactivated here: reactivation is an admin
        # decision distinct from "resend an email" (see audit_log.deactivate_user)
        # and must go through its own explicit action/audit entry, not happen
        # as a side effect of this call.
        raise HTTPException(409, "This account has been deactivated. Reactivate it first, then resend the set-password email.")

    set_password_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "set_password_token_hash": hash_token(set_password_token),
            "set_password_token_expires_at": (now + timedelta(days=EMAIL_VERIFY_TOKEN_TTL_DAYS)).isoformat(),
        }},
    )
    frontend_base = (os.environ.get("CORS_ORIGINS", "").split(",")[0] or "").strip() or "https://courtbazaar.com"
    set_password_url = f"{frontend_base}/auth/set-password?token={set_password_token}"
    from notifications import tmpl_set_password
    tmpl = tmpl_set_password(lead, set_password_url)
    result = send_email_fn(user["email"], tmpl["email_subject"], tmpl["email_html"])
    if result.get("status") == "failed":
        raise HTTPException(502, f"Email provider rejected the send: {result.get('error', 'unknown error')}")
    if result.get("status") == "mocked":
        raise HTTPException(400, "Email sending isn't configured on this server (EMAIL_PROVIDER/BREVO_API_KEY/EMAIL_FROM_ADDRESS) — the link was only logged to the server console, not delivered.")
    return {"ok": True, "email": user["email"]}


async def _find_linked_registered_user(db, lead: dict) -> Optional[dict]:
    """A lead's applicant may already be a *registered* CourtBazaar user —
    either because this exact lead was approved and bridged into an account
    (`converted_user_id`, set by `_activate_professional`), or because they
    separately self-registered under the same email (e.g. a vendor who
    signed up directly via /auth/register + /vendors/onboard, independent of
    the lead pipeline — see module docstring). Matching by normalized email
    mirrors the exact lookup `_activate_professional` itself uses, so this
    isn't a new linking rule. Returns None (not a match) for an account
    that's already deactivated — nothing left to deactivate there."""
    converted_user_id = lead.get("converted_user_id")
    if converted_user_id:
        user = await db.users.find_one(
            {"user_id": converted_user_id, "deleted": {"$ne": True}}, {"_id": 0, "password_hash": 0}
        )
        if user:
            return user
    email_normalized = lead.get("email_normalized")
    if email_normalized:
        return await db.users.find_one(
            {"email": email_normalized, "deleted": {"$ne": True}}, {"_id": 0, "password_hash": 0}
        )
    return None


async def delete_lead(db, delete_object_fn, lead_id: str, admin_user: dict) -> dict:
    """Admin "Delete" action on a lead request — behavior branches on whether
    the applicant already has a live registered account:

    - Not yet registered (no matching account, or the lead was never
      approved into one): a plain application with no account tied to it,
      so this hard-deletes the lead row, its uploaded KYC documents (DB row
      + underlying storage object), and its status history outright.
    - Already registered (see `_find_linked_registered_user`): the "lead" is
      really just the paper trail behind a real account now. Hard-deleting
      that account would destroy order/payment/audit history it's linked
      to, so this soft-deletes (deactivates) the account instead — see
      `audit_log.deactivate_user` — and leaves the lead row itself alone,
      preserving that history. The caller (admin_leads_delete) still removes
      it from the admin's on-screen list either way.
    """
    lead = await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(404, "Lead not found")

    from audit_log import log_audit

    linked_user = await _find_linked_registered_user(db, lead)
    if linked_user:
        from audit_log import deactivate_user
        try:
            await deactivate_user(db, linked_user["user_id"], admin_user["user_id"])
        except Exception as e:
            logger.error(f"lead.delete -> user.deactivated FAILED: lead_id={lead_id} user_id={linked_user['user_id']} error={e}")
            await log_audit(db, "admin.user_deactivated", admin_user, {
                "target_user_id": linked_user["user_id"], "target_email": linked_user.get("email"),
                "lead_id": lead_id, "trigger": "lead_delete_button", "result": "failure", "error": str(e),
            })
            raise HTTPException(500, "Could not deactivate the linked user account")
        logger.info(f"lead.delete -> user.deactivated: lead_id={lead_id} user_id={linked_user['user_id']} email={linked_user.get('email')}")
        await log_audit(db, "admin.user_deactivated", admin_user, {
            "target_user_id": linked_user["user_id"], "target_email": linked_user.get("email"),
            "lead_id": lead_id, "role_applied_for": lead.get("role_applied_for"),
            "trigger": "lead_delete_button", "result": "success",
        })
        return {"ok": True, "action": "deactivated", "user_id": linked_user["user_id"]}

    docs = await db.lead_documents.find({"lead_id": lead_id}, {"_id": 0}).to_list(200)
    for doc in docs:
        if not doc.get("is_deleted"):
            try:
                delete_object_fn(doc["storage_path"])
            except Exception:
                logger.warning(f"lead.delete: failed to purge storage object for doc_id={doc['doc_id']}", exc_info=True)
    await db.lead_documents.delete_many({"lead_id": lead_id})
    await db.lead_status_history.delete_many({"lead_id": lead_id})
    await db.leads.delete_one({"lead_id": lead_id})

    await log_audit(db, "lead.deleted", admin_user, {
        "lead_id": lead_id, "role_applied_for": lead.get("role_applied_for"),
        "status_at_deletion": lead.get("status"), "email": lead.get("email"),
    })
    return {"ok": True, "action": "deleted"}


async def lead_stats(db) -> dict:
    by_status = {s: await db.leads.count_documents({"status": s}) for s in LEAD_STATUSES}
    by_role = {r: await db.leads.count_documents({"role_applied_for": r}) for r in LEAD_ROLES}
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    pipeline = [
        {"$match": {"submitted_at": {"$ne": None, "$gte": since}}},
        {"$group": {"_id": {"$substrCP": ["$submitted_at", 0, 10]}, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    trend = [{"date": d["_id"], "count": d["count"]} async for d in db.leads.aggregate(pipeline)]
    return {"by_status": by_status, "by_role": by_role, "trend_30d": trend}
