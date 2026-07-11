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
"""
import hashlib
import logging
import time
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from fastapi import HTTPException

logger = logging.getLogger(__name__)

LEAD_ROLES = ["proxy_counsel", "counsel", "vendor", "partner", "agent"]
LEAD_STATUSES = ["draft", "submitted", "approved", "rejected", "more_info_requested"]
EDITABLE_STATUSES = ("draft", "more_info_requested")

DRAFT_EXPIRY_DAYS = 90
EMAIL_VERIFY_TOKEN_TTL_DAYS = 7

# Simple in-process sliding-window limiter for anonymous draft creation. Good
# enough for a single-worker deployment; a multi-worker/multi-instance
# deployment would need this backed by Redis instead — noted, not built,
# since this app runs single-instance today.
_draft_creation_log: Dict[str, List[float]] = {}
DRAFT_CREATE_RATE_LIMIT = 8
DRAFT_CREATE_RATE_WINDOW_SECONDS = 3600


def check_draft_rate_limit(client_ip: str) -> None:
    now = time.time()
    recent = [t for t in _draft_creation_log.get(client_ip, []) if now - t < DRAFT_CREATE_RATE_WINDOW_SECONDS]
    if len(recent) >= DRAFT_CREATE_RATE_LIMIT:
        raise HTTPException(429, "Too many applications started from this network. Please try again later.")
    recent.append(now)
    _draft_creation_log[client_ip] = recent


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
    each one's exact field keys."""
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
    return {"full_name": name, "email": email, "phone": phone}


def _required_field_count(form_data: dict) -> int:
    count = 0
    for v in (form_data or {}).values():
        if isinstance(v, str) and v.strip():
            count += 1
        elif isinstance(v, list) and v:
            count += 1
    return count


async def create_draft(db, role_applied_for: str, form_data: dict, current_step: int) -> dict:
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
    await db.leads.update_one({"lead_id": lead_id}, {"$set": update})
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
        raise HTTPException(400, "This application has already been submitted")
    if not lead.get("email"):
        raise HTTPException(400, "An email address is required before submitting")
    if _required_field_count(lead.get("form_data", {})) < 5:
        raise HTTPException(400, "Please complete the application before submitting")

    verify_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    await db.leads.update_one({"lead_id": lead_id}, {"$set": {
        "status": "submitted",
        "submitted_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "email_verify_token": verify_token,
        "email_verify_token_expires_at": (now + timedelta(days=EMAIL_VERIFY_TOKEN_TTL_DAYS)).isoformat(),
    }})
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
