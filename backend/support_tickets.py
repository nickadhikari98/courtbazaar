"""Support ticket pipeline — anonymous "Raise a Support Ticket" submissions
from the public Contact Us page.

Mirrors `reviews.py`'s shape (anonymous public submission -> admin queue)
since a ticket, like a review, is a single-shot submission with nothing to
save-as-draft or resume — no lead-style draft_token/ownership dance here.

Unlike a review, a ticket isn't display content that needs approval before
going live — it's a request that needs a human response. So instead of a
pending/approved/rejected moderation lifecycle, tickets track a work-queue
lifecycle (open -> in_progress -> resolved/closed) and every admin status
change can carry a reply that's emailed straight back to the submitter, so
the person who raised it is never left wondering whether anyone saw it.
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import HTTPException

from rate_limiter import get_limiter

logger = logging.getLogger(__name__)

TICKET_STATUSES = ("open", "in_progress", "resolved", "closed")
TICKET_CATEGORIES = ("order", "payment", "account", "technical", "feature_request", "other")

TICKET_CREATE_RATE_LIMIT = 5
TICKET_CREATE_RATE_WINDOW_SECONDS = 3600

MAX_NAME_LENGTH = 120
MAX_SUBJECT_LENGTH = 200
MAX_MESSAGE_LENGTH = 4000
MAX_ORDER_ID_LENGTH = 60

_EMAIL_VALID_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def check_ticket_rate_limit(client_ip: str) -> None:
    get_limiter(
        "support_ticket_create",
        limit=TICKET_CREATE_RATE_LIMIT,
        window_seconds=TICKET_CREATE_RATE_WINDOW_SECONDS,
        message="Too many support requests submitted from this network. Please try again later.",
    ).check(client_ip)


def _clean_str(value: Optional[str], max_len: int) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:max_len]


def _validate_ticket_input(name: str, email: str, category: str, subject: str, message: str) -> None:
    if not _clean_str(name, MAX_NAME_LENGTH):
        raise HTTPException(400, "Please enter your name")
    if not email or not _EMAIL_VALID_RE.match(email.strip()):
        raise HTTPException(400, "Please provide a valid email address")
    if category not in TICKET_CATEGORIES:
        raise HTTPException(400, "Please choose a valid category")
    if not _clean_str(subject, MAX_SUBJECT_LENGTH):
        raise HTTPException(400, "Please enter a subject")
    if not _clean_str(message, MAX_MESSAGE_LENGTH):
        raise HTTPException(400, "Please describe your issue or request")


def new_ticket_id() -> str:
    return f"tkt_{uuid.uuid4().hex[:10]}".upper()


async def ensure_indexes(db) -> None:
    """Admin queue is always filtered by status and sorted newest-first —
    this index covers that without a collection scan as ticket volume grows.
    Safe to call on every startup (idempotent)."""
    await db.support_tickets.create_index([("status", 1), ("created_at", -1)], name="status_created_at")
    await db.support_tickets.create_index([("email", 1)], name="email")


async def create_ticket(db, send_email_fn, name: str, email: str, phone: Optional[str], category: str,
                         subject: str, message: str, order_id: Optional[str], client_ip: Optional[str]) -> dict:
    _validate_ticket_input(name, email, category, subject, message)

    ticket_id = new_ticket_id()
    now = datetime.now(timezone.utc)
    doc = {
        "ticket_id": ticket_id,
        "name": _clean_str(name, MAX_NAME_LENGTH),
        "email": email.strip().lower(),
        "phone": _clean_str(phone, 20),
        "category": category,
        "subject": _clean_str(subject, MAX_SUBJECT_LENGTH),
        "message": _clean_str(message, MAX_MESSAGE_LENGTH),
        "order_id": _clean_str(order_id, MAX_ORDER_ID_LENGTH),
        "status": "open",
        "replies": [],
        "submitted_ip": client_ip,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "resolved_at": None,
    }
    await db.support_tickets.insert_one(doc)

    from audit_log import log_audit
    await log_audit(db, "support_ticket.created", None, {"ticket_id": ticket_id, "category": category, "ip": client_ip})

    from notifications import tmpl_support_ticket_created, notify_admins_new_support_ticket
    tmpl = tmpl_support_ticket_created(doc)
    send_email_fn(doc["email"], tmpl["email_subject"], tmpl["email_html"])
    try:
        notify_admins_new_support_ticket(doc)
    except Exception as e:
        logger.error(f"admin support ticket notification failed: {e}")

    return {"ticket_id": ticket_id, "status": "open"}


async def list_tickets(db, status: Optional[str], category: Optional[str], q: Optional[str]) -> List[dict]:
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if category:
        query["category"] = category
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"subject": {"$regex": q, "$options": "i"}},
            {"ticket_id": {"$regex": q, "$options": "i"}},
        ]
    return await db.support_tickets.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


async def get_ticket_detail(db, ticket_id: str) -> dict:
    ticket = await db.support_tickets.find_one({"ticket_id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(404, "Support ticket not found")
    return ticket


async def admin_change_status(db, send_email_fn, ticket_id: str, status: str,
                               reply: Optional[str], admin_user: dict) -> dict:
    if status not in TICKET_STATUSES:
        raise HTTPException(400, "Invalid status")
    ticket = await db.support_tickets.find_one({"ticket_id": ticket_id})
    if not ticket:
        raise HTTPException(404, "Support ticket not found")

    now = datetime.now(timezone.utc).isoformat()
    update: Dict[str, Any] = {"status": status, "updated_at": now}
    if status in ("resolved", "closed") and not ticket.get("resolved_at"):
        update["resolved_at"] = now

    reply_text = _clean_str(reply, MAX_MESSAGE_LENGTH)
    if reply_text:
        entry = {
            "text": reply_text, "admin_id": admin_user["user_id"],
            "admin_name": admin_user.get("name"), "created_at": now,
        }
        update["replies"] = (ticket.get("replies") or []) + [entry]

    await db.support_tickets.update_one({"ticket_id": ticket_id}, {"$set": update})

    # Only actually email the submitter when there's something new to tell
    # them — a bare status flip (e.g. open -> in_progress with no message
    # yet) shouldn't generate a notification with nothing in it.
    if reply_text:
        from notifications import tmpl_support_ticket_replied
        tmpl = tmpl_support_ticket_replied({**ticket, "status": status}, reply_text)
        send_email_fn(ticket["email"], tmpl["email_subject"], tmpl["email_html"])

    from audit_log import log_audit
    await log_audit(db, "support_ticket.status_change", admin_user, {
        "ticket_id": ticket_id, "from_status": ticket["status"], "to_status": status,
    })
    return {"ok": True, "status": status}


async def delete_ticket(db, ticket_id: str, admin_user: dict) -> dict:
    ticket = await db.support_tickets.find_one({"ticket_id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(404, "Support ticket not found")
    await db.support_tickets.delete_one({"ticket_id": ticket_id})

    from audit_log import log_audit
    await log_audit(db, "support_ticket.deleted", admin_user, {
        "ticket_id": ticket_id, "subject": ticket.get("subject"), "status_at_deletion": ticket.get("status"),
    })
    return {"ok": True}


async def ticket_stats(db) -> dict:
    by_status = {s: await db.support_tickets.count_documents({"status": s}) for s in TICKET_STATUSES}
    return {"by_status": by_status}
