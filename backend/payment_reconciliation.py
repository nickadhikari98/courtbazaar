"""Payment-transaction reconciliation — the shared claim/finalize logic
behind both the client-driven /verify routes and the Razorpay webhook safety
net in server.py. Owns the payment_transactions status/payment_status pair
(one table, one place that sets it) and the side effects finalizing or
failing a payment triggers on the underlying order/hearing.

server.py's routes stay thin HTTP wiring that delegates to this module — the
same split hearings.py/escrow.py already keep between their own domains and
server.py's route layer. Every function here takes `db` explicitly (same
convention as hearings.py/escrow.py) instead of importing a module-global
client, so this module has no import-order dependency on server.py.

Hearing notifications go through a `notify_hearing_event` callback supplied
by the caller (server.py's own `_notify_hearing_event`, which threads in
email-notification context this module has no reason to know about) rather
than being duplicated here.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

import escrow as escrow_svc
import hearings as hearings_svc
import razorpay_svc

logger = logging.getLogger(__name__)

NotifyHearingEvent = Callable[[str, str, str, str], Awaitable[None]]

PAYMENT_TX_OUTCOMES = {
    "paid": {"status": "complete", "payment_status": "paid"},
    "failed": {"status": "failed", "payment_status": "failed"},
}


async def claim_payment_transaction(db, razorpay_order_id: str, outcome: str, **extra_fields) -> Optional[dict]:
    """Single source of truth for the payment_transactions status/
    payment_status pair each terminal outcome sets — shared by
    mark_payment_failed, finalize_marketplace_payment and
    finalize_hearing_payment so a future schema change to that pair (or to
    the idempotency rule below) only has one place to change instead of
    three.

    The {"$ne": "paid"} guard is what makes every caller's claim atomic and
    correct together: it lets "paid" be reached from pending or failed (a
    retry succeeding after an earlier failed attempt on the same order) while
    guaranteeing a transaction already "paid" can never move anywhere else —
    a late/out-of-order payment.failed racing an already-successful payment
    (client /verify vs. webhook, or two webhook deliveries) is a deliberate
    no-op, not an error. Returns the pre-update row (pymongo's default
    find_one_and_update behaviour) so callers can still read the context
    fields (order_id/context_type/...) that don't change across the update,
    or None if another caller already claimed it first."""
    fields = {**PAYMENT_TX_OUTCOMES[outcome], **extra_fields}
    return await db.payment_transactions.find_one_and_update(
        {"razorpay_order_id": razorpay_order_id, "payment_status": {"$ne": "paid"}},
        {"$set": fields},
    )


async def _notify_payment_failed(db, tx: dict, notify_hearing_event: NotifyHearingEvent) -> None:
    """Best-effort notice to the payer that their payment didn't go through.
    Without this, a declined card left the payer with no explanation and no
    signal to retry — the order/hearing itself is already retryable (e.g.
    hearings.py's payment_pending self-loop, or simply calling create-order
    again), this only tells the payer that."""
    if tx.get("context_type") == "hearing":
        hearing = await db.hearing_requests.find_one({"hearing_id": tx["context_id"]}, {"_id": 0})
        if hearing:
            await notify_hearing_event(
                hearing["requesting_user_id"], "Payment failed",
                f"Your payment for the hearing at {hearing['court_id']} did not go through. Please try again.",
                hearing["hearing_id"],
            )
        return
    order_id, user_id = tx.get("order_id"), tx.get("user_id")
    if not (order_id and user_id):
        return
    try:
        from notifications import notify, record_notification_event
        title = "Payment failed"
        body = f"Your payment for order {order_id} did not go through. Please try again."
        recipient = await db.users.find_one({"user_id": user_id})
        if recipient:
            notify(recipient, "payment_failed", {"title": title, "body": body})
        await record_notification_event(db, user_id, "payment_failed", title, body, "order", order_id)
        await db.orders.update_one(
            {"order_id": order_id},
            {"$push": {"timeline": {"status": "placed", "at": datetime.now(timezone.utc).isoformat(), "note": "Payment attempt failed"}}},
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"notify error: {e}")


async def mark_payment_failed(db, rzp_order_id: str, rzp_payment_id: str, notify_hearing_event: NotifyHearingEvent) -> bool:
    """payment.failed handling. Guarded the same way as the finalize_*
    helpers, but in the opposite direction: this must NEVER move a
    transaction out of "paid" — a late/out-of-order payment.failed (e.g. an
    earlier failed attempt on the same order, delivered after a later
    successful retry) is a deliberate no-op here, not an error. Returns
    False when that no-op path is taken."""
    tx = await claim_payment_transaction(db, rzp_order_id, "failed", razorpay_payment_id=rzp_payment_id)
    if not tx:
        return False
    await _notify_payment_failed(db, tx, notify_hearing_event)
    return True


async def finalize_marketplace_payment(db, tx: dict, rzp_payment_id: str) -> bool:
    """Idempotency guard: {"$ne": "paid"} lets a payment move pending/failed
    -> paid (a retry succeeding after an earlier failed attempt on the same
    order), but a find_one_and_update that returns None means someone
    already finalized this transaction — the client's own /verify call, or
    a webhook delivery that raced it. Returns False in that case so the
    caller can skip re-running order-state side effects instead of erroring
    (the payment IS confirmed either way)."""
    updated_tx = await claim_payment_transaction(db, tx["razorpay_order_id"], "paid", razorpay_payment_id=rzp_payment_id)
    if not updated_tx:
        return False
    await db.orders.update_one(
        {"order_id": tx["order_id"]},
        {"$set": {"payment_status": "paid", "status": "matched"},
         "$push": {"timeline": {"status": "matched", "at": datetime.now(timezone.utc).isoformat(), "note": "Payment successful via Razorpay"}}},
    )
    return True


async def finalize_hearing_payment(
    db, hearing: dict, tx: dict, rzp_payment_id: str, *,
    platform_commission_pct: float, notify_hearing_event: NotifyHearingEvent,
) -> bool:
    """Same idempotency contract as finalize_marketplace_payment (see that
    docstring) — used by both verify_hearing_payment and the webhook.
    mark_payment_confirmed checks hearing["requesting_user_id"] != user
    ["user_id"]; the webhook path has no authenticated end-user, only a
    verified gateway signature, so it's satisfied here with a synthetic
    actor built straight from the hearing's own requester.

    Orphaned-capture protection: the per-order claim above only dedupes
    repeat deliveries of the SAME Razorpay order. A hearing can have several
    orders (every create-order call, incl. the payment_pending self-loop
    retry, makes a new one), and a capture can land after the hearing left
    payment_pending (cancelled/rejected while checkout was open). So before
    any escrow is created, this payment must also win an atomic per-hearing
    claim — see _claim_hearing_for_payment. A capture that loses it is
    never attached to the hearing: no escrow, no state change; it is
    refunded and recorded instead (_refund_orphaned_capture). Returns False
    for both the duplicate and the orphaned case; callers that need to tell
    them apart read payment_transactions.orphaned."""
    order_id = tx["razorpay_order_id"]
    updated_tx = await claim_payment_transaction(db, order_id, "paid", razorpay_payment_id=rzp_payment_id)
    if not updated_tx:
        return False
    hearing_id = hearing["hearing_id"]
    claimed = await _claim_hearing_for_payment(db, hearing_id, order_id)
    if not claimed:
        current = await db.hearing_requests.find_one(
            {"hearing_id": hearing_id}, {"_id": 0, "status": 1, "payment_claim_order_id": 1},
        )
        if not current:
            reason = "hearing_not_found"
        elif current.get("status") != "payment_pending":
            reason = f"hearing_not_payable:{current.get('status')}"
        else:
            reason = f"hearing_already_claimed_by:{current.get('payment_claim_order_id')}"
        await _refund_orphaned_capture(db, tx, rzp_payment_id, reason)
        return False
    # From here on use the authoritative record returned by the claim, not
    # the caller's (possibly stale) snapshot.
    hearing = claimed
    try:
        # M6 reorder: payment now happens before anyone accepts, so
        # proxy_counsel_user_id is still None here — escrow.create_and_hold's
        # deferred-payee path (M2) holds the funds unassigned; M12's
        # accept_hearing_request extension is what calls assign_payee later.
        await escrow_svc.create_and_hold(
            db, context_type="hearing", context_id=hearing_id, service_id=hearings_svc.ESCROW_SERVICE_ID,
            matter_id=hearing.get("matter_id"), payer_user_id=hearing["requesting_user_id"], payee_user_id=hearing.get("proxy_counsel_user_id"),
            amount=hearing["fee"], platform_commission_pct=platform_commission_pct,
            razorpay_order_id=order_id, razorpay_payment_id=rzp_payment_id,
        )
        synthetic_actor = {"user_id": hearing["requesting_user_id"]}
        await hearings_svc.mark_payment_confirmed(db, hearing_id, synthetic_actor)
    except Exception as e:
        # The payment is captured and this hearing is claimed by it, so it
        # must not fail silently: leave a durable marker for admins/
        # reconciliation, then re-raise so the caller still sees the error.
        now = datetime.now(timezone.utc).isoformat()
        await db.payment_transactions.update_one(
            {"razorpay_order_id": order_id},
            {"$set": {"finalize_error": str(e)[:500], "finalize_error_at": now}},
        )
        from audit_log import log_audit
        await log_audit(db, "payment.finalize_failed", None, {
            "razorpay_order_id": order_id, "razorpay_payment_id": rzp_payment_id,
            "context_type": "hearing", "context_id": hearing_id, "error": str(e)[:500],
        })
        raise
    # Targeted advocate is now notified at request-creation time (see
    # create_hearing_request in server.py) — by the time payment is verified
    # here, negotiation has already been agreed, so this is a
    # payment-confirmation notice, not the first the advocate hears of the
    # request. Broadcast-to-all requests have no single recipient to notify
    # at this point (same as before) — that's the Counsel Matching Agent's
    # job (M11, not built yet).
    if hearing.get("target_advocate_id"):
        await notify_hearing_event(hearing["target_advocate_id"], "Payment received",
                                    f"Payment for your hearing at {hearing['court_id']} is confirmed and held securely by CourtBazaar.",
                                    hearing_id)
    await notify_hearing_event(hearing["requesting_user_id"], "Payment successful",
                                f"Your payment for the hearing at {hearing['court_id']} is confirmed and held securely by CourtBazaar.",
                                hearing_id)
    return True


async def _claim_hearing_for_payment(db, hearing_id: str, razorpay_order_id: str) -> Optional[dict]:
    """Atomic per-hearing payment claim — a single find_one_and_update that
    matches only while the hearing is still payment_pending AND no other
    order has claimed it (same compare-and-swap idiom as hearings._transition).
    MongoDB applies the match and the $set as one atomic operation on the
    document, so of any number of concurrent captures for one hearing
    (verify + webhook, two tabs, two orders) exactly one gets a document
    back; every other caller gets None. hearings._transition additionally
    refuses cancel/reject out of payment_pending once this field is set, so
    a cancel can't slip in between this claim and mark_payment_confirmed.
    Returns the pre-update hearing document (authoritative, freshly read)."""
    now = datetime.now(timezone.utc).isoformat()
    return await db.hearing_requests.find_one_and_update(
        {"hearing_id": hearing_id, "status": "payment_pending", "payment_claim_order_id": None},
        {"$set": {"payment_claim_order_id": razorpay_order_id, "payment_claimed_at": now}},
        projection={"_id": 0},
    )


async def _refund_orphaned_capture(db, tx: dict, rzp_payment_id: str, reason: str) -> None:
    """A captured payment that can't be attached to its hearing: refund it
    through the existing gateway refund (simulated without keys / for
    pay_sim_ ids) and record everything needed for reconciliation on the
    payment_transactions row itself, which /admin/reconciliation reports as
    a mismatch. Callers must already hold this order's payment claim
    (claim_payment_transaction), which is what guarantees this runs — and
    refunds — at most once per Razorpay order. A refund failure is recorded
    rather than raised: the money is still captured and needs an admin, not
    a webhook retry that could no longer reach this code anyway."""
    order_id = tx["razorpay_order_id"]
    now = datetime.now(timezone.utc).isoformat()
    fields = {"orphaned": True, "orphan_reason": reason, "orphaned_at": now}
    try:
        result = razorpay_svc.refund_payment(
            rzp_payment_id, amount_inr=tx.get("amount"),
            notes={"razorpay_order_id": order_id, "context_type": tx.get("context_type"),
                   "context_id": tx.get("context_id"), "reason": f"orphaned_capture:{reason}"},
        )
        fields.update({
            "orphan_refund_status": result.get("status"),
            "orphan_refund_id": result.get("razorpay_refund_id"),
            "orphan_refund_simulated": bool(result.get("simulated")),
        })
    except Exception as e:
        logger.error(f"Refund of orphaned capture failed for {order_id}: {e}")
        fields.update({"orphan_refund_status": "failed", "orphan_refund_error": str(e)[:500]})
    await db.payment_transactions.update_one({"razorpay_order_id": order_id}, {"$set": fields})
    from audit_log import log_audit
    await log_audit(db, "payment.orphaned_capture", None, {
        "razorpay_order_id": order_id, "razorpay_payment_id": rzp_payment_id,
        "context_type": tx.get("context_type"), "context_id": tx.get("context_id"),
        "amount": tx.get("amount"), "reason": reason,
        "refund_status": fields.get("orphan_refund_status"), "refund_id": fields.get("orphan_refund_id"),
    })


async def handle_orphaned_capture(db, tx: dict, rzp_payment_id: str, reason: str) -> bool:
    """Entry point for a capture whose hearing/order can't be found at all
    (webhook path). Takes this order's payment claim first so a repeated
    webhook delivery can never refund twice; returns False if already
    handled."""
    claimed_tx = await claim_payment_transaction(db, tx["razorpay_order_id"], "paid", razorpay_payment_id=rzp_payment_id)
    if not claimed_tx:
        return False
    await _refund_orphaned_capture(db, tx, rzp_payment_id, reason)
    return True


# ---------------------------------------------------------------------------
# Bug C: Razorpay refund webhooks + orphan-refund retry
# ---------------------------------------------------------------------------

ORPHAN_REFUND_RETRYABLE = ("failed", "pending", "created")
STALE_ORPHAN_RETRY_MINUTES = 10


async def apply_refund_event(db, refund_entity: dict, event: str) -> dict:
    """refund.processed / refund.failed from the Razorpay webhook. Settles
    whichever record requested the refund — an escrow refund
    (escrow.settle_refund_from_gateway) or an orphaned-capture refund on
    payment_transactions — with compare-and-swap writes, so duplicate or
    late deliveries are no-ops. Returns a small summary for logging."""
    refund_id = refund_entity.get("id")
    payment_id = refund_entity.get("payment_id")
    status = "processed" if event == "refund.processed" else "failed"
    error = None
    if status == "failed":
        error = (refund_entity.get("error_description") or refund_entity.get("error_reason")
                 or "Razorpay reported the refund as failed")

    escrow = await escrow_svc.settle_refund_from_gateway(
        db, refund_id=refund_id, payment_id=payment_id, gateway_status=status, error=error,
    )
    if escrow:
        return {"matched": "escrow", "escrow_id": escrow["escrow_id"], "status": escrow["status"],
                "changed": bool(escrow.get("refund_settled"))}

    # Orphaned capture refunds (Bug A) — match by refund id, then payment id.
    query = {"orphaned": True, "orphan_refund_id": refund_id} if refund_id else None
    tx = await db.payment_transactions.find_one(query, {"_id": 0}) if query else None
    if not tx and payment_id:
        tx = await db.payment_transactions.find_one({"orphaned": True, "razorpay_payment_id": payment_id}, {"_id": 0})
    if not tx:
        return {"matched": None}
    now = datetime.now(timezone.utc).isoformat()
    allowed_from = ["pending", "created", "failed", "retrying"] if status == "processed" else ["pending", "created", "retrying"]
    fields = {"orphan_refund_status": status, "orphan_refund_settled_at": now}
    if refund_id:
        fields["orphan_refund_id"] = refund_id
    if status == "failed":
        fields["orphan_refund_error"] = error
    res = await db.payment_transactions.update_one(
        {"razorpay_order_id": tx["razorpay_order_id"], "orphan_refund_status": {"$in": allowed_from}},
        {"$set": fields},
    )
    return {"matched": "orphan", "razorpay_order_id": tx["razorpay_order_id"],
            "status": status if res.modified_count else tx.get("orphan_refund_status"), "changed": bool(res.modified_count)}


async def retry_orphan_refund(db, razorpay_order_id: str, actor: Optional[dict]) -> dict:
    """Admin recovery for an orphaned-capture refund that failed or is stuck
    pending. Same safety pattern as escrow.retry_refund: an atomic claim
    (orphan_refund_status -> "retrying"; a concurrent retry gets 409), then a
    lookup of refunds Razorpay already holds for the payment before any new
    request, refunding only the unrefunded remainder."""
    from fastapi import HTTPException
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    stale = (now_dt - timedelta(minutes=STALE_ORPHAN_RETRY_MINUTES)).isoformat()
    before = await db.payment_transactions.find_one_and_update(
        {"razorpay_order_id": razorpay_order_id, "orphaned": True, "$or": [
            {"orphan_refund_status": {"$in": list(ORPHAN_REFUND_RETRYABLE)}},
            {"orphan_refund_status": "retrying", "orphan_refund_retry_at": {"$lt": stale}},
        ]},
        {"$set": {"orphan_refund_status": "retrying", "orphan_refund_retry_at": now,
                  "orphan_refund_retry_by": actor["user_id"] if actor else "system"},
         "$inc": {"orphan_refund_attempts": 1}},
        projection={"_id": 0},
    )
    if not before:
        current = await db.payment_transactions.find_one({"razorpay_order_id": razorpay_order_id}, {"_id": 0})
        if not current or not current.get("orphaned"):
            raise HTTPException(404, "No orphaned payment for this order")
        if current.get("orphan_refund_status") == "processed":
            return current  # already refunded — idempotent, never a second refund
        if current.get("orphan_refund_status") == "retrying":
            raise HTTPException(409, "A refund retry is already in progress for this payment")
        raise HTTPException(400, f"Nothing to retry: refund status is '{current.get('orphan_refund_status')}'")

    payment_id = before.get("razorpay_payment_id")
    amount = float(before.get("amount") or 0)
    fields: dict = {}
    try:
        existing = razorpay_svc.fetch_refunds(payment_id) if payment_id else []
        processed = [r for r in existing if (r.get("status") or "").lower() == "processed"]
        in_flight = [r for r in existing if (r.get("status") or "").lower() in ("pending", "created")]
        remaining = round(amount - sum(float(r.get("amount_inr") or 0) for r in processed), 2)
        if payment_id and remaining <= 0.009:
            fields = {"orphan_refund_status": "processed", "orphan_refund_id": processed[-1]["razorpay_refund_id"]}
        elif in_flight:
            fields = {"orphan_refund_status": "pending", "orphan_refund_id": in_flight[-1]["razorpay_refund_id"]}
        else:
            result = razorpay_svc.refund_payment(
                payment_id, amount_inr=remaining,
                notes={"razorpay_order_id": razorpay_order_id, "reason": "orphaned_capture_retry"},
            )
            status = (result.get("status") or "").lower()
            if result.get("simulated"):
                status = "processed"
            fields = {"orphan_refund_status": status if status in ("processed", "failed") else "pending",
                      "orphan_refund_id": result.get("razorpay_refund_id")}
    except Exception as e:
        logger.error(f"Orphan refund retry failed for {razorpay_order_id}: {e}")
        fields = {"orphan_refund_status": "failed", "orphan_refund_error": str(e)[:500]}
    fields["orphan_refund_settled_at" if fields["orphan_refund_status"] == "processed" else "orphan_refund_updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.payment_transactions.update_one(
        {"razorpay_order_id": razorpay_order_id, "orphan_refund_status": "retrying"}, {"$set": fields},
    )
    from audit_log import log_audit
    await log_audit(db, "payment.orphan_refund_retry", actor, {
        "razorpay_order_id": razorpay_order_id, "razorpay_payment_id": payment_id,
        "status": fields["orphan_refund_status"], "refund_id": fields.get("orphan_refund_id"),
        "error": fields.get("orphan_refund_error"),
    })
    return {**before, **fields}
