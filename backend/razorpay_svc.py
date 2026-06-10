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


def verify_webhook(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")
