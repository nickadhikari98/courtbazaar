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
    "admin.user_deactivated", "admin.user_reactivated", "admin.user_deleted",
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


async def reactivate_user(db, user_id: str, admin_user_id: str) -> dict:
    """Undo `deactivate_user`. Deliberately the mirror image, not a generic
    "restore" — it only clears the lockout flags, exactly as that function's
    docstring anticipated. It does NOT restore a password: `deactivate_user`
    wiped `password_hash`, so the account is reactivated but stays
    unusable until a fresh set-password link is issued (callers pair this
    with `leads.resend_set_password_email` rather than this function trying
    to send email itself)."""
    now = datetime.now(timezone.utc).isoformat()
    result = await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"deleted": False, "reactivated_at": now, "reactivated_by": admin_user_id},
         "$unset": {"deleted_at": "", "deactivated_by": ""}},
    )
    return {"matched": result.matched_count > 0}


# Every escrow state except the two terminal ones (released / refunded):
# anything else is money that still has to reach someone.
OPEN_ESCROW_STATUSES = ("created", "captured", "held", "refund_pending", "refund_processing", "refund_failed")
CLOSED_HEARING_STATUSES_FOR_DELETE = ("completed", "rated", "rejected", "cancelled", "expired")
CLOSED_ORDER_STATUSES_FOR_DELETE = ("completed", "cancelled")
UNPAID_SETTLEMENT_STATUSES = ("queued", "failed")
MONEY_BLOCK_REASON = "Has money held in escrow or a wallet balance"
DELETED_ACCOUNT_MESSAGE = "This account has been permanently deleted. You can sign up again to create a new account."

# The user's own public-facing profile rows, keyed by user_id. The browse
# grid, profile pages, hearing-time matching and vendor lists read these
# collections directly (never joining back to users), so they must go with
# the user or a deleted counsel/vendor would stay listed and matchable.
PROFILE_COLLECTIONS = ("proxy_counsel_profiles", "availability_slots", "vendors", "calendar_events")


def _norm_email(email: Optional[str]) -> Optional[str]:
    return email.strip().lower() if email else None


async def financial_blockers(db, target: Dict[str, Any]) -> list:
    """Why `target` (a users row) must not be permanently deleted yet —
    empty list means nothing financial or in-flight is tied to them.
    Shared by permanently_delete_users and scripts/user_deletion_dry_run.py
    so the production dry run reports exactly what the endpoint enforces."""
    user_id = target["user_id"]
    vendor_ids = [user_id] + [
        v["vendor_id"] for v in await db.vendors.find({"user_id": user_id}, {"_id": 0, "vendor_id": 1}).to_list(20)
        if v.get("vendor_id")
    ]
    reasons = []
    open_escrow = await db.escrow_transactions.count_documents({
        "$or": [{"payer_user_id": user_id}, {"payee_user_id": user_id}],
        "status": {"$in": list(OPEN_ESCROW_STATUSES)},
    })
    if open_escrow or (target.get("wallet_balance") or 0) or (target.get("wallet_held_balance") or 0):
        reasons.append(MONEY_BLOCK_REASON)
    if await db.hearing_requests.count_documents({
        "$or": [{"requesting_user_id": user_id}, {"proxy_counsel_user_id": user_id}, {"target_advocate_id": user_id}],
        "status": {"$nin": list(CLOSED_HEARING_STATUSES_FOR_DELETE)},
    }):
        reasons.append("Has an active hearing")
    if await db.orders.count_documents({
        "$or": [{"user_id": user_id}, {"vendor_id": {"$in": vendor_ids}}],
        "status": {"$nin": list(CLOSED_ORDER_STATUSES_FOR_DELETE)},
    }):
        reasons.append("Has an open order")
    if await db.settlements.count_documents({
        "payee_id": {"$in": vendor_ids}, "status": {"$in": list(UNPAID_SETTLEMENT_STATUSES)},
    }):
        reasons.append("Has an unpaid settlement payout")
    return reasons


async def is_permanently_deleted(db, *, email: Optional[str] = None, phone: Optional[str] = None) -> bool:
    """Whether an email/phone belonged to an account permanently_delete_users
    removed. Only used to tell someone signing in with an old password why
    it no longer works. It does NOT block anything: the founder's rule (Oct
    15 2026) is that a deleted person may register again with the same
    email/phone and gets a brand-new account (new user_id, normal approval)."""
    clauses = []
    if email:
        clauses.append({"email": _norm_email(email)})
    if phone:
        clauses.append({"phones": phone})
    if not clauses:
        return False
    return await db.deleted_accounts.find_one({"$or": clauses}, {"_id": 1}) is not None


async def permanently_delete_users(db, user_ids, admin_user: Dict[str, Any], request=None, delete_object_fn=None) -> dict:
    """Admin bulk delete (Admin → Users "Delete selected") — unlike
    deactivate_user and delete_user_data, this REMOVES the users row
    outright; the founder chose a real delete over soft-delete/anonymize
    for this screen (Oct 15 2026). The user's public profile rows
    (PROFILE_COLLECTIONS) and sessions go too, and their email/phone are
    recorded in deleted_accounts as a record of the deletion (it does not
    block signing up again — see is_permanently_deleted). Old tokens die
    with the users row, since every token is bound to the old user_id. Their lead application(s) are removed
    through leads.delete_lead — the same path as Admin → Leads' Delete
    button, KYC document purge included when `delete_object_fn` is given —
    so they don't stay on that screen either. Orders/hearings/escrow rows
    that point at a deleted user_id are left as they are.

    Skipped (never deleted), each with a reason: the calling admin, any
    admin account, unknown ids, and anyone financial_blockers() flags —
    an open escrow as payer or payee, a non-zero wallet balance, an active
    hearing, an open order, or an unpaid settlement payout — since deleting
    them would leave money or an in-flight job with nobody behind it.

    Every delete is audit-logged with the user's name/email/role captured
    first, because the users row those fields came from is gone after."""
    deleted, skipped = [], []
    for user_id in dict.fromkeys(user_ids):  # de-dupe, keep order
        if user_id == admin_user.get("user_id"):
            skipped.append({"user_id": user_id, "reason": "You cannot delete your own account"})
            continue
        target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
        if not target:
            skipped.append({"user_id": user_id, "reason": "User not found"})
            continue
        if target.get("role") == "admin":
            skipped.append({"user_id": user_id, "reason": "Admin accounts cannot be deleted"})
            continue
        blockers = await financial_blockers(db, target)
        if blockers:
            skipped.append({"user_id": user_id, "reason": "; ".join(blockers)})
            continue

        snapshot = {
            "target_user_id": user_id, "target_email": target.get("email"), "target_name": target.get("name"),
            "target_role": target.get("role"), "was_deactivated": bool(target.get("deleted")),
        }
        phones = [p for p in [target.get("phone"), *(target.get("alt_phones") or [])] if p]
        try:
            # Deletion record first, rolled back if the users row can't be
            # removed, so the record only ever lists accounts that are gone.
            await db.deleted_accounts.insert_one({
                "user_id": user_id, "email": _norm_email(target.get("email")), "phones": phones,
                "deleted_at": datetime.now(timezone.utc).isoformat(), "deleted_by": admin_user.get("user_id"),
            })
            try:
                await db.users.delete_one({"user_id": user_id})
            except Exception:
                await db.deleted_accounts.delete_one({"user_id": user_id})
                raise
            await db.user_sessions.delete_many({"user_id": user_id})
            removed = {}
            for coll in PROFILE_COLLECTIONS:
                removed[coll] = (await db[coll].delete_many({"user_id": user_id})).deleted_count
            snapshot["profiles_removed"] = removed
            import leads
            lead_q = [{"converted_user_id": user_id}]
            if target.get("email"):
                lead_q.append({"email_normalized": _norm_email(target.get("email"))})
            lead_ids = [l["lead_id"] for l in await db.leads.find({"$or": lead_q}, {"_id": 0, "lead_id": 1}).to_list(50)]
            snapshot["leads_removed"] = []
            for lead_id in lead_ids:
                # The user is already gone at this point — a lead that fails
                # to delete is logged, not reported as a failed user delete.
                try:
                    await leads.delete_lead(db, delete_object_fn or (lambda _path: None), lead_id, admin_user)
                    snapshot["leads_removed"].append(lead_id)
                except Exception:
                    logger.warning(f"admin.user_deleted: could not remove lead {lead_id} for {user_id}", exc_info=True)
        except Exception as e:
            logger.error(f"admin.user_deleted FAILED: admin={admin_user.get('user_id')} target={user_id} error={e}")
            await log_audit(db, "admin.user_deleted", admin_user, {**snapshot, "result": "failure", "error": str(e)}, request)
            skipped.append({"user_id": user_id, "reason": "Could not delete this user"})
            continue
        logger.info(f"admin.user_deleted: admin={admin_user.get('user_id')} target={user_id} email={target.get('email')}")
        await log_audit(db, "admin.user_deleted", admin_user, {**snapshot, "result": "success"}, request)
        deleted.append(user_id)
    return {"deleted": deleted, "skipped": skipped}


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
