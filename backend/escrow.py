"""Escrow — the one payment-holding mechanism any service on the platform can
use (hearings today, anything else later). Owns *all* money state and math
(commission %, hold/release amounts) so call sites like hearings.py never
compute or store payout math themselves — hearings.py owns operational
workflow only, this module owns payment state, and neither reaches into the
other's transition table.

Payment lifecycle (independent of any service's own operational status):
    created -> captured -> held -> released
                            held -> refunded

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
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException
from pymongo import ReturnDocument

from workflow import StateMachine, IllegalTransition

ESCROW_TRANSITIONS = {
    ("created", "capture"): "captured",
    ("captured", "hold"): "held",
    ("held", "release"): "released",
    ("held", "refund"): "refunded",
}


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
    "released" while crediting nobody, silently losing track of the money."""
    escrow = await db.escrow_transactions.find_one({"context_type": context_type, "context_id": context_id})
    if not escrow:
        raise HTTPException(404, "No escrow record for this context")
    if not escrow.get("payee_user_id"):
        raise HTTPException(400, "Cannot release escrow with no payee assigned — call assign_payee first")
    sm = StateMachine(ESCROW_TRANSITIONS, _make_timeline_hook(db, escrow["escrow_id"]))
    try:
        await sm.apply(escrow, escrow["status"], "release", {"user_id": released_by_user_id})
    except IllegalTransition:
        raise HTTPException(400, f"Cannot release from status '{escrow['status']}'")

    now = datetime.now(timezone.utc).isoformat()
    await db.escrow_transactions.update_one(
        {"escrow_id": escrow["escrow_id"]}, {"$set": {"status": "released", "updated_at": now}},
    )
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
    escrow["status"] = "released"
    escrow.pop("_id", None)
    return escrow


async def refund(db, *, context_type: str, context_id: str, reason: str) -> dict:
    """held -> refunded: ledger-level only in this pass — an actual bank/
    gateway refund call is a documented future step (see module docstring),
    not built now. Reverses the wallet_held_balance bump from create_and_hold
    — skipped entirely if no payee was ever assigned (nothing to reverse;
    see assign_payee/module docstring for the deferred-payee case)."""
    escrow = await db.escrow_transactions.find_one({"context_type": context_type, "context_id": context_id})
    if not escrow:
        raise HTTPException(404, "No escrow record for this context")
    sm = StateMachine(ESCROW_TRANSITIONS, _make_timeline_hook(db, escrow["escrow_id"]))
    try:
        await sm.apply(escrow, escrow["status"], "refund", None)
    except IllegalTransition:
        raise HTTPException(400, f"Cannot refund from status '{escrow['status']}'")

    now = datetime.now(timezone.utc).isoformat()
    await db.escrow_transactions.update_one(
        {"escrow_id": escrow["escrow_id"]},
        {"$set": {"status": "refunded", "refund_reason": reason, "updated_at": now}},
    )
    if escrow.get("payee_user_id"):
        await db.users.update_one(
            {"user_id": escrow["payee_user_id"]}, {"$inc": {"wallet_held_balance": -escrow["payee_amount"]}},
        )
    escrow["status"] = "refunded"
    escrow["refund_reason"] = reason
    escrow.pop("_id", None)
    return escrow


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
