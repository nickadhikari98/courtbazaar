"""Escrow — the one payment-holding mechanism any service on the platform can
use (hearings today, anything else later). Owns *all* money state and math
(commission %, hold/release amounts) so call sites like hearings.py never
compute or store payout math themselves — hearings.py owns operational
workflow only, this module owns payment state, and neither reaches into the
other's transition table.

Payment lifecycle (independent of any service's own operational status):
    created -> captured -> held -> released
                            held -> refund_pending -> refunded | refund_processing | refund_failed
                            refund_failed / refund_processing -> (retry_refund) -> refund_pending

`create_and_hold` auto-chains created->captured->held in one call — there's
no separate gateway-capture webhook to key off in this simulated-escrow pass
(same auto-chain precedent as hearings.create_hearing_request's existing
requested->broadcast chain). A future real gateway-level hold (Razorpay Route
or equivalent) only changes this module's internals — razorpay_svc.py, the
call sites in server.py, and the frontend payment UI would all stay exactly
as they are, since none of them see payment *state* today, only "pay"/
"released" as business events.

`payee_user_id` on create_and_hold is optional (Counsel Matching Agent):
funds can be held before a payee is known — payment is confirmed, then
matching picks a counsel. assign_payee() attaches the payee once one accepts
and performs the wallet_held_balance credit that create_and_hold would
otherwise have done immediately. release() refuses to run until a payee has
been assigned — see release()'s docstring for why.

refund() calls the real gateway (razorpay_svc.refund_payment) when the
escrow isn't a simulated payment, via the "held" -> "refund_pending" ->
"refunded" claim sequence documented on refund() itself — the intermediate
state is what makes a double-invocation (e.g. an admin double-click) safe.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException
from pymongo import ReturnDocument

import razorpay_svc
from workflow import StateMachine, IllegalTransition

ESCROW_TRANSITIONS = {
    ("created", "capture"): "captured",
    ("captured", "hold"): "held",
    ("held", "release"): "released",
    ("held", "refund"): "refund_pending",
    ("refund_pending", "refund_confirm"): "refunded",
    ("refund_pending", "refund_release"): "held",
    # Refund recovery (Bug B): a refund Razorpay accepted but hasn't
    # processed yet, and a refund that failed — both retryable via
    # retry_refund(), which re-enters refund_pending.
    ("refund_pending", "refund_processing"): "refund_processing",
    ("refund_pending", "refund_fail"): "refund_failed",
    ("refund_failed", "refund_retry"): "refund_pending",
    ("refund_processing", "refund_retry"): "refund_pending",
    ("refund_pending", "refund_retry"): "refund_pending",  # stale in-flight claim only (see retry_refund)
    # Bug C: Razorpay's refund.processed / refund.failed webhook settles a
    # refund asynchronously (see settle_refund_from_gateway).
    ("refund_processing", "refund_confirm"): "refunded",
    ("refund_failed", "refund_confirm"): "refunded",
    ("refund_processing", "refund_fail"): "refund_failed",
}

# Statuses an admin needs to look at: refund failed, accepted-but-not-
# processed, or an in-flight claim that never finished (process crash).
REFUND_ATTENTION_STATUSES = ("refund_failed", "refund_processing", "refund_pending")
STALE_REFUND_PENDING_MINUTES = 10


def new_escrow_id() -> str:
    return f"escrow_{uuid.uuid4().hex[:12]}"


async def ensure_indexes(db) -> None:
    await db.escrow_transactions.create_index([("context_type", 1), ("context_id", 1)], name="context")
    await db.escrow_transactions.create_index([("status", 1), ("created_at", -1)], name="status_created")
    await db.escrow_transactions.create_index([("payee_user_id", 1)], name="payee")


def _make_timeline_hook(db, escrow_id: str):
    async def hook(entity: dict, from_status: str, to_status: str, actor: Optional[dict]) -> None:
        await db.escrow_transactions.update_one(
            {"escrow_id": escrow_id},
            {"$push": {"timeline": {
                "status": to_status, "at": datetime.now(timezone.utc).isoformat(),
                "note": f"{from_status} -> {to_status}", "by": actor["user_id"] if actor else "system",
            }}},
        )
    return hook


async def create_and_hold(
    db, *, context_type: str, context_id: str, service_id: Optional[str], matter_id: Optional[str],
    payer_user_id: str, payee_user_id: Optional[str] = None, amount: float, platform_commission_pct: float,
    razorpay_order_id: Optional[str], razorpay_payment_id: Optional[str],
) -> dict:
    """Records the customer's payment as platform-held, not payable to
    `payee_user_id` yet — `wallet_balance` is untouched here; only
    `wallet_held_balance` moves, so the amount is visible somewhere without
    being withdrawable (see release() for when it actually becomes theirs).

    `payee_user_id` may be omitted when no payee has been chosen yet (see
    module docstring) — the wallet_held_balance credit is deferred to
    assign_payee() in that case instead of happening here."""
    now = datetime.now(timezone.utc)
    payee_amount = round(amount * (1 - platform_commission_pct), 2)
    doc = {
        "escrow_id": new_escrow_id(),
        "context_type": context_type,
        "context_id": context_id,
        "service_id": service_id,
        "matter_id": matter_id,
        "payer_user_id": payer_user_id,
        "payee_user_id": payee_user_id,
        "amount": amount,
        "platform_commission_pct": platform_commission_pct,
        "payee_amount": payee_amount,
        "status": "created",
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "timeline": [{"status": "created", "at": now.isoformat(), "note": "Payment captured"}],
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    await db.escrow_transactions.insert_one(doc)

    sm = StateMachine(ESCROW_TRANSITIONS, _make_timeline_hook(db, doc["escrow_id"]))
    await sm.apply(doc, "created", "capture", None)
    await sm.apply(doc, "captured", "hold", None)
    await db.escrow_transactions.update_one(
        {"escrow_id": doc["escrow_id"]},
        {"$set": {"status": "held", "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if payee_user_id:
        await db.users.update_one({"user_id": payee_user_id}, {"$inc": {"wallet_held_balance": payee_amount}})

    doc["status"] = "held"
    doc.pop("_id", None)
    return doc


async def assign_payee(db, *, context_type: str, context_id: str, payee_user_id: str) -> dict:
    """Deferred-payee path (see module docstring): attaches a payee to an
    escrow hold created with payee_user_id=None, then performs the
    wallet_held_balance credit create_and_hold would have done immediately
    had the payee been known at hold time. Race-safe — same conditional
    find_one_and_update idiom as hearings.accept_hearing_request — and
    idempotent against a retried call for the same payee."""
    now = datetime.now(timezone.utc).isoformat()
    updated = await db.escrow_transactions.find_one_and_update(
        {"context_type": context_type, "context_id": context_id, "status": "held", "payee_user_id": None},
        {"$set": {"payee_user_id": payee_user_id, "updated_at": now}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if updated:
        await db.users.update_one({"user_id": payee_user_id}, {"$inc": {"wallet_held_balance": updated["payee_amount"]}})
        return updated

    escrow = await db.escrow_transactions.find_one({"context_type": context_type, "context_id": context_id}, {"_id": 0})
    if not escrow:
        raise HTTPException(404, "No escrow record for this context")
    if escrow.get("payee_user_id") == payee_user_id:
        return escrow  # already assigned to this exact payee — idempotent no-op
    if escrow.get("payee_user_id"):
        raise HTTPException(409, "Escrow already has a different payee assigned")
    raise HTTPException(400, f"Cannot assign payee from status '{escrow['status']}'")


async def release(db, *, context_type: str, context_id: str, released_by_user_id: str) -> dict:
    """held -> released: credits the payee's withdrawable wallet_balance and
    lifetime_earnings, moves the amount off wallet_held_balance, and writes a
    wallet_transactions row the existing Withdrawal flow already understands
    (settlements.py's /earnings/withdraw reads wallet_balance, unchanged).

    Refuses to run until a payee has been assigned (see assign_payee) —
    without this guard, an escrow held with payee_user_id=None could be
    "released" while crediting nobody, silently losing track of the money.

    The "held" -> "released" step is claimed atomically (same idiom as
    refund()/assign_payee(), not just StateMachine's in-memory check): two
    near-simultaneous release() calls for the same context could otherwise
    both read status "held", both pass validation, and both credit the
    payee's wallet — double-paying them and driving wallet_held_balance
    negative. Claiming "released" first means only one caller ever proceeds
    to the wallet mutation; the other gets an idempotent response instead."""
    escrow = await db.escrow_transactions.find_one({"context_type": context_type, "context_id": context_id})
    if not escrow:
        raise HTTPException(404, "No escrow record for this context")
    if not escrow.get("payee_user_id"):
        raise HTTPException(400, "Cannot release escrow with no payee assigned — call assign_payee first")

    now = datetime.now(timezone.utc).isoformat()
    claimed = await db.escrow_transactions.find_one_and_update(
        {"escrow_id": escrow["escrow_id"], "status": "held", "payee_user_id": {"$ne": None}},
        {"$set": {"status": "released", "updated_at": now}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        current = await db.escrow_transactions.find_one({"escrow_id": escrow["escrow_id"]}, {"_id": 0})
        if current and current["status"] == "released":
            return current  # already released — idempotent success, not an error
        if current and not current.get("payee_user_id"):
            raise HTTPException(400, "Cannot release escrow with no payee assigned — call assign_payee first")
        raise HTTPException(400, f"Cannot release from status '{current['status'] if current else escrow['status']}'")

    sm = StateMachine(ESCROW_TRANSITIONS, _make_timeline_hook(db, claimed["escrow_id"]))
    await sm.apply(claimed, "held", "release", {"user_id": released_by_user_id})

    escrow = claimed
    payee_id = escrow["payee_user_id"]
    payee_amount = escrow["payee_amount"]
    await db.users.update_one(
        {"user_id": payee_id},
        {"$inc": {"wallet_balance": payee_amount, "wallet_lifetime_earnings": payee_amount, "wallet_held_balance": -payee_amount}},
    )
    # `settlement_state` is forward-compat schema only (Part 5 of the
    # refinement) — stamped "withdrawable" immediately so today's
    # instant-withdraw behavior is unchanged; a future settlement-delay job
    # would flip new rows to "released" first and age them to "withdrawable".
    await db.wallet_transactions.insert_one({
        "user_id": payee_id, "amount": payee_amount, "type": "credit",
        "description": f"Escrow release ({context_type} {context_id})",
        "context_type": f"{context_type}_payout", "related_entity_id": context_id,
        "matter_id": escrow.get("matter_id"),
        "settlement_state": "withdrawable",
        "created_at": now,
    })
    return escrow


async def refund(db, *, context_type: str, context_id: str, reason: str) -> dict:
    """held -> refund_pending -> refunded: calls the real gateway refund
    (razorpay_svc.refund_payment) before any ledger state says "refunded",
    so a failed gateway call never leaves the ledger claiming money moved
    that Razorpay never released.

    The "held" -> "refund_pending" step is an atomic conditional write (same
    idiom as assign_payee), not just the StateMachine's in-memory check —
    StateMachine.apply() only validates a transition and never touches the
    database, so without this claim two concurrent refund() calls could both
    read status "held", both pass validation, and both call the gateway.
    Claiming "refund_pending" first means only one caller ever proceeds to
    the gateway; the other gets an idempotent response instead.

    Outcome (Bug B — refund failure recovery): the gateway's answer decides
    the resting status, never the mere fact that a request was sent —
      refunded           Razorpay reports "processed" (or simulated payment)
      refund_processing  Razorpay accepted it but reports it still pending
      refund_failed      the call errored/timed out, or Razorpay said failed
    A failure is recorded (refund_last_error/refund_failed_at) and the
    escrow is RETURNED, not raised: the caller's own action (cancel,
    dispute resolution) has already committed, so it should report the
    refund status rather than 500. refund_failed/refund_processing are
    retried with retry_refund().

    Skips the gateway call for a simulated payment (no razorpay_payment_id,
    or one starting with pay_sim_) — see razorpay_svc.refund_payment.
    Skips the wallet reversal entirely if no payee was ever assigned
    (nothing to reverse; see assign_payee/module docstring for the
    deferred-payee case)."""
    escrow = await db.escrow_transactions.find_one({"context_type": context_type, "context_id": context_id})
    if not escrow:
        raise HTTPException(404, "No escrow record for this context")

    now = datetime.now(timezone.utc).isoformat()
    refund_pending_state = ESCROW_TRANSITIONS[("held", "refund")]
    claimed = await db.escrow_transactions.find_one_and_update(
        {"escrow_id": escrow["escrow_id"], "status": "held"},
        {"$set": {"status": refund_pending_state, "updated_at": now, "refund_requested_at": now, "refund_reason": reason},
         "$inc": {"refund_attempts": 1}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        current = await db.escrow_transactions.find_one({"escrow_id": escrow["escrow_id"]}, {"_id": 0})
        if current and current["status"] in ("refunded", "refund_processing", "refund_failed"):
            # Already requested: refunded is idempotent success; the other
            # two are already recorded and retried via retry_refund(), never
            # by requesting a second refund here.
            return current
        if current and current["status"] == "refund_pending":
            raise HTTPException(409, "Refund already in progress for this escrow")
        raise HTTPException(400, f"Cannot refund from status '{escrow['status']}'")

    # The atomic claim above already performed the "held" -> refund_pending_state
    # write; run the same audit hook sm.apply() would have run for it so this
    # step still lands in the timeline like every other transition does.
    await _make_timeline_hook(db, claimed["escrow_id"])(claimed, "held", refund_pending_state, None)
    return await _settle_refund_attempt(db, claimed, reason=reason, check_existing=False, actor=None)


async def retry_refund(db, escrow_id: str, actor: Optional[dict]) -> dict:
    """Admin recovery for a refund that didn't complete: refund_failed,
    refund_processing, or a refund_pending claim older than
    STALE_REFUND_PENDING_MINUTES (the process died mid-call).

    Safe to call repeatedly/concurrently: the retry is claimed with the same
    atomic compare-and-swap as refund() (only one caller gets the escrow
    back into refund_pending; others get 409 or the idempotent result), and
    before any new gateway request it asks Razorpay which refunds already
    exist for the payment (razorpay_svc.fetch_refunds) — a refund that
    already went through (e.g. the first call timed out after Razorpay
    created it) is recorded, not requested again, and only the unrefunded
    remainder is ever requested. Razorpay itself also rejects refunding more
    than was captured, as a final backstop."""
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    stale_cutoff = (now_dt - timedelta(minutes=STALE_REFUND_PENDING_MINUTES)).isoformat()
    before = await db.escrow_transactions.find_one_and_update(
        {"escrow_id": escrow_id, "$or": [
            {"status": {"$in": ["refund_failed", "refund_processing"]}},
            {"status": "refund_pending", "updated_at": {"$lt": stale_cutoff}},
        ]},
        {"$set": {"status": "refund_pending", "updated_at": now, "refund_last_retry_at": now,
                  "refund_last_retry_by": actor["user_id"] if actor else "system"},
         "$inc": {"refund_attempts": 1}},
        projection={"_id": 0}, return_document=ReturnDocument.BEFORE,
    )
    if not before:
        current = await db.escrow_transactions.find_one({"escrow_id": escrow_id}, {"_id": 0})
        if not current:
            raise HTTPException(404, "Escrow not found")
        if current["status"] == "refunded":
            return current  # already refunded — idempotent, never a second refund
        if current["status"] == "refund_pending":
            raise HTTPException(409, "Refund already in progress for this escrow")
        raise HTTPException(400, f"Nothing to retry: escrow status is '{current['status']}'")

    claimed = {**before, "status": "refund_pending", "updated_at": now,
               "refund_attempts": (before.get("refund_attempts") or 0) + 1}
    await _make_timeline_hook(db, escrow_id)(claimed, before["status"], "refund_pending", actor)
    return await _settle_refund_attempt(
        db, claimed, reason=before.get("refund_reason") or "Refund retry", check_existing=True, actor=actor,
    )


async def _settle_refund_attempt(db, claimed: dict, *, reason: str, check_existing: bool,
                                 actor: Optional[dict]) -> dict:
    """Runs one refund attempt for an escrow this caller has claimed into
    refund_pending, and records the outcome (see refund()'s docstring for
    the three outcomes). Never raises for a gateway problem."""
    escrow_id = claimed["escrow_id"]
    payment_id = claimed.get("razorpay_payment_id")
    amount = float(claimed.get("amount") or 0)
    gateway_result: Optional[dict] = None
    error: Optional[str] = None
    outcome: Optional[str] = None
    try:
        if not payment_id or payment_id.startswith("pay_sim_"):
            outcome = "refunded"  # simulated payment: nothing to call
        else:
            remaining = amount
            if check_existing:
                existing = razorpay_svc.fetch_refunds(payment_id)
                processed = [r for r in existing if (r.get("status") or "").lower() == "processed"]
                in_flight = [r for r in existing if (r.get("status") or "").lower() in ("pending", "created")]
                remaining = round(amount - sum(float(r.get("amount_inr") or 0) for r in processed), 2)
                if remaining <= 0.009:
                    outcome = "refunded"
                    gateway_result = {"razorpay_refund_id": processed[-1]["razorpay_refund_id"], "status": "processed"}
                elif in_flight:
                    outcome = "refund_processing"
                    gateway_result = {"razorpay_refund_id": in_flight[-1]["razorpay_refund_id"], "status": in_flight[-1].get("status")}
            if outcome is None:
                gateway_result = razorpay_svc.refund_payment(
                    payment_id, amount_inr=remaining,
                    notes={"context_type": claimed.get("context_type"), "context_id": claimed.get("context_id"), "reason": reason,
                           # Attribution for refund webhooks: which escrow and which
                           # attempt this Razorpay refund belongs to (see
                           # settle_refund_from_gateway).
                           "escrow_id": escrow_id, "refund_attempt": claimed.get("refund_attempts")},
                )
                status = (gateway_result.get("status") or "").lower()
                if gateway_result.get("simulated") or status == "processed":
                    outcome = "refunded"
                elif status == "failed":
                    outcome, error = "refund_failed", "Razorpay reported the refund as failed"
                else:
                    outcome = "refund_processing"
    except Exception as e:
        outcome, error = "refund_failed", str(e)[:500] or e.__class__.__name__

    now = datetime.now(timezone.utc).isoformat()
    fields: Dict[str, Any] = {"status": outcome, "updated_at": now}
    if gateway_result:
        fields["gateway_refund_id"] = gateway_result.get("razorpay_refund_id")
        fields["gateway_refund_status"] = gateway_result.get("status")
    if outcome == "refund_failed":
        fields.update({"refund_last_error": error, "refund_failed_at": now})
    elif outcome == "refunded":
        fields["refund_completed_at"] = now
    # Settle only our own claim — conditional on still being refund_pending.
    res = await db.escrow_transactions.update_one({"escrow_id": escrow_id, "status": "refund_pending"}, {"$set": fields})
    if res.matched_count == 0:
        # Something else settled this escrow while our gateway call was in
        # flight (a refund webhook, or a stale-claim retry). Report the real
        # stored status instead of this attempt's outcome, and skip side
        # effects — whoever settled it already applied them.
        current = await db.escrow_transactions.find_one({"escrow_id": escrow_id}, {"_id": 0})
        return {**(current or claimed), "refund_settled_elsewhere": True}
    await _make_timeline_hook(db, escrow_id)(claimed, "refund_pending", outcome, actor)
    if outcome in ("refunded", "refund_processing"):
        await _reverse_payee_hold_once(db, claimed)
    claimed.update(fields)
    if outcome == "refund_processing" and fields.get("gateway_refund_id"):
        replayed = await _replay_logged_refund_webhook(db, fields["gateway_refund_id"], claimed.get("razorpay_payment_id"))
        if replayed and replayed.get("refund_settled"):
            return replayed
    return claimed


async def _replay_logged_refund_webhook(db, refund_id: str, payment_id: Optional[str]) -> Optional[dict]:
    """settle_refund_from_gateway only matches a refund id once it is stored
    on the escrow. If Razorpay's refund.processed/failed webhook for a NEW
    refund arrived before this attempt stored that id, the webhook was logged
    (payment_webhook_events) but matched nothing. Re-apply the latest logged
    event for this refund id now, so that webhook is never lost."""
    ev = await db.payment_webhook_events.find_one(
        {"razorpay_refund_id": refund_id, "event": {"$in": ["refund.processed", "refund.failed"]}},
        {"_id": 0, "event": 1}, sort=[("received_at", -1)],
    )
    if not ev:
        return None
    status = "processed" if ev["event"] == "refund.processed" else "failed"
    return await settle_refund_from_gateway(db, refund_id=refund_id, payment_id=payment_id, gateway_status=status)


def _as_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _record_stale_refund_event(db, escrow: dict, refund_id: Optional[str], status: str,
                                     attempt: Optional[int]) -> dict:
    """A refund webhook that belongs to an earlier refund attempt of this
    escrow (or can't be attributed unambiguously). It must not change the
    escrow's status, refund id or payee hold. It is recorded (idempotently)
    and — when that older refund was actually PROCESSED, i.e. money went
    back to the customer — flagged for admin review, because the current
    attempt may also refund (possible duplicate refund)."""
    update: Dict[str, Any] = {
        "$addToSet": {"stale_refund_events": {"refund_id": refund_id, "status": status, "attempt": attempt}},
        "$set": {"stale_refund_last_at": datetime.now(timezone.utc).isoformat()},
    }
    if status == "processed":
        update["$set"]["refund_needs_review"] = True
    await db.escrow_transactions.update_one({"escrow_id": escrow["escrow_id"]}, update)
    current = await db.escrow_transactions.find_one({"escrow_id": escrow["escrow_id"]}, {"_id": 0})
    return {**(current or escrow), "refund_settled": False, "refund_stale": True}


async def settle_refund_from_gateway(db, *, refund_id: Optional[str], payment_id: Optional[str],
                                     gateway_status: str, error: Optional[str] = None,
                                     notes: Optional[dict] = None) -> Optional[dict]:
    """Bug C: apply Razorpay's final word on a refund (refund.processed /
    refund.failed webhook) to the escrow that requested it. Matched by
    gateway_refund_id first, then by the refund's notes (escrow_id +
    refund_attempt — only the escrow's current attempt may settle it), then,
    for refunds without notes, by payment id only while a single refund
    request was ever sent. Returns the escrow with refund_settled True/False
    (False = duplicate/late/stale event, nothing changed; refund_stale True =
    event of an earlier attempt, recorded for review), or None when no
    escrow matched.

    Each step is a compare-and-swap on the current status, so a duplicate or
    late webhook is a no-op:
      processed: refund_processing | refund_failed | refund_pending -> refunded
                 (refund_failed covers a call that timed out after Razorpay
                 actually created the refund)
      failed:    refund_processing | refund_pending -> refund_failed
                 (never downgrades an escrow that is already refunded)"""
    notes = notes or {}
    status = (gateway_status or "").lower()
    if status not in ("processed", "failed"):
        return None
    escrow = None
    attempt_guard: Any = None
    if refund_id:
        escrow = await db.escrow_transactions.find_one({"gateway_refund_id": refund_id}, {"_id": 0})
    if not escrow and notes.get("escrow_id"):
        # Refunds CourtBazaar created carry escrow_id + refund_attempt in their
        # notes. Only the escrow's CURRENT attempt may settle it; an event for
        # an earlier attempt (e.g. refund A that timed out, then an admin
        # retry sent refund B) is recorded as stale and never applied.
        candidate = await db.escrow_transactions.find_one({"escrow_id": notes["escrow_id"]}, {"_id": 0})
        if candidate:
            attempt = _as_int(notes.get("refund_attempt"))
            if (attempt is not None and attempt == (candidate.get("refund_attempts") or 0)
                    and candidate.get("gateway_refund_id") in (None, refund_id)):
                escrow, attempt_guard = candidate, attempt
            else:
                return await _record_stale_refund_event(db, candidate, refund_id, status, attempt)
    if not escrow and payment_id and not notes.get("escrow_id"):
        # No attribution notes (refunds created before notes were added). The
        # payment id is only unambiguous while exactly ONE refund request was
        # ever sent for this escrow and no refund id is stored yet (first call
        # timed out). After a retry sent another request, an id-less match
        # could belong to either attempt — recorded as stale, never applied.
        candidate = await db.escrow_transactions.find_one(
            {"razorpay_payment_id": payment_id,
             "status": {"$in": ["refund_processing", "refund_failed", "refund_pending"]}}, {"_id": 0})
        if candidate:
            if candidate.get("gateway_refund_id") is None and (candidate.get("refund_attempts") or 0) <= 1:
                escrow, attempt_guard = candidate, "single"
            else:
                return await _record_stale_refund_event(db, candidate, refund_id, status, None)
    if not escrow:
        return None

    now = datetime.now(timezone.utc).isoformat()
    if status == "processed":
        from_states, to_state = ["refund_processing", "refund_failed", "refund_pending"], "refunded"
        fields = {"status": "refunded", "gateway_refund_status": "processed", "refund_completed_at": now, "updated_at": now}
    elif status == "failed":
        from_states, to_state = ["refund_processing", "refund_pending"], "refund_failed"
        fields = {"status": "refund_failed", "gateway_refund_status": "failed", "refund_failed_at": now, "updated_at": now,
                  "refund_last_error": error or "Razorpay reported the refund as failed"}
    if refund_id:
        fields["gateway_refund_id"] = refund_id

    # Same refund-id guard inside the atomic write, so a retry that records a
    # new refund id between the lookup above and this update can't be
    # overwritten by the older refund's event.
    cas: Dict[str, Any] = {"escrow_id": escrow["escrow_id"], "status": {"$in": from_states}}
    cas["gateway_refund_id"] = {"$in": [None, refund_id]} if refund_id else None
    # ...and the attempt that matched must still be the escrow's current one:
    # an admin retry claiming a new attempt in between makes this a no-op.
    if attempt_guard == "single":
        cas["refund_attempts"] = {"$not": {"$gt": 1}}
    elif attempt_guard is not None:
        cas["refund_attempts"] = attempt_guard
    before = await db.escrow_transactions.find_one_and_update(
        cas, {"$set": fields}, projection={"_id": 0}, return_document=ReturnDocument.BEFORE,
    )
    if not before:
        # Already settled (duplicate/late webhook) — no-op, but still report the match.
        current = await db.escrow_transactions.find_one({"escrow_id": escrow["escrow_id"]}, {"_id": 0})
        return {**(current or escrow), "refund_settled": False}
    await _make_timeline_hook(db, escrow["escrow_id"])(before, before["status"], to_state, {"user_id": "razorpay_webhook"})
    if to_state == "refunded":
        await _reverse_payee_hold_once(db, before)
    return {**before, **fields, "refund_settled": True}


async def _reverse_payee_hold_once(db, escrow: dict) -> None:
    """Moves the payee's wallet_held_balance back down exactly once per
    escrow, however many refund attempts/retries reach an accepted outcome
    — the payee_hold_reversed flag is claimed atomically first."""
    if not escrow.get("payee_user_id"):
        return
    res = await db.escrow_transactions.update_one(
        {"escrow_id": escrow["escrow_id"], "payee_hold_reversed": {"$ne": True}},
        {"$set": {"payee_hold_reversed": True}},
    )
    if res.modified_count == 1:
        await db.users.update_one(
            {"user_id": escrow["payee_user_id"]}, {"$inc": {"wallet_held_balance": -escrow["payee_amount"]}},
        )


async def get_for_context(db, context_type: str, context_id: str) -> Optional[dict]:
    return await db.escrow_transactions.find_one(
        {"context_type": context_type, "context_id": context_id}, {"_id": 0},
    )


async def list_transactions(db, context_type: Optional[str] = None, status: Optional[str] = None) -> list:
    """Read-only listing behind GET /admin/escrow-transactions — the general
    reporting/finance/wallet read path referenced in the refinement ask; not
    tied to hearings specifically, so any future escrow-using service shows
    up here without new code."""
    query: Dict[str, Any] = {}
    if context_type:
        query["context_type"] = context_type
    if status:
        query["status"] = status
    return await db.escrow_transactions.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
