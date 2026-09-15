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
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import escrow as escrow_svc
import hearings as hearings_svc

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
    actor built straight from the hearing's own requester."""
    updated_tx = await claim_payment_transaction(db, tx["razorpay_order_id"], "paid", razorpay_payment_id=rzp_payment_id)
    if not updated_tx:
        return False
    hearing_id = hearing["hearing_id"]
    # M6 reorder: payment now happens before anyone accepts, so
    # proxy_counsel_user_id is still None here — escrow.create_and_hold's
    # deferred-payee path (M2) holds the funds unassigned; M12's
    # accept_hearing_request extension is what calls assign_payee later.
    await escrow_svc.create_and_hold(
        db, context_type="hearing", context_id=hearing_id, service_id=hearings_svc.ESCROW_SERVICE_ID,
        matter_id=hearing.get("matter_id"), payer_user_id=hearing["requesting_user_id"], payee_user_id=hearing["proxy_counsel_user_id"],
        amount=hearing["fee"], platform_commission_pct=platform_commission_pct,
        razorpay_order_id=tx["razorpay_order_id"], razorpay_payment_id=rzp_payment_id,
    )
    synthetic_actor = {"user_id": hearing["requesting_user_id"]}
    await hearings_svc.mark_payment_confirmed(db, hearing_id, synthetic_actor)
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
