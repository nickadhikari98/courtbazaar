"""Leads pipeline — anonymous applicant submissions from the landing page's
"Join as..." forms (Proxy Counsel, Counsel, Vendor, Partner, Agent).

Leads are intentionally isolated from the `users` collection. Approving a
lead is a manual admin status change today, not an automatic account
creation — converting an approved lead into a real user is a deliberately
deferred future phase, not built here.

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
import re
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from rate_limiter import get_limiter

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
    Each index is partial (`status: {$ne: "draft"}` + the field actually
    present) so:
      - in-progress drafts never collide with each other or with a real
        submission while someone is still filling the form out, and
      - a lead with no phone captured yet doesn't collide with every other
        phone-less lead under a null-equals-null match.

    This is the actual race-condition-proof guarantee: two concurrent
    `submit` calls for the same email+role will have exactly one succeed
    and one hit a DuplicateKeyError at the database layer, regardless of
    any earlier application-level check having raced.
    """
    await db.leads.create_index(
        [("role_applied_for", 1), ("email_normalized", 1)],
        unique=True,
        partialFilterExpression={"status": {"$ne": "draft"}, "email_normalized": {"$type": "string"}},
        name="uniq_role_email_submitted",
    )
    await db.leads.create_index(
        [("role_applied_for", 1), ("phone_normalized", 1)],
        unique=True,
        partialFilterExpression={"status": {"$ne": "draft"}, "phone_normalized": {"$type": "string"}},
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
    return {**lead, "documents": documents, "status_history": history}


async def admin_change_status(db, send_email_fn, lead_id: str, new_status: str,
                               remark: Optional[str], admin_user: dict) -> dict:
    if new_status not in LEAD_STATUSES:
        raise HTTPException(400, "Invalid status")
    lead = await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(404, "Lead not found")
    old_status = lead["status"]
    now = datetime.now(timezone.utc).isoformat()
    update: Dict[str, Any] = {"status": new_status, "updated_at": now, "reviewed_by": admin_user["user_id"]}
    if remark:
        update["admin_remarks"] = lead.get("admin_remarks", []) + [{
            "text": remark, "admin_id": admin_user["user_id"],
            "admin_name": admin_user.get("name"), "created_at": now,
        }]
    await db.leads.update_one({"lead_id": lead_id}, {"$set": update})
    await log_status_change(db, lead_id, old_status, new_status, admin_user["user_id"], remark)

    if lead.get("email") and new_status in ("approved", "rejected", "more_info_requested"):
        from notifications import tmpl_lead_approved, tmpl_lead_rejected, tmpl_lead_more_info_requested
        tmpl_fn = {
            "approved": tmpl_lead_approved,
            "rejected": tmpl_lead_rejected,
            "more_info_requested": tmpl_lead_more_info_requested,
        }[new_status]
        tmpl = tmpl_fn(lead, remark)
        send_email_fn(lead["email"], tmpl["email_subject"], tmpl["email_html"])
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
