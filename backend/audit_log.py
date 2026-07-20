"""Audit log + DPDP Act compliance helpers.
Logs critical user/admin actions for traceability and produces user data exports."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Any, Dict

logger = logging.getLogger(__name__)

CRITICAL_ACTIONS = {
    "auth.login", "auth.logout", "auth.register", "auth.profile_update", "auth.password_change",
    "auth.google_login", "auth.otp_verify",
    "order.create", "order.status_change", "order.cancel", "order.rate",
    "payment.checkout_create", "payment.success", "payment.failure", "payment.refund",
    "vendor.onboard", "vendor.approve", "vendor.reject", "vendor.sponsored_activate",
    "firm.create", "firm.invite", "firm.invite_accept", "firm.member_remove",
    "admin.pricing_update", "admin.user_role_change", "admin.template_approve",
    "delivery.accept", "delivery.complete",
    "dpdp.data_export", "dpdp.data_deletion_request", "dpdp.data_deletion_executed",
    "file.upload", "file.delete",
    "lead.created", "lead.duplicate_blocked", "lead.deleted",
    "admin.user_deactivated",
    "review.submitted", "review.approved", "review.rejected", "review.deleted",
}


async def log_audit(db, action: str, user: Optional[Dict[str, Any]] = None, details: Optional[Dict] = None, request=None):
    """Persist an audit log entry."""
    try:
        entry = {
            "audit_id": f"aud_{uuid.uuid4().hex[:14]}",
            "action": action,
            "user_id": user.get("user_id") if user else None,
            "user_email": user.get("email") if user else None,
            "user_role": user.get("role") if user else None,
            "ip_address": request.client.host if request and request.client else None,
            "user_agent": request.headers.get("user-agent", "")[:200] if request else None,
            "details": details or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.audit_log.insert_one(entry)
    except Exception as e:
        logger.error(f"audit log failed: {e}")


async def export_user_data(db, user_id: str) -> dict:
    """DPDP Act: export all PII + activity for a user."""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        return {}
    orders = await db.orders.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
    files = await db.files.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
    wallet_txns = await db.wallet_transactions.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
    ai_messages = await db.ai_messages.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
    payment_txns = await db.payment_transactions.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
    audit_entries = await db.audit_log.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    vendor = await db.vendors.find_one({"user_id": user_id}, {"_id": 0})
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "profile": user,
        "vendor_profile": vendor,
        "orders": orders,
        "files": files,
        "wallet_transactions": wallet_txns,
        "payment_transactions": payment_txns,
        "ai_messages": ai_messages,
        "audit_log": audit_entries,
    }


async def deactivate_user(db, user_id: str, admin_user_id: str) -> dict:
    """Admin-initiated soft delete of a *registered* account (e.g. an admin
    removing a vendor/counsel/proxy-counsel/partner/agent who no longer
    wants to be associated with CourtBazaar) — deliberately distinct from
    delete_user_data (the DPDP self-service erasure request) above:
    delete_user_data anonymizes PII because that's what a legal erasure
    request means; this only revokes access and leaves name/email/phone
    intact so orders/audit logs/admin views stay attributable, per
    "preserve historical data" in the deactivation UX.

    Reuses the exact `deleted`/`deleted_at` flags get_current_user already
    rejects on every authenticated request (see server.py), so a
    deactivated account is locked out everywhere instantly — no separate
    auth-guard change was needed. password_hash is cleared too, as
    defense-in-depth against a login path that ever forgets the `deleted`
    check. Nothing here is destructive: a future "Restore User" feature
    only needs to clear `deleted` and let the user (or an admin) set a new
    password."""
    now = datetime.now(timezone.utc).isoformat()
    result = await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"deleted": True, "deleted_at": now, "password_hash": "", "deactivated_by": admin_user_id}},
    )
    await db.user_sessions.delete_many({"user_id": user_id})
    return {"matched": result.matched_count > 0}


async def delete_user_data(db, user_id: str) -> dict:
    """DPDP Act: anonymize a user's data (don't hard-delete to preserve order/financial records integrity)."""
    anon = f"deleted_user_{uuid.uuid4().hex[:8]}"
    await db.users.update_one({"user_id": user_id}, {"$set": {
        "name": "[deleted]", "email": f"{anon}@deleted.local", "phone": None,
        "bar_council_id": None, "chamber_address": None, "gst_number": None,
        "avatar_url": None, "password_hash": "", "deleted": True, "deleted_at": datetime.now(timezone.utc).isoformat(),
    }})
    # Anonymise file references but keep storage_path so vendor can still process active orders
    await db.files.update_many({"user_id": user_id}, {"$set": {"original_filename": "[deleted]"}})
    await db.user_sessions.delete_many({"user_id": user_id})
    counts = {
        "orders_retained": await db.orders.count_documents({"user_id": user_id}),
        "files_anonymised": await db.files.count_documents({"user_id": user_id}),
    }
    return {"status": "anonymized", "anon_id": anon, **counts}
