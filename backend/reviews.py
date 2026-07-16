"""Reviews pipeline — anonymous "Write a Review" submissions from the
landing page testimonials section.

Mirrors the shape of `leads.py` (anonymous public submission -> pending
admin queue -> moderated outcome) but is deliberately simpler: a review is
a single-shot submission (name/designation/organization/rating/review text
+ optional photo) with nothing to save-as-draft or resume, so there's no
lead-style draft_token/ownership dance here — once submitted, only an
admin can change it.

Every review starts at status="pending" and is invisible to
`list_public_reviews` until an admin approves it. This is the fix for the
previous "Write a Review" modal, which was UI-only and never persisted
anything (see audit report).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import HTTPException

from rate_limiter import get_limiter

logger = logging.getLogger(__name__)

REVIEW_STATUSES = ("pending", "approved", "rejected")
REVIEW_CREATE_RATE_LIMIT = 5
REVIEW_CREATE_RATE_WINDOW_SECONDS = 3600
MAX_REVIEW_TEXT_LENGTH = 2000
MAX_NAME_LENGTH = 120


def check_review_rate_limit(client_ip: str) -> None:
    get_limiter(
        "review_create",
        limit=REVIEW_CREATE_RATE_LIMIT,
        window_seconds=REVIEW_CREATE_RATE_WINDOW_SECONDS,
        message="Too many reviews submitted from this network. Please try again later.",
    ).check(client_ip)


def _clean_str(value: Optional[str], max_len: int) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:max_len]


def _validate_review_input(name: str, rating: int, review: str) -> None:
    if not _clean_str(name, MAX_NAME_LENGTH):
        raise HTTPException(400, "Please enter your name")
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        raise HTTPException(400, "Rating must be a whole number from 1 to 5")
    if not _clean_str(review, MAX_REVIEW_TEXT_LENGTH):
        raise HTTPException(400, "Please write a review")


def new_review_id() -> str:
    return f"rev_{uuid.uuid4().hex[:12]}"


async def ensure_indexes(db) -> None:
    """Public display only ever queries status="approved" sorted by
    featured/display_order/approved_at — this index makes that a covered,
    ordered scan instead of an in-memory sort over the whole collection as
    review volume grows. Safe to call on every startup (idempotent)."""
    await db.reviews.create_index(
        [("status", 1), ("featured", -1), ("display_order", 1), ("approved_at", -1)],
        name="public_listing",
    )
    await db.reviews.create_index([("submitted_at", -1)], name="submitted_at_desc")


async def create_review(db, put_object_fn, validate_upload_fn, name: str, designation: Optional[str],
                         organization: Optional[str], rating: int, review: str,
                         photo_file: Optional[Dict[str, Any]], client_ip: Optional[str]) -> dict:
    """`photo_file`, if given, is {"filename", "content_type", "data": bytes}."""
    _validate_review_input(name, rating, review)

    review_id = new_review_id()
    photo_url_path = None
    if photo_file:
        validate_upload_fn(photo_file["filename"], photo_file["content_type"], len(photo_file["data"]))
        ext = photo_file["filename"].rsplit(".", 1)[-1].lower() if "." in (photo_file["filename"] or "") else "jpg"
        path = f"reviews/{review_id}/photo.{ext}"
        result = put_object_fn(path, photo_file["data"], photo_file["content_type"])
        photo_url_path = result["path"]

    now = datetime.now(timezone.utc)
    doc = {
        "review_id": review_id,
        "name": _clean_str(name, MAX_NAME_LENGTH),
        "designation": _clean_str(designation, MAX_NAME_LENGTH),
        "organization": _clean_str(organization, MAX_NAME_LENGTH),
        "rating": rating,
        "review": _clean_str(review, MAX_REVIEW_TEXT_LENGTH),
        "photo_path": photo_url_path,
        "status": "pending",
        "featured": False,
        "display_order": 0,
        "submitted_ip": client_ip,
        "submitted_at": now.isoformat(),
        "approved_at": None,
        "approved_by": None,
        "updated_at": now.isoformat(),
    }
    await db.reviews.insert_one(doc)

    from audit_log import log_audit
    await log_audit(db, "review.submitted", None, {"review_id": review_id, "ip": client_ip})

    try:
        from notifications import notify_admins_new_review
        notify_admins_new_review(doc)
    except Exception as e:
        logger.error(f"admin review notification failed: {e}")

    return {"review_id": review_id, "status": "pending"}


def _public_review_view(doc: dict, photo_url_fn) -> dict:
    return {
        "review_id": doc["review_id"],
        "name": doc["name"],
        "designation": doc.get("designation"),
        "organization": doc.get("organization"),
        "rating": doc["rating"],
        "review": doc["review"],
        "photo_url": photo_url_fn(doc["photo_path"]) if doc.get("photo_path") else None,
        "featured": doc.get("featured", False),
        "approved_at": doc.get("approved_at"),
    }


async def list_public_reviews(db, photo_url_fn, limit: int = 50) -> List[dict]:
    cursor = db.reviews.find({"status": "approved"}, {"_id": 0}).sort(
        [("featured", -1), ("display_order", 1), ("approved_at", -1)]
    ).limit(limit)
    docs = await cursor.to_list(limit)
    return [_public_review_view(d, photo_url_fn) for d in docs]


async def admin_list_reviews(db, status: Optional[str], q: Optional[str]) -> List[dict]:
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"organization": {"$regex": q, "$options": "i"}},
            {"review": {"$regex": q, "$options": "i"}},
        ]
    return await db.reviews.find(query, {"_id": 0}).sort("submitted_at", -1).to_list(500)


async def admin_get_review(db, review_id: str) -> dict:
    review = await db.reviews.find_one({"review_id": review_id}, {"_id": 0})
    if not review:
        raise HTTPException(404, "Review not found")
    return review


EDITABLE_FIELDS = ("name", "designation", "organization", "rating", "review", "featured", "display_order")


async def admin_update_review(db, review_id: str, patch: Dict[str, Any]) -> dict:
    review = await db.reviews.find_one({"review_id": review_id})
    if not review:
        raise HTTPException(404, "Review not found")
    update = {k: v for k, v in patch.items() if k in EDITABLE_FIELDS and v is not None}
    if "name" in update and not _clean_str(update["name"], MAX_NAME_LENGTH):
        raise HTTPException(400, "Name cannot be empty")
    if "review" in update and not _clean_str(update["review"], MAX_REVIEW_TEXT_LENGTH):
        raise HTTPException(400, "Review text cannot be empty")
    if "rating" in update and (not isinstance(update["rating"], int) or not 1 <= update["rating"] <= 5):
        raise HTTPException(400, "Rating must be a whole number from 1 to 5")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.reviews.update_one({"review_id": review_id}, {"$set": update})
    return {"ok": True}


async def admin_change_status(db, review_id: str, status: str, admin_user: dict) -> dict:
    if status not in REVIEW_STATUSES:
        raise HTTPException(400, "Invalid status")
    review = await db.reviews.find_one({"review_id": review_id})
    if not review:
        raise HTTPException(404, "Review not found")
    now = datetime.now(timezone.utc).isoformat()
    update: Dict[str, Any] = {"status": status, "updated_at": now}
    if status == "approved":
        update["approved_at"] = now
        update["approved_by"] = admin_user["user_id"]
    await db.reviews.update_one({"review_id": review_id}, {"$set": update})

    from audit_log import log_audit
    await log_audit(db, f"review.{status}" if status in ("approved", "rejected") else "review.status_change",
                     admin_user, {"review_id": review_id})
    return {"ok": True, "status": status}


async def admin_delete_review(db, review_id: str, delete_object_fn, admin_user: dict) -> dict:
    review = await db.reviews.find_one({"review_id": review_id})
    if not review:
        raise HTTPException(404, "Review not found")
    if review.get("photo_path"):
        try:
            delete_object_fn(review["photo_path"])
        except Exception as e:
            logger.error(f"review photo delete failed: {e}")
    await db.reviews.delete_one({"review_id": review_id})

    from audit_log import log_audit
    await log_audit(db, "review.deleted", admin_user, {
        "review_id": review_id, "name": review.get("name"), "status_at_deletion": review.get("status"),
    })
    return {"ok": True}


async def admin_bulk_action(db, review_ids: List[str], action: str, delete_object_fn, admin_user: dict) -> dict:
    if action in ("approve", "reject"):
        status = "approved" if action == "approve" else "rejected"
        results = [await admin_change_status(db, rid, status, admin_user) for rid in review_ids]
        return {"ok": True, "affected": len(results)}
    if action == "delete":
        for rid in review_ids:
            await admin_delete_review(db, rid, delete_object_fn, admin_user)
        return {"ok": True, "affected": len(review_ids)}
    if action in ("feature", "unfeature"):
        await db.reviews.update_many({"review_id": {"$in": review_ids}}, {"$set": {
            "featured": action == "feature", "updated_at": datetime.now(timezone.utc).isoformat(),
        }})
        return {"ok": True, "affected": len(review_ids)}
    raise HTTPException(400, "Invalid bulk action")


async def admin_reorder(db, review_ids_in_order: List[str]) -> dict:
    """Sets display_order = position in the given list — the backing call
    for an admin drag-and-drop reorder UI."""
    now = datetime.now(timezone.utc).isoformat()
    for i, review_id in enumerate(review_ids_in_order):
        await db.reviews.update_one({"review_id": review_id}, {"$set": {"display_order": i, "updated_at": now}})
    return {"ok": True}


async def review_stats(db) -> dict:
    by_status = {s: await db.reviews.count_documents({"status": s}) for s in REVIEW_STATUSES}
    return {"by_status": by_status, "featured_count": await db.reviews.count_documents({"featured": True})}
