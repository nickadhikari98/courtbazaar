"""Razorpay live-mode gaps (issue #50): signature/webhook HMAC verification,
and the webhook-vs-/verify idempotency contract that keeps a payment from
being finalized twice or a late payment.failed from undoing a successful
capture.

Same convention as test_escrow_module.py: async wrappers against a real
Mongo instance, no HTTP layer — the actual webhook route's thin
Request-parsing shell (raw body read, header extraction, malformed-JSON
4xx) is exercised manually against Razorpay Test Mode per the rollout plan,
not here; FastAPI's TestClient needs httpx, which isn't a project
dependency. What's tested here is the logic that actually has to be
correct: HMAC verification, and the finalize/fail helpers' idempotency
guards, including under real concurrent invocation (asyncio.gather), not
just sequential calls.

One deviation from test_escrow_module.py's plain asyncio.run()-per-test
style: tests that call into server._finalize_*/_mark_payment_failed share
one persistent event loop (_run_with_server, defined below) instead, since
those functions close over server.py's own module-global Motor client —
see that helper's comment for why a fresh asyncio.run() per test breaks it.
"""
import asyncio
import hashlib
import hmac
import os
import sys
import uuid
from unittest.mock import MagicMock

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("JWT_SECRET", "test-only-not-a-real-secret")
import razorpay_svc  # noqa: E402
import hearings  # noqa: E402
import server  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _user(prefix):
    return {"user_id": f"test_rzp_{prefix}_{uuid.uuid4().hex[:10]}"}


class _keys:
    """Context manager: temporarily force razorpay_svc into "live" mode
    (is_enabled() == True) without ever making a real network call, and
    restore the original module state afterwards no matter what happens in
    the test body."""

    def __enter__(self):
        self._orig = (razorpay_svc.RAZORPAY_KEY_ID, razorpay_svc.RAZORPAY_KEY_SECRET, razorpay_svc.RAZORPAY_WEBHOOK_SECRET)
        razorpay_svc.RAZORPAY_KEY_ID = "rzp_test_fake"
        razorpay_svc.RAZORPAY_KEY_SECRET = "fake_secret_for_hmac"
        razorpay_svc.RAZORPAY_WEBHOOK_SECRET = "fake_webhook_secret"
        return self

    def __exit__(self, *exc):
        razorpay_svc.RAZORPAY_KEY_ID, razorpay_svc.RAZORPAY_KEY_SECRET, razorpay_svc.RAZORPAY_WEBHOOK_SECRET = self._orig


# ---------- Signature / webhook HMAC verification ----------

def test_verify_payment_accepts_valid_signature_and_rejects_tampered():
    with _keys():
        order_id, payment_id = "order_abc123", "pay_xyz789"
        sig = hmac.new(
            razorpay_svc.RAZORPAY_KEY_SECRET.encode(),
            f"{order_id}|{payment_id}".encode(), hashlib.sha256,
        ).hexdigest()
        assert razorpay_svc.verify_payment(order_id, payment_id, sig) is True
        assert razorpay_svc.verify_payment(order_id, payment_id, sig[:-1] + ("0" if sig[-1] != "0" else "1")) is False


def test_verify_webhook_valid_wrong_and_missing_signature():
    secret = "whsec_fake"
    body = b'{"event": "payment.captured"}'
    valid_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert razorpay_svc.verify_webhook(body, valid_sig, secret) is True
    assert razorpay_svc.verify_webhook(body, "wrong" + valid_sig, secret) is False
    assert razorpay_svc.verify_webhook(body, "", secret) is False
    assert razorpay_svc.verify_webhook(body, None, secret) is False


def test_create_order_and_refund_payment_live_mode_use_mocked_client_no_network_call():
    with _keys():
        fake_client = MagicMock()
        fake_client.order.create.return_value = {"id": "order_live_123", "notes": {}}
        fake_client.payment.refund.return_value = {"id": "rfnd_live_456", "status": "processed"}
        orig_client_fn = razorpay_svc._client
        razorpay_svc._client = lambda: fake_client
        try:
            order = razorpay_svc.create_order(1500.0, "ref-1")
            assert order["simulated"] is False
            assert order["razorpay_order_id"] == "order_live_123"
            fake_client.order.create.assert_called_once()

            refund = razorpay_svc.refund_payment("pay_live_789", amount_inr=1500.0)
            assert refund["simulated"] is False
            assert refund["razorpay_refund_id"] == "rfnd_live_456"
            fake_client.payment.refund.assert_called_once()
        finally:
            razorpay_svc._client = orig_client_fn


def test_refund_payment_simulated_path_makes_no_client_call():
    # Keys unset -> is_enabled() False -> must never construct a real client.
    orig = (razorpay_svc.RAZORPAY_KEY_ID, razorpay_svc.RAZORPAY_KEY_SECRET)
    razorpay_svc.RAZORPAY_KEY_ID, razorpay_svc.RAZORPAY_KEY_SECRET = None, None
    try:
        result = razorpay_svc.refund_payment("pay_sim_abc123")
        assert result["simulated"] is True
        assert result["razorpay_refund_id"].startswith("rfnd_sim_")
    finally:
        razorpay_svc.RAZORPAY_KEY_ID, razorpay_svc.RAZORPAY_KEY_SECRET = orig


# ---------- _finalize_hearing_payment idempotency ----------

# server._finalize_*/_mark_payment_failed close over server.py's own
# module-global Motor client, which binds to whichever event loop first
# runs an operation on it. Plain asyncio.run() tears its loop down when the
# test function returns, so a second, unrelated asyncio.run() call later in
# this file hands that same client a fresh loop and Motor raises "Event
# loop is closed" on the next operation. Tests below that call into
# server.* share one persistent loop instead; tests using only a fresh
# local _db() (no server.* calls) keep plain asyncio.run(), matching every
# other test file's convention.
_server_loop = asyncio.new_event_loop()


def _run_with_server(coro):
    return _server_loop.run_until_complete(coro)


async def _cleanup(db, hearing_ids=(), order_ids=()):
    if hearing_ids:
        await db.hearing_requests.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
        await db.escrow_transactions.delete_many({"context_id": {"$in": list(hearing_ids)}})
        await db.payment_transactions.delete_many({"context_id": {"$in": list(hearing_ids)}})
        await db.notification_events.delete_many({"related_entity_id": {"$in": list(hearing_ids)}})
    if order_ids:
        await db.orders.delete_many({"order_id": {"$in": list(order_ids)}})
        await db.payment_transactions.delete_many({"order_id": {"$in": list(order_ids)}})


async def _hearing_awaiting_confirmation(db, requester, fee=1500.0):
    """create_hearing_request -> initiate_payment gets a hearing to
    "payment_pending", the real precondition _finalize_hearing_payment's
    call into mark_payment_confirmed requires (confirm_payment is only
    legal from payment_pending) — no state is skipped/faked."""
    hearing = await hearings.create_hearing_request(
        db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", fee, None,
    )
    hearing_id = hearing["hearing_id"]
    await hearings.initiate_payment(db, hearing_id, requester)
    rzp_order_id = f"order_{uuid.uuid4().hex[:12]}"
    await db.payment_transactions.insert_one({
        "razorpay_order_id": rzp_order_id, "context_type": "hearing", "context_id": hearing_id,
        "user_id": requester["user_id"], "amount": fee, "currency": "INR", "gateway": "razorpay",
        "status": "initiated", "payment_status": "pending", "simulated": True,
    })
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
    tx = await db.payment_transactions.find_one({"razorpay_order_id": rzp_order_id}, {"_id": 0})
    return hearing, tx


def test_finalize_hearing_payment_is_idempotent_against_duplicate_calls():
    async def body():
        db = _db()
        requester = _user("requester")
        hearing, tx = await _hearing_awaiting_confirmation(db, requester)
        hearing_id = hearing["hearing_id"]
        try:
            rzp_payment_id = f"pay_{uuid.uuid4().hex[:12]}"
            first = await server._finalize_hearing_payment(hearing, tx, rzp_payment_id)
            second = await server._finalize_hearing_payment(hearing, tx, rzp_payment_id)
            assert first is True
            assert second is False  # already finalized — must be a no-op, not a duplicate

            escrow_docs = await db.escrow_transactions.find({"context_id": hearing_id}).to_list(10)
            assert len(escrow_docs) == 1  # not two

            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "broadcast"
        finally:
            await _cleanup(db, hearing_ids=[hearing_id])
    _run_with_server(body())


def test_finalize_hearing_payment_concurrent_calls_only_finalize_once():
    """The actual production race this whole feature exists to close: the
    client's own /verify call and a webhook delivery landing at nearly the
    same instant, not one strictly after the other."""
    async def body():
        db = _db()
        requester = _user("requester")
        hearing, tx = await _hearing_awaiting_confirmation(db, requester)
        hearing_id = hearing["hearing_id"]
        try:
            rzp_payment_id = f"pay_{uuid.uuid4().hex[:12]}"
            results = await asyncio.gather(
                server._finalize_hearing_payment(hearing, tx, rzp_payment_id),
                server._finalize_hearing_payment(hearing, tx, rzp_payment_id),
            )
            assert sorted(results) == [False, True]  # exactly one side effect chain ran

            escrow_docs = await db.escrow_transactions.find({"context_id": hearing_id}).to_list(10)
            assert len(escrow_docs) == 1
        finally:
            await _cleanup(db, hearing_ids=[hearing_id])
    _run_with_server(body())


# ---------- _mark_payment_failed must never undo a successful capture ----------

def test_mark_payment_failed_before_paid_succeeds():
    async def body():
        db = _db()
        order_id = f"order_{uuid.uuid4().hex[:12]}"
        await db.payment_transactions.insert_one({
            "razorpay_order_id": order_id, "order_id": f"ord_{uuid.uuid4().hex[:10]}",
            "payment_status": "pending", "status": "initiated",
        })
        try:
            changed = await server._mark_payment_failed(order_id, f"pay_{uuid.uuid4().hex[:10]}")
            assert changed is True
            tx = await db.payment_transactions.find_one({"razorpay_order_id": order_id}, {"_id": 0})
            assert tx["payment_status"] == "failed"
        finally:
            await db.payment_transactions.delete_many({"razorpay_order_id": order_id})
    _run_with_server(body())


def test_mark_payment_failed_after_paid_is_a_noop():
    """Out-of-order webhook delivery: a payment.failed for an earlier failed
    attempt on the same order arrives AFTER a later payment.captured already
    marked it paid. Must not regress paid -> failed."""
    async def body():
        db = _db()
        order_id = f"order_{uuid.uuid4().hex[:12]}"
        await db.payment_transactions.insert_one({
            "razorpay_order_id": order_id, "order_id": f"ord_{uuid.uuid4().hex[:10]}",
            "payment_status": "paid", "status": "complete",
        })
        try:
            changed = await server._mark_payment_failed(order_id, f"pay_{uuid.uuid4().hex[:10]}")
            assert changed is False
            tx = await db.payment_transactions.find_one({"razorpay_order_id": order_id}, {"_id": 0})
            assert tx["payment_status"] == "paid"  # unchanged
        finally:
            await db.payment_transactions.delete_many({"razorpay_order_id": order_id})
    _run_with_server(body())


# ---------- _finalize_marketplace_payment idempotency ----------

def test_finalize_marketplace_payment_is_idempotent():
    async def body():
        db = _db()
        order_id = f"ord_{uuid.uuid4().hex[:10]}"
        rzp_order_id = f"order_{uuid.uuid4().hex[:12]}"
        await db.orders.insert_one({"order_id": order_id, "status": "pending_payment", "payment_status": "pending", "timeline": []})
        await db.payment_transactions.insert_one({
            "razorpay_order_id": rzp_order_id, "order_id": order_id,
            "payment_status": "pending", "status": "initiated",
        })
        try:
            tx = await db.payment_transactions.find_one({"razorpay_order_id": rzp_order_id}, {"_id": 0})
            rzp_payment_id = f"pay_{uuid.uuid4().hex[:12]}"
            first = await server._finalize_marketplace_payment(tx, rzp_payment_id)
            second = await server._finalize_marketplace_payment(tx, rzp_payment_id)
            assert first is True
            assert second is False

            order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
            assert order["status"] == "matched"
            assert len(order["timeline"]) == 1  # not pushed twice
        finally:
            await _cleanup(db, order_ids=[order_id])
    _run_with_server(body())
