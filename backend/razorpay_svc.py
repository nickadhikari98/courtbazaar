"""Razorpay payment integration (alongside Stripe).
Fail-soft: if keys missing, returns simulated checkout for sandbox."""
import os
import logging
import uuid
import hmac
import hashlib
from typing import Optional

logger = logging.getLogger(__name__)

RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET")


def is_enabled() -> bool:
    return bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)


def _client():
    import razorpay
    c = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    return c


def create_order(amount_inr: float, order_ref: str, notes: dict = None) -> dict:
    """Create a Razorpay order. Returns dict with order_id and razorpay_order_id."""
    notes = notes or {}
    amount_paise = int(round(amount_inr * 100))
    if not is_enabled():
        # Fail-soft: simulated order
        rzp_order_id = f"order_sim_{uuid.uuid4().hex[:14]}"
        return {
            "razorpay_order_id": rzp_order_id,
            "amount": amount_paise,
            "currency": "INR",
            "key_id": "rzp_test_simulated",
            "notes": {**notes, "order_ref": order_ref},
            "simulated": True,
            "message": "Razorpay running in simulated mode. Add RAZORPAY_KEY_ID + RAZORPAY_KEY_SECRET to enable real checkout.",
        }
    try:
        c = _client()
        rzp_order = c.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": order_ref,
            "notes": {**notes, "order_ref": order_ref},
        })
        return {
            "razorpay_order_id": rzp_order["id"],
            "amount": amount_paise,
            "currency": "INR",
            "key_id": RAZORPAY_KEY_ID,
            "notes": rzp_order.get("notes", {}),
            "simulated": False,
        }
    except Exception as e:
        logger.error(f"Razorpay order create failed: {e}")
        raise


def verify_payment(razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> bool:
    """Verify Razorpay payment signature."""
    if not is_enabled():
        # In simulated mode, accept anything (for sandbox testing)
        return razorpay_order_id.startswith("order_sim_")
    try:
        c = _client()
        c.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })
        return True
    except Exception as e:
        logger.error(f"Razorpay verify failed: {e}")
        return False


def refund_payment(razorpay_payment_id: str, amount_inr: Optional[float] = None, notes: dict = None) -> dict:
    """Issue a refund for a captured payment. amount_inr=None means a full
    refund. Fail-soft mirrors create_order: a simulated payment id (or no
    keys configured) returns a fabricated refund record with no network
    call, so callers never need to branch on is_enabled() themselves."""
    notes = notes or {}
    if not is_enabled() or razorpay_payment_id.startswith("pay_sim_"):
        return {
            "razorpay_refund_id": f"rfnd_sim_{uuid.uuid4().hex[:14]}",
            "status": "processed",
            "simulated": True,
        }
    try:
        c = _client()
        payload = {"notes": notes}
        if amount_inr is not None:
            payload["amount"] = int(round(amount_inr * 100))
        rfnd = c.payment.refund(razorpay_payment_id, payload)
        return {
            "razorpay_refund_id": rfnd["id"],
            "status": rfnd.get("status", "processed"),
            "simulated": False,
        }
    except Exception as e:
        logger.error(f"Razorpay refund failed: {e}")
        raise


def fetch_refunds(razorpay_payment_id: str) -> list:
    """Refunds Razorpay already holds for a payment, as a list of
    {"razorpay_refund_id", "amount_inr", "status"} — used before RETRYING a
    refund, so a refund that actually went through (e.g. the first call
    timed out after Razorpay created it) is detected instead of requested
    again. Razorpay's refund API has no idempotency key, so this lookup is
    the client-side guard. Simulated payments / no keys -> [] (no network).
    Raises on a gateway error so callers never mistake "couldn't check" for
    "no refunds exist"."""
    if not is_enabled() or razorpay_payment_id.startswith("pay_sim_"):
        return []
    c = _client()
    resp = c.payment.fetch_multiple_refund(razorpay_payment_id)
    items = resp.get("items", []) if isinstance(resp, dict) else []
    return [
        {"razorpay_refund_id": r.get("id"), "amount_inr": (r.get("amount") or 0) / 100.0, "status": r.get("status")}
        for r in items
    ]


def verify_webhook(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")
