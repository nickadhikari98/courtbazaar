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


# ---------- Orphaned captured payments (Bug A) ----------
#
# A capture must win an atomic per-hearing claim before any escrow is
# created; a capture that loses it (hearing no longer payment_pending, or
# already claimed by another order) is refunded and recorded, never
# attached. Refunds are counted through a stub so no gateway call is made.

import payment_reconciliation  # noqa: E402


class _count_refunds:
    """Context manager: replace razorpay_svc.refund_payment with a counting
    stub (no network), restoring the original afterwards."""
    def __enter__(self):
        self.calls = []
        self._orig = razorpay_svc.refund_payment

        def _stub(payment_id, amount_inr=None, notes=None):
            self.calls.append({"payment_id": payment_id, "amount_inr": amount_inr, "notes": notes})
            return {"razorpay_refund_id": f"rfnd_test_{uuid.uuid4().hex[:10]}", "status": "processed", "simulated": True}
        razorpay_svc.refund_payment = _stub
        return self

    def __exit__(self, *exc):
        razorpay_svc.refund_payment = self._orig


async def _second_order_for(db, hearing, requester, fee=1500.0):
    """A second checkout for the same hearing — what the payment_pending
    self-loop (second tab / retry) produces: a new Razorpay order and row."""
    rzp_order_id = f"order_{uuid.uuid4().hex[:12]}"
    await db.payment_transactions.insert_one({
        "razorpay_order_id": rzp_order_id, "context_type": "hearing", "context_id": hearing["hearing_id"],
        "user_id": requester["user_id"], "amount": fee, "currency": "INR", "gateway": "razorpay",
        "status": "initiated", "payment_status": "pending", "simulated": True,
    })
    return await db.payment_transactions.find_one({"razorpay_order_id": rzp_order_id}, {"_id": 0})


async def _cleanup_orphan_audit(db, order_ids):
    await db.audit_log.delete_many({
        "action": {"$in": ["payment.orphaned_capture", "payment.finalize_failed"]},
        "details.razorpay_order_id": {"$in": list(order_ids)},
    })


# ---------- Finalize failure after the hearing claim (PR #53 review) ----------
#
# A capture that wins both claims but then fails in escrow/confirmation
# leaves the hearing payment_pending with payment_claim_order_id set and the
# transaction already "paid" — so no retry can finish it. It must be visible
# to admins and must never be reported to the client as a success.

import escrow  # noqa: E402
from fastapi import HTTPException  # noqa: E402


class _failing_escrow:
    """Context manager: make escrow.create_and_hold raise, restoring it
    afterwards (payment_reconciliation calls it through the module)."""
    def __enter__(self):
        self._orig = escrow.create_and_hold

        async def _boom(*a, **k):
            raise RuntimeError("escrow insert failed (test)")
        escrow.create_and_hold = _boom
        return self

    def __exit__(self, *exc):
        escrow.create_and_hold = self._orig


def test_finalize_error_is_surfaced_in_admin_reconciliation():
    async def body():
        db = _db()
        requester = _user("requester")
        hearing, tx = await _hearing_awaiting_confirmation(db, requester)
        hearing_id = hearing["hearing_id"]
        order_id = tx["razorpay_order_id"]
        # A normal, successfully finalized payment alongside it must stay unflagged.
        ok_hearing, ok_tx = await _hearing_awaiting_confirmation(db, requester)
        now = "9999-12-31T00:00:00+00:00"  # sort both rows to the top of the reconciliation window
        await db.payment_transactions.update_many(
            {"razorpay_order_id": {"$in": [order_id, ok_tx["razorpay_order_id"]]}}, {"$set": {"created_at": now}},
        )
        try:
            with _failing_escrow():
                try:
                    await server._finalize_hearing_payment(hearing, tx, f"pay_{uuid.uuid4().hex[:12]}")
                    raise AssertionError("finalize should have re-raised the escrow failure")
                except RuntimeError as e:
                    assert "escrow insert failed" in str(e)
            assert await server._finalize_hearing_payment(ok_hearing, ok_tx, f"pay_{uuid.uuid4().hex[:12]}") is True

            ftx = await db.payment_transactions.find_one({"razorpay_order_id": order_id}, {"_id": 0})
            assert "escrow insert failed" in ftx["finalize_error"]
            assert await db.audit_log.count_documents(
                {"action": "payment.finalize_failed", "details.razorpay_order_id": order_id}) == 1
            stuck = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert stuck["status"] == "payment_pending"
            assert stuck["payment_claim_order_id"] == order_id

            report = await server.admin_reconciliation(
                user={"role": "admin", "user_id": "test_rzp_admin"},
                gateway=None, status_filter=None, from_date=None, to_date=None,
            )
            rows = {r["razorpay_order_id"]: r for r in report["rows"]}
            assert rows[order_id]["mismatch"] is True
            assert "Finalize failed after capture" in rows[order_id]["mismatch_reason"]
            assert "escrow insert failed" in rows[order_id]["mismatch_reason"]
            flagged = [m for m in report["mismatches"] if m["session_id"] == ftx.get("session_id")
                       and "Finalize failed after capture" in m["reason"]]
            assert len(flagged) == 1 and flagged[0]["order_id"] == hearing_id
            # Normal reconciliation behaviour unchanged for the healthy payment.
            assert rows[ok_tx["razorpay_order_id"]]["mismatch"] is False
            assert rows[ok_tx["razorpay_order_id"]]["mismatch_reason"] is None
        finally:
            await _cleanup_orphan_audit(db, [order_id, ok_tx["razorpay_order_id"]])
            await _cleanup(db, hearing_ids=[hearing_id, ok_hearing["hearing_id"]])
    _run_with_server(body())


def test_verify_does_not_report_broadcast_when_finalize_failed():
    async def body():
        db = _db()
        requester = _user("requester")
        hearing, tx = await _hearing_awaiting_confirmation(db, requester)
        hearing_id = hearing["hearing_id"]
        order_id = tx["razorpay_order_id"]
        payload = {"razorpay_order_id": order_id, "razorpay_payment_id": f"pay_{uuid.uuid4().hex[:12]}",
                   "razorpay_signature": "sig_test"}
        orig_verify = razorpay_svc.verify_payment
        razorpay_svc.verify_payment = lambda *a, **k: True  # signature check itself is covered elsewhere
        try:
            # First attempt: capture claims the hearing, escrow fails -> error propagates.
            with _failing_escrow():
                try:
                    await server.verify_hearing_payment(hearing_id, payload, user=requester)
                    raise AssertionError("first verify should have failed")
                except RuntimeError:
                    pass
            # Retry (client retry, or after a webhook no-op): must NOT claim success.
            try:
                await server.verify_hearing_payment(hearing_id, payload, user=requester)
                raise AssertionError("verify must not return a success/broadcast response")
            except HTTPException as e:
                assert e.status_code == 500
                assert "could not be finalized" in e.detail
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "payment_pending"
            assert await db.escrow_transactions.count_documents({"context_id": hearing_id}) == 0
            # Authorization is unchanged: a different user is still refused before any of this.
            try:
                await server.verify_hearing_payment(hearing_id, payload, user=_user("stranger"))
                raise AssertionError("non-requester must be refused")
            except HTTPException as e:
                assert e.status_code in (403, 404)
        finally:
            razorpay_svc.verify_payment = orig_verify
            await _cleanup_orphan_audit(db, [order_id])
            await _cleanup(db, hearing_ids=[hearing_id])
    _run_with_server(body())


def test_orphan_valid_capture_is_attached_normally():
    """A. hearing payment_pending -> capture attaches, escrow held, broadcast."""
    async def body():
        db = _db()
        requester = _user("requester")
        hearing, tx = await _hearing_awaiting_confirmation(db, requester)
        hearing_id = hearing["hearing_id"]
        try:
            with _count_refunds() as refunds:
                ok = await server._finalize_hearing_payment(hearing, tx, f"pay_{uuid.uuid4().hex[:12]}")
            assert ok is True
            assert refunds.calls == []
            escrows = await db.escrow_transactions.find({"context_id": hearing_id}).to_list(10)
            assert len(escrows) == 1 and escrows[0]["status"] == "held"
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "broadcast"
            assert fetched["payment_claim_order_id"] == tx["razorpay_order_id"]
            ftx = await db.payment_transactions.find_one({"razorpay_order_id": tx["razorpay_order_id"]}, {"_id": 0})
            assert ftx["payment_status"] == "paid"
            assert not ftx.get("orphaned")
        finally:
            await _cleanup(db, hearing_ids=[hearing_id])
    _run_with_server(body())


def test_orphan_duplicate_capture_no_second_escrow_or_refund():
    """B. same order delivered again (verify + webhook) -> no duplicate
    escrow, no refund at all."""
    async def body():
        db = _db()
        requester = _user("requester")
        hearing, tx = await _hearing_awaiting_confirmation(db, requester)
        hearing_id = hearing["hearing_id"]
        try:
            pay_id = f"pay_{uuid.uuid4().hex[:12]}"
            with _count_refunds() as refunds:
                first = await server._finalize_hearing_payment(hearing, tx, pay_id)
                second = await server._finalize_hearing_payment(hearing, tx, pay_id)
            assert (first, second) == (True, False)
            assert refunds.calls == []
            assert await db.escrow_transactions.count_documents({"context_id": hearing_id}) == 1
            ftx = await db.payment_transactions.find_one({"razorpay_order_id": tx["razorpay_order_id"]}, {"_id": 0})
            assert not ftx.get("orphaned")
        finally:
            await _cleanup(db, hearing_ids=[hearing_id])
    _run_with_server(body())


def test_orphan_late_capture_after_cancel_is_refunded_not_attached():
    """C. hearing cancelled while checkout was open, then the capture
    arrives -> no escrow, hearing stays cancelled, refunded once, recorded;
    a repeat delivery does not refund again."""
    async def body():
        db = _db()
        requester = _user("requester")
        hearing, tx = await _hearing_awaiting_confirmation(db, requester)
        hearing_id = hearing["hearing_id"]
        order_id = tx["razorpay_order_id"]
        try:
            await hearings.cancel_hearing_request(db, hearing_id, requester)
            pay_id = f"pay_{uuid.uuid4().hex[:12]}"
            with _count_refunds() as refunds:
                result = await server._finalize_hearing_payment(hearing, tx, pay_id)
                repeat = await server._finalize_hearing_payment(hearing, tx, pay_id)
            assert result is False and repeat is False
            assert len(refunds.calls) == 1
            assert refunds.calls[0]["payment_id"] == pay_id
            assert refunds.calls[0]["amount_inr"] == tx["amount"]
            assert await db.escrow_transactions.count_documents({"context_id": hearing_id}) == 0
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "cancelled"
            assert not fetched.get("payment_claim_order_id")
            ftx = await db.payment_transactions.find_one({"razorpay_order_id": order_id}, {"_id": 0})
            assert ftx["orphaned"] is True
            assert ftx["orphan_reason"] == "hearing_not_payable:cancelled"
            assert ftx["orphan_refund_status"] == "processed"
            assert ftx["orphan_refund_id"].startswith("rfnd_test_")
            assert await db.audit_log.count_documents(
                {"action": "payment.orphaned_capture", "details.razorpay_order_id": order_id}) == 1
        finally:
            await _cleanup_orphan_audit(db, [order_id])
            await _cleanup(db, hearing_ids=[hearing_id])
    _run_with_server(body())


def test_orphan_two_orders_same_hearing_only_one_attaches():
    """D. two different orders for one hearing captured concurrently ->
    exactly one attaches (one escrow), the other is refunded and recorded."""
    async def body():
        db = _db()
        requester = _user("requester")
        hearing, tx1 = await _hearing_awaiting_confirmation(db, requester)
        hearing_id = hearing["hearing_id"]
        tx2 = await _second_order_for(db, hearing, requester)
        order_ids = [tx1["razorpay_order_id"], tx2["razorpay_order_id"]]
        try:
            with _count_refunds() as refunds:
                results = await asyncio.gather(
                    server._finalize_hearing_payment(hearing, tx1, f"pay_{uuid.uuid4().hex[:12]}"),
                    server._finalize_hearing_payment(hearing, tx2, f"pay_{uuid.uuid4().hex[:12]}"),
                )
            assert sorted(results) == [False, True]
            assert len(refunds.calls) == 1
            escrows = await db.escrow_transactions.find({"context_id": hearing_id}, {"_id": 0}).to_list(10)
            assert len(escrows) == 1
            winner = order_ids[results.index(True)]
            loser = order_ids[results.index(False)]
            assert escrows[0]["razorpay_order_id"] == winner
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "broadcast"
            assert fetched["payment_claim_order_id"] == winner
            ltx = await db.payment_transactions.find_one({"razorpay_order_id": loser}, {"_id": 0})
            assert ltx["orphaned"] is True
            assert ltx["orphan_reason"] in (f"hearing_already_claimed_by:{winner}", "hearing_not_payable:broadcast")
            wtx = await db.payment_transactions.find_one({"razorpay_order_id": winner}, {"_id": 0})
            assert not wtx.get("orphaned")
        finally:
            await _cleanup_orphan_audit(db, order_ids)
            await _cleanup(db, hearing_ids=[hearing_id])
    _run_with_server(body())


def test_orphan_capture_for_missing_hearing_is_refunded_once():
    """E. capture references a hearing that doesn't exist -> no escrow,
    refunded and recorded once; a repeat webhook delivery is a no-op."""
    async def body():
        db = _db()
        missing_hearing_id = f"hearing_missing_{uuid.uuid4().hex[:10]}"
        order_id = f"order_{uuid.uuid4().hex[:12]}"
        await db.payment_transactions.insert_one({
            "razorpay_order_id": order_id, "context_type": "hearing", "context_id": missing_hearing_id,
            "user_id": _user("requester")["user_id"], "amount": 999.0, "currency": "INR", "gateway": "razorpay",
            "status": "initiated", "payment_status": "pending", "simulated": True,
        })
        try:
            tx = await db.payment_transactions.find_one({"razorpay_order_id": order_id}, {"_id": 0})
            pay_id = f"pay_{uuid.uuid4().hex[:12]}"
            with _count_refunds() as refunds:
                first = await payment_reconciliation.handle_orphaned_capture(server.db, tx, pay_id, "hearing_not_found")
                second = await payment_reconciliation.handle_orphaned_capture(server.db, tx, pay_id, "hearing_not_found")
            assert (first, second) == (True, False)
            assert len(refunds.calls) == 1
            assert await db.escrow_transactions.count_documents({"context_id": missing_hearing_id}) == 0
            ftx = await db.payment_transactions.find_one({"razorpay_order_id": order_id}, {"_id": 0})
            assert ftx["payment_status"] == "paid"  # money was captured
            assert ftx["orphaned"] is True and ftx["orphan_reason"] == "hearing_not_found"
            assert await db.audit_log.count_documents(
                {"action": "payment.orphaned_capture", "details.razorpay_order_id": order_id}) == 1
        finally:
            await _cleanup_orphan_audit(db, [order_id])
            await db.payment_transactions.delete_many({"razorpay_order_id": order_id})
    _run_with_server(body())


def test_orphan_refund_failure_is_recorded_not_raised():
    """A failing gateway refund must leave a visible record for admins, not
    crash the webhook (and never attach the payment)."""
    async def body():
        db = _db()
        requester = _user("requester")
        hearing, tx = await _hearing_awaiting_confirmation(db, requester)
        hearing_id = hearing["hearing_id"]
        order_id = tx["razorpay_order_id"]
        orig = razorpay_svc.refund_payment

        def _boom(*a, **k):
            raise RuntimeError("gateway down")
        try:
            await hearings.cancel_hearing_request(db, hearing_id, requester)
            razorpay_svc.refund_payment = _boom
            result = await server._finalize_hearing_payment(hearing, tx, f"pay_{uuid.uuid4().hex[:12]}")
            assert result is False
            ftx = await db.payment_transactions.find_one({"razorpay_order_id": order_id}, {"_id": 0})
            assert ftx["orphaned"] is True
            assert ftx["orphan_refund_status"] == "failed"
            assert "gateway down" in ftx["orphan_refund_error"]
            assert await db.escrow_transactions.count_documents({"context_id": hearing_id}) == 0
        finally:
            razorpay_svc.refund_payment = orig
            await _cleanup_orphan_audit(db, [order_id])
            await _cleanup(db, hearing_ids=[hearing_id])
    _run_with_server(body())


def test_cancel_refused_once_a_payment_has_claimed_the_hearing():
    """Race guard: after a capture claims the hearing (and before it reaches
    broadcast), cancel/reject out of payment_pending must lose atomically."""
    async def body():
        db = _db()
        requester = _user("requester")
        hearing, tx = await _hearing_awaiting_confirmation(db, requester)
        hearing_id = hearing["hearing_id"]
        try:
            claimed = await payment_reconciliation._claim_hearing_for_payment(db, hearing_id, tx["razorpay_order_id"])
            assert claimed is not None
            # A second claim for another order loses.
            assert await payment_reconciliation._claim_hearing_for_payment(db, hearing_id, "order_other") is None
            try:
                await hearings.cancel_hearing_request(db, hearing_id, requester)
                raise AssertionError("cancel should have been refused")
            except hearings.HTTPException as e:
                assert e.status_code == 409
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "payment_pending"
        finally:
            await _cleanup(db, hearing_ids=[hearing_id])
    asyncio.run(body())


def test_reconciliation_reports_locked_payee_hold_for_failed_refund():
    """A failed refund on an escrow with an assigned payee: the payee's held
    balance is still counted (only reversed once a refund is accepted), and
    reconciliation says so; once processing is accepted the lock is gone."""
    async def body():
        import escrow as escrow_mod
        db = _db()
        admin = {"user_id": _user("admin")["user_id"], "role": "admin"}
        payee = _user("payee")
        context_id = f"hearing_bugb_{uuid.uuid4().hex[:10]}"
        await db.users.insert_one({"user_id": payee["user_id"], "wallet_held_balance": 0})
        doc = await escrow_mod.create_and_hold(
            db, context_type="hearing", context_id=context_id, service_id=hearings.ESCROW_SERVICE_ID,
            matter_id=None, payer_user_id=_user("payer")["user_id"], payee_user_id=payee["user_id"],
            amount=1500.0, platform_commission_pct=0.2,
            razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=f"pay_live_{uuid.uuid4().hex[:10]}",
        )
        orig = (razorpay_svc.refund_payment, razorpay_svc.fetch_refunds)
        try:
            def _fail(*a, **k):
                raise RuntimeError("gateway down")
            razorpay_svc.refund_payment, razorpay_svc.fetch_refunds = _fail, (lambda pid: [])
            await escrow_mod.refund(db, context_type="hearing", context_id=context_id, reason="t")
            report = await server.admin_reconciliation(user=admin, gateway=None, status_filter=None, from_date=None, to_date=None)
            m = [x for x in report["mismatches"] if x.get("escrow_id") == doc["escrow_id"]][0]
            assert m["escrow_status"] == "refund_failed"
            assert m["payee_hold_locked"] is True and m["payee_amount"] == doc["payee_amount"]

            razorpay_svc.refund_payment = lambda pid, amount_inr=None, notes=None: {
                "razorpay_refund_id": "rfnd_p", "status": "pending", "simulated": False}
            out = await escrow_mod.retry_refund(db, doc["escrow_id"], {"user_id": admin["user_id"]})
            assert out["status"] == "refund_processing"
            report = await server.admin_reconciliation(user=admin, gateway=None, status_filter=None, from_date=None, to_date=None)
            m = [x for x in report["mismatches"] if x.get("escrow_id") == doc["escrow_id"]][0]
            assert m["escrow_status"] == "refund_processing"
            assert m["payee_hold_locked"] is False and m["payee_amount"] is None
        finally:
            razorpay_svc.refund_payment, razorpay_svc.fetch_refunds = orig
            await db.escrow_transactions.delete_many({"context_id": context_id})
            await db.users.delete_many({"user_id": payee["user_id"]})
    _run_with_server(body())


# ---------- Bug B: failed refunds are visible to admins and retryable ----------

import escrow  # noqa: E402


def test_refund_failure_visible_in_reconciliation_and_admin_retry_endpoint():
    async def body():
        db = _db()
        admin = {"user_id": _user("admin")["user_id"], "role": "admin"}
        non_admin = {"user_id": _user("user")["user_id"], "role": "client"}
        context_id = f"hearing_bugb_{uuid.uuid4().hex[:10]}"
        doc = await escrow.create_and_hold(
            db, context_type="hearing", context_id=context_id, service_id=hearings.ESCROW_SERVICE_ID,
            matter_id=None, payer_user_id=_user("payer")["user_id"], payee_user_id=None,
            amount=1500.0, platform_commission_pct=0.2,
            razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=f"pay_live_{uuid.uuid4().hex[:10]}",
        )
        orig = (razorpay_svc.refund_payment, razorpay_svc.fetch_refunds)
        try:
            def _fail(*a, **k):
                raise RuntimeError("gateway down")
            razorpay_svc.refund_payment, razorpay_svc.fetch_refunds = _fail, (lambda pid: [])
            r = await escrow.refund(db, context_type="hearing", context_id=context_id, reason="t")
            assert r["status"] == "refund_failed"

            report = await server.admin_reconciliation(user=admin, gateway=None, status_filter=None, from_date=None, to_date=None)
            flagged = [m for m in report["mismatches"] if m.get("escrow_id") == doc["escrow_id"]]
            assert len(flagged) == 1 and "refund_failed" in flagged[0]["reason"] and "gateway down" in flagged[0]["reason"]
            # Structured fields the admin UI renders (status badge / Retry button / hold note).
            assert flagged[0]["escrow_status"] == "refund_failed"
            assert flagged[0]["amount"] == 1500.0
            assert flagged[0]["payee_hold_locked"] is False  # no payee assigned on this escrow

            try:
                await server.admin_retry_escrow_refund(doc["escrow_id"], user=non_admin)
                raise AssertionError("non-admin must be refused")
            except server.HTTPException as e:
                assert e.status_code == 403

            razorpay_svc.refund_payment = lambda pid, amount_inr=None, notes=None: {
                "razorpay_refund_id": "rfnd_admin", "status": "processed", "simulated": False}
            out = await server.admin_retry_escrow_refund(doc["escrow_id"], user=admin)
            assert out["status"] == "refunded"
            again = await server.admin_retry_escrow_refund(doc["escrow_id"], user=admin)  # double click
            assert again["status"] == "refunded" and again["gateway_refund_id"] == "rfnd_admin"

            report = await server.admin_reconciliation(user=admin, gateway=None, status_filter=None, from_date=None, to_date=None)
            assert not [m for m in report["mismatches"] if m.get("escrow_id") == doc["escrow_id"]]
            assert await db.audit_log.count_documents({"action": "payment.refund_retry", "details.escrow_id": doc["escrow_id"]}) == 2
        finally:
            razorpay_svc.refund_payment, razorpay_svc.fetch_refunds = orig
            await db.escrow_transactions.delete_many({"context_id": context_id})
            await db.audit_log.delete_many({"action": "payment.refund_retry", "details.escrow_id": doc["escrow_id"]})
    _run_with_server(body())


# ---------- Bug C: refund.* webhooks + orphan-refund retry ----------
# The webhook is exercised through the real route handler with a
# hand-built Starlette Request (signed body, no httpx, no network).

import json  # noqa: E402
from starlette.requests import Request  # noqa: E402

_WEBHOOK_SECRET = "whsec_test_only"


def _signed_webhook_request(payload: dict, secret: str = _WEBHOOK_SECRET) -> Request:
    body = json.dumps(payload).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}
    scope = {"type": "http", "method": "POST", "path": "/api/payments/razorpay/webhook", "query_string": b"",
             "headers": [(b"x-razorpay-signature", sig.encode()), (b"content-type", b"application/json")]}
    return Request(scope, receive)


def _refund_event(event, refund_id, payment_id, amount_inr=1500.0, **extra):
    entity = {"id": refund_id, "payment_id": payment_id, "amount": int(round(amount_inr * 100)),
              "status": "processed" if event == "refund.processed" else "failed", **extra}
    return {"event": event, "payload": {"refund": {"entity": entity}}}


class _webhook_secret:
    def __enter__(self):
        self._orig = razorpay_svc.RAZORPAY_WEBHOOK_SECRET
        razorpay_svc.RAZORPAY_WEBHOOK_SECRET = _WEBHOOK_SECRET

    def __exit__(self, *exc):
        razorpay_svc.RAZORPAY_WEBHOOK_SECRET = self._orig


async def _escrow_in_refund_processing(db, counsel_id):
    """A held escrow whose refund Razorpay accepted as 'pending'."""
    await db.users.insert_one({"user_id": counsel_id, "wallet_held_balance": 0})
    context_id = f"hearing_bugc_{uuid.uuid4().hex[:10]}"
    pay_id = f"pay_live_{uuid.uuid4().hex[:10]}"
    doc = await escrow.create_and_hold(
        db, context_type="hearing", context_id=context_id, service_id=hearings.ESCROW_SERVICE_ID,
        matter_id=None, payer_user_id=_user("payer")["user_id"], payee_user_id=counsel_id,
        amount=1500.0, platform_commission_pct=0.2,
        razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=pay_id,
    )
    refund_id = f"rfnd_{uuid.uuid4().hex[:10]}"
    orig = razorpay_svc.refund_payment
    razorpay_svc.refund_payment = lambda pid, amount_inr=None, notes=None: {
        "razorpay_refund_id": refund_id, "status": "pending", "simulated": False}
    try:
        r = await escrow.refund(db, context_type="hearing", context_id=context_id, reason="t")
    finally:
        razorpay_svc.refund_payment = orig
    assert r["status"] == "refund_processing"
    return context_id, doc, pay_id, refund_id


async def _cleanup_bugc(db, context_ids=(), user_ids=(), order_ids=()):
    if context_ids:
        await db.escrow_transactions.delete_many({"context_id": {"$in": list(context_ids)}})
    if user_ids:
        await db.users.delete_many({"user_id": {"$in": list(user_ids)}})
    if order_ids:
        await db.payment_transactions.delete_many({"razorpay_order_id": {"$in": list(order_ids)}})
        await db.audit_log.delete_many({"details.razorpay_order_id": {"$in": list(order_ids)}})


def test_refund_processed_webhook_settles_escrow_and_duplicate_is_noop():
    async def body():
        db = _db()
        counsel = _user("counsel")["user_id"]
        context_id, doc, pay_id, refund_id = await _escrow_in_refund_processing(db, counsel)
        try:
            with _webhook_secret():
                out = await server.razorpay_webhook(_signed_webhook_request(_refund_event("refund.processed", refund_id, pay_id)))
                dup = await server.razorpay_webhook(_signed_webhook_request(_refund_event("refund.processed", refund_id, pay_id)))
            assert out["matched"] == "escrow" and out["status"] == "refunded" and out["changed"] is True
            assert dup["matched"] == "escrow" and dup["changed"] is False
            e = await db.escrow_transactions.find_one({"escrow_id": doc["escrow_id"]}, {"_id": 0})
            assert e["status"] == "refunded" and e["gateway_refund_status"] == "processed" and e["refund_completed_at"]
            u = await db.users.find_one({"user_id": counsel}, {"_id": 0})
            assert u["wallet_held_balance"] == 0  # reversed once (at processing), not again
            assert await db.payment_webhook_events.count_documents({"razorpay_refund_id": refund_id}) == 2
        finally:
            await db.payment_webhook_events.delete_many({"razorpay_refund_id": refund_id})
            await _cleanup_bugc(db, [context_id], [counsel])
    _run_with_server(body())


def test_refund_failed_webhook_marks_escrow_refund_failed_and_never_downgrades_refunded():
    async def body():
        db = _db()
        counsel = _user("counsel")["user_id"]
        context_id, doc, pay_id, refund_id = await _escrow_in_refund_processing(db, counsel)
        try:
            with _webhook_secret():
                out = await server.razorpay_webhook(_signed_webhook_request(
                    _refund_event("refund.failed", refund_id, pay_id, error_description="Bank rejected")))
            assert out["status"] == "refund_failed"
            e = await db.escrow_transactions.find_one({"escrow_id": doc["escrow_id"]}, {"_id": 0})
            assert e["status"] == "refund_failed" and e["refund_last_error"] == "Bank rejected"

            # Now processed arrives (e.g. retried by Razorpay) -> refunded; a later 'failed' must not downgrade it.
            with _webhook_secret():
                await server.razorpay_webhook(_signed_webhook_request(_refund_event("refund.processed", refund_id, pay_id)))
                late = await server.razorpay_webhook(_signed_webhook_request(_refund_event("refund.failed", refund_id, pay_id)))
            assert late["changed"] is False
            e = await db.escrow_transactions.find_one({"escrow_id": doc["escrow_id"]}, {"_id": 0})
            assert e["status"] == "refunded"
        finally:
            await db.payment_webhook_events.delete_many({"razorpay_refund_id": refund_id})
            await _cleanup_bugc(db, [context_id], [counsel])
    _run_with_server(body())


def test_refund_processed_webhook_settles_timed_out_refund_failed_escrow_by_payment_id():
    """The refund call timed out (escrow refund_failed, no refund id stored)
    but Razorpay did create it — the webhook matches by payment id."""
    async def body():
        db = _db()
        counsel = _user("counsel")["user_id"]
        await db.users.insert_one({"user_id": counsel, "wallet_held_balance": 0})
        context_id = f"hearing_bugc_{uuid.uuid4().hex[:10]}"
        pay_id = f"pay_live_{uuid.uuid4().hex[:10]}"
        doc = await escrow.create_and_hold(
            db, context_type="hearing", context_id=context_id, service_id=hearings.ESCROW_SERVICE_ID,
            matter_id=None, payer_user_id=_user("payer")["user_id"], payee_user_id=counsel,
            amount=1500.0, platform_commission_pct=0.2,
            razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=pay_id,
        )
        orig = razorpay_svc.refund_payment

        def _timeout(*a, **k):
            raise TimeoutError("read timed out")
        razorpay_svc.refund_payment = _timeout
        try:
            r = await escrow.refund(db, context_type="hearing", context_id=context_id, reason="t")
            assert r["status"] == "refund_failed"
            with _webhook_secret():
                out = await server.razorpay_webhook(_signed_webhook_request(_refund_event("refund.processed", "rfnd_late", pay_id)))
            assert out["status"] == "refunded"
            e = await db.escrow_transactions.find_one({"escrow_id": doc["escrow_id"]}, {"_id": 0})
            assert e["gateway_refund_id"] == "rfnd_late"
            u = await db.users.find_one({"user_id": counsel}, {"_id": 0})
            assert u["wallet_held_balance"] == 0  # reversed exactly once, here
        finally:
            razorpay_svc.refund_payment = orig
            await db.payment_webhook_events.delete_many({"razorpay_refund_id": "rfnd_late", "razorpay_payment_id": pay_id})
            await _cleanup_bugc(db, [context_id], [counsel])
    _run_with_server(body())


def test_refund_webhook_unknown_refund_and_bad_signature():
    async def body():
        db = _db()
        pay_id = f"pay_unknown_{uuid.uuid4().hex[:10]}"
        try:
            with _webhook_secret():
                out = await server.razorpay_webhook(_signed_webhook_request(_refund_event("refund.processed", "rfnd_nope", pay_id)))
                assert out == {"ok": True, "ignored": "unknown_refund"}
                try:
                    await server.razorpay_webhook(_signed_webhook_request(
                        _refund_event("refund.processed", "rfnd_nope", pay_id), secret="wrong_secret"))
                    raise AssertionError("bad signature must be rejected")
                except server.HTTPException as e:
                    assert e.status_code == 400
        finally:
            await db.payment_webhook_events.delete_many({"razorpay_payment_id": pay_id})
    _run_with_server(body())


async def _orphan_tx(db, refund_status, refund_id=None):
    order_id = f"order_{uuid.uuid4().hex[:12]}"
    pay_id = f"pay_live_{uuid.uuid4().hex[:10]}"
    await db.payment_transactions.insert_one({
        "razorpay_order_id": order_id, "session_id": order_id, "context_type": "hearing", "context_id": "hearing_gone",
        "amount": 1500.0, "currency": "INR", "gateway": "razorpay", "status": "complete", "payment_status": "paid",
        "razorpay_payment_id": pay_id, "orphaned": True, "orphan_reason": "hearing_not_payable:cancelled",
        "orphan_refund_status": refund_status, "orphan_refund_id": refund_id,
        "created_at": "2026-09-23T00:00:00+00:00",
    })
    return order_id, pay_id


def test_orphan_refund_webhook_settles_and_leaves_reconciliation():
    async def body():
        db = _db()
        admin = {"user_id": _user("admin")["user_id"], "role": "admin"}
        order_id, pay_id = await _orphan_tx(db, "pending", "rfnd_orphan_1")
        try:
            report = await server.admin_reconciliation(user=admin, gateway=None, status_filter=None, from_date=None, to_date=None)
            assert [m for m in report["mismatches"] if m.get("session_id") == order_id]  # pending -> flagged

            with _webhook_secret():
                out = await server.razorpay_webhook(_signed_webhook_request(_refund_event("refund.processed", "rfnd_orphan_1", pay_id)))
                dup = await server.razorpay_webhook(_signed_webhook_request(_refund_event("refund.processed", "rfnd_orphan_1", pay_id)))
            assert out["matched"] == "orphan" and out["changed"] is True and dup["changed"] is False
            tx = await db.payment_transactions.find_one({"razorpay_order_id": order_id}, {"_id": 0})
            assert tx["orphan_refund_status"] == "processed" and tx["orphan_refund_settled_at"]

            report = await server.admin_reconciliation(user=admin, gateway=None, status_filter=None, from_date=None, to_date=None)
            assert not [m for m in report["mismatches"] if m.get("session_id") == order_id]  # resolved -> not flagged
        finally:
            await db.payment_webhook_events.delete_many({"razorpay_refund_id": "rfnd_orphan_1"})
            await _cleanup_bugc(db, order_ids=[order_id])
    _run_with_server(body())


def test_orphan_refund_retry_endpoint_is_idempotent_and_race_safe():
    async def body():
        db = _db()
        admin = {"user_id": _user("admin")["user_id"], "role": "admin"}
        non_admin = {"user_id": _user("user")["user_id"], "role": "client"}
        order_id, pay_id = await _orphan_tx(db, "failed")
        order_id2, _ = await _orphan_tx(db, "failed")
        calls = []
        orig = (razorpay_svc.refund_payment, razorpay_svc.fetch_refunds)

        def _refund(pid, amount_inr=None, notes=None):
            calls.append(amount_inr)
            return {"razorpay_refund_id": f"rfnd_retry_{len(calls)}", "status": "processed", "simulated": False}
        razorpay_svc.refund_payment, razorpay_svc.fetch_refunds = _refund, (lambda pid: [])
        try:
            try:
                await server.admin_retry_orphan_refund(order_id, user=non_admin)
                raise AssertionError("non-admin must be refused")
            except server.HTTPException as e:
                assert e.status_code == 403

            out = await server.admin_retry_orphan_refund(order_id, user=admin)
            again = await server.admin_retry_orphan_refund(order_id, user=admin)  # double click
            assert out["orphan_refund_status"] == "processed" and again["orphan_refund_status"] == "processed"
            assert calls == [1500.0]  # exactly one refund

            # Concurrent retries on another orphan -> exactly one gateway refund.
            results = await asyncio.gather(
                server.admin_retry_orphan_refund(order_id2, user=admin),
                server.admin_retry_orphan_refund(order_id2, user=admin),
                return_exceptions=True,
            )
            assert len(calls) == 2
            assert any(not isinstance(r, Exception) and r["orphan_refund_status"] == "processed" for r in results)
            assert all(not isinstance(r, Exception) or (isinstance(r, server.HTTPException) and r.status_code == 409) for r in results)

            # Retry after a timeout where Razorpay already holds the refund -> recorded, no new refund.
            order_id3, pay_id3 = await _orphan_tx(db, "failed")
            razorpay_svc.fetch_refunds = lambda pid: [{"razorpay_refund_id": "rfnd_existing", "amount_inr": 1500.0, "status": "processed"}]
            out3 = await server.admin_retry_orphan_refund(order_id3, user=admin)
            assert out3["orphan_refund_status"] == "processed" and out3["orphan_refund_id"] == "rfnd_existing"
            assert len(calls) == 2
            await _cleanup_bugc(db, order_ids=[order_id3])
        finally:
            razorpay_svc.refund_payment, razorpay_svc.fetch_refunds = orig
            await _cleanup_bugc(db, order_ids=[order_id, order_id2])
    _run_with_server(body())


# ---------- PR #55 hardening ----------

from pymongo import MongoClient as _SyncMongoClient  # noqa: E402


def _sync_db():
    """Synchronous client, used from inside stubbed (synchronous) Razorpay
    calls to simulate a webhook landing while that gateway call is in flight."""
    return _SyncMongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "courtbazaar")]


def test_late_webhook_of_older_refund_never_settles_newer_retry_refund():
    """Refund A fails, admin retry creates refund B (escrow now tracks B).
    A's late webhooks — failed or a (partial) processed — must not touch the
    escrow; B's webhook still settles it."""
    async def body():
        db = _db()
        counsel = _user("counsel")["user_id"]
        context_id, doc, pay_id, refund_a = await _escrow_in_refund_processing(db, counsel)
        refund_b = f"rfnd_b_{uuid.uuid4().hex[:8]}"
        orig = (razorpay_svc.refund_payment, razorpay_svc.fetch_refunds)
        try:
            with _webhook_secret():
                await server.razorpay_webhook(_signed_webhook_request(_refund_event("refund.failed", refund_a, pay_id)))
            e = await db.escrow_transactions.find_one({"escrow_id": doc["escrow_id"]}, {"_id": 0})
            assert e["status"] == "refund_failed" and e["gateway_refund_id"] == refund_a

            razorpay_svc.fetch_refunds = lambda pid: [{"razorpay_refund_id": refund_a, "amount_inr": 1500.0, "status": "failed"}]
            razorpay_svc.refund_payment = lambda pid, amount_inr=None, notes=None: {
                "razorpay_refund_id": refund_b, "status": "pending", "simulated": False}
            r = await escrow.retry_refund(db, doc["escrow_id"], {"user_id": "admin_t"})
            assert r["status"] == "refund_processing" and r["gateway_refund_id"] == refund_b

            with _webhook_secret():
                late_failed = await server.razorpay_webhook(_signed_webhook_request(_refund_event("refund.failed", refund_a, pay_id)))
                late_processed = await server.razorpay_webhook(_signed_webhook_request(
                    _refund_event("refund.processed", refund_a, pay_id, amount_inr=500.0)))
            for late in (late_failed, late_processed):
                assert late["matched"] == "escrow" and late["changed"] is False and late["stale"] is True
            e = await db.escrow_transactions.find_one({"escrow_id": doc["escrow_id"]}, {"_id": 0})
            assert e["status"] == "refund_processing" and e["gateway_refund_id"] == refund_b  # untouched
            assert e["refund_needs_review"] is True  # A's (partial) refund was processed -> admin review
            assert {"refund_id": refund_a, "status": "processed", "attempt": None} in e["stale_refund_events"]

            with _webhook_secret():
                out = await server.razorpay_webhook(_signed_webhook_request(_refund_event("refund.processed", refund_b, pay_id)))
            assert out["matched"] == "escrow" and out["status"] == "refunded" and out["changed"] is True
            e = await db.escrow_transactions.find_one({"escrow_id": doc["escrow_id"]}, {"_id": 0})
            assert e["status"] == "refunded" and e["gateway_refund_id"] == refund_b
            u = await db.users.find_one({"user_id": counsel}, {"_id": 0})
            assert u["wallet_held_balance"] == 0
        finally:
            razorpay_svc.refund_payment, razorpay_svc.fetch_refunds = orig
            await db.payment_webhook_events.delete_many({"razorpay_refund_id": {"$in": [refund_a, refund_b]}})
            await _cleanup_bugc(db, [context_id], [counsel])
    _run_with_server(body())


def test_late_webhook_of_older_orphan_refund_never_settles_newer_one():
    async def body():
        db = _db()
        order_id, pay_id = await _orphan_tx(db, "pending", "rfnd_orphan_B")
        try:
            with _webhook_secret():
                late = await server.razorpay_webhook(_signed_webhook_request(_refund_event("refund.processed", "rfnd_orphan_A", pay_id)))
            assert late["matched"] == "orphan" and late["changed"] is False and late["stale"] is True
            tx = await db.payment_transactions.find_one({"razorpay_order_id": order_id}, {"_id": 0})
            assert tx["orphan_refund_status"] == "pending" and tx["orphan_refund_id"] == "rfnd_orphan_B"
            assert tx["orphan_refund_needs_review"] is True

            with _webhook_secret():
                out = await server.razorpay_webhook(_signed_webhook_request(_refund_event("refund.processed", "rfnd_orphan_B", pay_id)))
            assert out["matched"] == "orphan" and out["changed"] is True
            tx = await db.payment_transactions.find_one({"razorpay_order_id": order_id}, {"_id": 0})
            assert tx["orphan_refund_status"] == "processed"
        finally:
            await db.payment_webhook_events.delete_many({"razorpay_refund_id": {"$in": ["rfnd_orphan_A", "rfnd_orphan_B"]}})
            await _cleanup_bugc(db, order_ids=[order_id])
    _run_with_server(body())


def test_webhook_arriving_before_refund_id_is_stored_is_replayed_not_lost():
    """Razorpay's webhook for a new refund lands before our refund call
    stored its id: it is logged and ignored at that moment, then replayed as
    soon as the id is stored — the escrow still ends up refunded."""
    async def body():
        db = _db()
        counsel = _user("counsel")["user_id"]
        await db.users.insert_one({"user_id": counsel, "wallet_held_balance": 0})
        context_id = f"hearing_bugc_{uuid.uuid4().hex[:10]}"
        pay_id = f"pay_live_{uuid.uuid4().hex[:10]}"
        refund_id = f"rfnd_early_{uuid.uuid4().hex[:8]}"
        doc = await escrow.create_and_hold(
            db, context_type="hearing", context_id=context_id, service_id=hearings.ESCROW_SERVICE_ID,
            matter_id=None, payer_user_id=_user("payer")["user_id"], payee_user_id=counsel,
            amount=1500.0, platform_commission_pct=0.2,
            razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=pay_id,
        )
        orig = razorpay_svc.refund_payment
        try:
            # Simulate the ordering: gateway call starts (escrow refund_pending,
            # no refund id yet) and Razorpay's processed webhook for it arrives.
            def _refund(pid, amount_inr=None, notes=None):
                sdb = _sync_db()
                sdb.payment_webhook_events.insert_one({
                    "razorpay_payment_id": pay_id, "razorpay_refund_id": refund_id,
                    "event": "refund.processed", "received_at": "2026-09-24T00:00:00+00:00"})
                return {"razorpay_refund_id": refund_id, "status": "pending", "simulated": False}
            razorpay_svc.refund_payment = _refund
            r = await escrow.refund(db, context_type="hearing", context_id=context_id, reason="t")
            assert r["status"] == "refunded"
            e = await db.escrow_transactions.find_one({"escrow_id": doc["escrow_id"]}, {"_id": 0})
            assert e["status"] == "refunded" and e["gateway_refund_id"] == refund_id
            u = await db.users.find_one({"user_id": counsel}, {"_id": 0})
            assert u["wallet_held_balance"] == 0  # reversed exactly once
        finally:
            razorpay_svc.refund_payment = orig
            await db.payment_webhook_events.delete_many({"razorpay_refund_id": refund_id})
            await _cleanup_bugc(db, [context_id], [counsel])
    _run_with_server(body())


def test_retry_reports_real_status_when_webhook_settles_during_the_call():
    """Escrow and orphan retries: a webhook settles the record while the
    retry's gateway call is in flight -> the retry returns the stored status,
    not its own (stale) attempt outcome, and never downgrades it."""
    async def body():
        db = _db()
        counsel = _user("counsel")["user_id"]
        await db.users.insert_one({"user_id": counsel, "wallet_held_balance": 0})
        context_id = f"hearing_bugc_{uuid.uuid4().hex[:10]}"
        pay_id = f"pay_live_{uuid.uuid4().hex[:10]}"
        doc = await escrow.create_and_hold(
            db, context_type="hearing", context_id=context_id, service_id=hearings.ESCROW_SERVICE_ID,
            matter_id=None, payer_user_id=_user("payer")["user_id"], payee_user_id=counsel,
            amount=1500.0, platform_commission_pct=0.2,
            razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=pay_id,
        )
        order_id, orphan_pay = await _orphan_tx(db, "failed")
        orig = (razorpay_svc.refund_payment, razorpay_svc.fetch_refunds)
        try:
            def _timeout(*a, **k):
                raise TimeoutError("read timed out")
            razorpay_svc.refund_payment = _timeout
            r = await escrow.refund(db, context_type="hearing", context_id=context_id, reason="t")
            assert r["status"] == "refund_failed"

            razorpay_svc.fetch_refunds = lambda pid: []

            def _escrow_settled_mid_call(pid, amount_inr=None, notes=None):
                _sync_db().escrow_transactions.update_one(
                    {"escrow_id": doc["escrow_id"]}, {"$set": {"status": "refunded", "gateway_refund_id": "rfnd_hook"}})
                return {"razorpay_refund_id": "rfnd_new", "status": "failed", "simulated": False}
            razorpay_svc.refund_payment = _escrow_settled_mid_call
            out = await escrow.retry_refund(db, doc["escrow_id"], {"user_id": "admin_t"})
            assert out["status"] == "refunded" and out.get("refund_settled_elsewhere") is True
            e = await db.escrow_transactions.find_one({"escrow_id": doc["escrow_id"]}, {"_id": 0})
            assert e["status"] == "refunded" and e["gateway_refund_id"] == "rfnd_hook"  # not overwritten
            assert not [t for t in e.get("timeline", []) if t.get("status") == "refund_failed" and "admin_t" in str(t.get("by"))]

            def _orphan_settled_mid_call(pid, amount_inr=None, notes=None):
                _sync_db().payment_transactions.update_one(
                    {"razorpay_order_id": order_id}, {"$set": {"orphan_refund_status": "processed", "orphan_refund_id": "rfnd_hook_o"}})
                return {"razorpay_refund_id": "rfnd_new_o", "status": "failed", "simulated": False}
            razorpay_svc.refund_payment = _orphan_settled_mid_call
            out = await server.admin_retry_orphan_refund(order_id, user={"user_id": "admin_t", "role": "admin"})
            assert out["orphan_refund_status"] == "processed" and out.get("refund_settled_elsewhere") is True
            tx = await db.payment_transactions.find_one({"razorpay_order_id": order_id}, {"_id": 0})
            assert tx["orphan_refund_status"] == "processed" and tx["orphan_refund_id"] == "rfnd_hook_o"
        finally:
            razorpay_svc.refund_payment, razorpay_svc.fetch_refunds = orig
            await _cleanup_bugc(db, [context_id], [counsel], order_ids=[order_id])
    _run_with_server(body())


def test_reconciliation_orphans_excluded_from_paid_totals_and_retryable():
    """Deterministic: both rows get one unique created_at and the report is
    filtered to exactly that instant, so the totals cover only these two
    transactions regardless of what else the test DB holds."""
    async def body():
        db = _db()
        admin = {"user_id": _user("admin")["user_id"], "role": "admin"}
        stamp = f"9998-01-01T00:00:00.{uuid.uuid4().int % 1000000:06d}+00:00"
        order_id, pay_id = await _orphan_tx(db, "failed")
        paid_order = f"order_{uuid.uuid4().hex[:12]}"
        await db.payment_transactions.insert_one({
            "razorpay_order_id": paid_order, "session_id": paid_order, "context_type": "hearing", "context_id": "hearing_ok",
            "amount": 700.0, "currency": "INR", "gateway": "razorpay", "status": "complete", "payment_status": "paid",
        })
        await db.payment_transactions.update_many({"razorpay_order_id": {"$in": [order_id, paid_order]}},
                                                  {"$set": {"created_at": stamp}})
        try:
            report = await server.admin_reconciliation(user=admin, gateway="razorpay", status_filter=None,
                                                       from_date=stamp, to_date=stamp)
            t = report["totals"]["razorpay"]
            assert t["paid"] == 1 and t["paid_amount"] == 700.0          # only the real payment
            assert t["orphaned"] == 1 and t["orphaned_amount"] == 1500.0  # refunded/owed money, not revenue
            assert report["totals"]["grand_total_paid"] == 700.0
            assert report["totals"]["transaction_count"] == 2

            m = [x for x in report["mismatches"] if x.get("razorpay_order_id") == order_id]
            assert len(m) == 1 and m[0]["orphaned"] is True
            assert m[0]["orphan_refund_status"] == "failed" and m[0]["amount"] == 1500.0
            rows = {r["razorpay_order_id"]: r for r in report["rows"]}
            assert rows[order_id]["orphaned"] is True and rows[order_id]["mismatch"] is True
            assert rows[paid_order]["orphaned"] is False and rows[paid_order]["mismatch"] is False

            csv_resp = await server.admin_reconciliation_csv(user=admin)
            lines = csv_resp.body.decode().splitlines()
            assert lines[0].endswith(",orphaned,orphan_refund_status")
            assert [ln for ln in lines if ln.startswith(order_id + ",")][0].endswith(",True,failed")
            assert [ln for ln in lines if ln.startswith(paid_order + ",")][0].endswith(",False,")
        finally:
            await _cleanup_bugc(db, order_ids=[order_id, paid_order])
    _run_with_server(body())


# ---------- Timeout -> admin retry -> late webhook of the timed-out refund ----------

import threading  # noqa: E402


def _deliver_refund_webhook_now(entity: dict, event: str) -> dict:
    """Process a refund webhook synchronously from inside a (synchronous)
    stubbed Razorpay call — i.e. while a retry is genuinely in flight — on
    its own thread, event loop and DB client."""
    out = {}

    def _run():
        async def _go():
            client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            wdb = client[os.environ.get("DB_NAME", "courtbazaar")]
            out["result"] = await payment_reconciliation.apply_refund_event(wdb, entity, event)
        asyncio.run(_go())
    t = threading.Thread(target=_run)
    t.start()
    t.join()
    return out["result"]


def test_timed_out_refund_late_webhook_never_settles_retry_refund():
    """1) Refund A times out (no id stored). 2) Admin retry claims attempt 2
    and — while its Razorpay call is in flight — A's refund.processed webhook
    arrives. 3) Retry creates refund B. 4) A's webhook arrives again later.
    A must never settle/overwrite B (with or without attribution notes); it
    is recorded and flagged for review. B's own webhook settles B; the payee
    hold is reversed exactly once."""
    async def body():
        db = _db()
        counsel = _user("counsel")["user_id"]
        await db.users.insert_one({"user_id": counsel, "wallet_held_balance": 0})
        context_id = f"hearing_race_{uuid.uuid4().hex[:10]}"
        pay_id = f"pay_live_{uuid.uuid4().hex[:10]}"
        refund_a, refund_b = f"rfnd_a_{uuid.uuid4().hex[:8]}", f"rfnd_b_{uuid.uuid4().hex[:8]}"
        doc = await escrow.create_and_hold(
            db, context_type="hearing", context_id=context_id, service_id=hearings.ESCROW_SERVICE_ID,
            matter_id=None, payer_user_id=_user("payer")["user_id"], payee_user_id=counsel,
            amount=1500.0, platform_commission_pct=0.2,
            razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=pay_id,
        )
        sent_notes = []
        orig = (razorpay_svc.refund_payment, razorpay_svc.fetch_refunds)
        try:
            # 1) Refund A: Razorpay created it, but our call timed out.
            def _timeout(pid, amount_inr=None, notes=None):
                sent_notes.append(notes)
                raise TimeoutError("read timed out")
            razorpay_svc.refund_payment = _timeout
            r = await escrow.refund(db, context_type="hearing", context_id=context_id, reason="t")
            assert r["status"] == "refund_failed" and not r.get("gateway_refund_id")
            notes_a = sent_notes[0]
            assert notes_a["escrow_id"] == doc["escrow_id"] and notes_a["refund_attempt"] == 1

            entity_a = {"id": refund_a, "payment_id": pay_id, "amount": 150000, "status": "processed", "notes": notes_a}
            legacy_a = {"id": refund_a, "payment_id": pay_id, "amount": 150000, "status": "processed"}  # no notes

            # 2)+3) Admin retry; A's webhooks land while the retry is in flight.
            in_flight = {}

            def _lookup_with_late_webhook(pid):
                e = _sync_db().escrow_transactions.find_one({"escrow_id": doc["escrow_id"]}, {"_id": 0})
                in_flight["state"] = (e["status"], e.get("gateway_refund_id"), e.get("refund_attempts"))
                in_flight["with_notes"] = _deliver_refund_webhook_now(entity_a, "refund.processed")
                in_flight["legacy"] = _deliver_refund_webhook_now(legacy_a, "refund.processed")
                return []  # A not visible at Razorpay yet

            def _refund_b(pid, amount_inr=None, notes=None):
                sent_notes.append(notes)
                return {"razorpay_refund_id": refund_b, "status": "pending", "simulated": False}
            razorpay_svc.fetch_refunds, razorpay_svc.refund_payment = _lookup_with_late_webhook, _refund_b
            out = await escrow.retry_refund(db, doc["escrow_id"], {"user_id": "admin_t"})

            assert in_flight["state"] == ("refund_pending", None, 2)  # the exact in-flight window
            for res in (in_flight["with_notes"], in_flight["legacy"]):
                assert res["matched"] == "escrow" and res["changed"] is False and res["stale"] is True
            assert out["status"] == "refund_processing" and out["gateway_refund_id"] == refund_b
            assert sent_notes[1]["refund_attempt"] == 2

            e = await db.escrow_transactions.find_one({"escrow_id": doc["escrow_id"]}, {"_id": 0})
            assert e["status"] == "refund_processing" and e["gateway_refund_id"] == refund_b
            assert e["refund_needs_review"] is True
            assert {"refund_id": refund_a, "status": "processed", "attempt": 1} in e["stale_refund_events"]

            # 4) A's webhook again after B is stored (duplicate delivery) -> still nothing.
            with _webhook_secret():
                again = await server.razorpay_webhook(_signed_webhook_request({
                    "event": "refund.processed", "payload": {"refund": {"entity": entity_a}}}))
            assert again["changed"] is False and again["stale"] is True
            e2 = await db.escrow_transactions.find_one({"escrow_id": doc["escrow_id"]}, {"_id": 0})
            assert e2["status"] == "refund_processing" and e2["gateway_refund_id"] == refund_b
            assert len(e2["stale_refund_events"]) == len(e["stale_refund_events"])  # idempotent record

            # B's own webhook settles B.
            entity_b = {"id": refund_b, "payment_id": pay_id, "amount": 150000, "status": "processed", "notes": sent_notes[1]}
            with _webhook_secret():
                done = await server.razorpay_webhook(_signed_webhook_request({
                    "event": "refund.processed", "payload": {"refund": {"entity": entity_b}}}))
            assert done["matched"] == "escrow" and done["status"] == "refunded" and done["changed"] is True
            u = await db.users.find_one({"user_id": counsel}, {"_id": 0})
            assert u["wallet_held_balance"] == 0  # reversed once

            # Reconciliation keeps it visible for review even though it is refunded.
            report = await server.admin_reconciliation(user={"user_id": "admin_t", "role": "admin"},
                                                       gateway=None, status_filter=None, from_date=None, to_date=None)
            m = [x for x in report["mismatches"] if x.get("escrow_id") == doc["escrow_id"]]
            assert len(m) == 1 and m[0]["refund_needs_review"] is True and refund_a in m[0]["reason"]
        finally:
            razorpay_svc.refund_payment, razorpay_svc.fetch_refunds = orig
            await db.payment_webhook_events.delete_many({"razorpay_refund_id": {"$in": [refund_a, refund_b]}})
            await _cleanup_bugc(db, [context_id], [counsel])
    _run_with_server(body())


def test_timed_out_orphan_refund_late_webhook_never_settles_retry_refund():
    async def body():
        db = _db()
        order_id, pay_id = await _orphan_tx(db, "failed", None)
        stamp = f"9998-02-01T00:00:00.{uuid.uuid4().int % 1000000:06d}+00:00"  # deterministic reconciliation window
        await db.payment_transactions.update_one({"razorpay_order_id": order_id},
                                                 {"$set": {"orphan_refund_attempts": 1, "created_at": stamp}})
        entity_a = {"id": "rfnd_orph_a", "payment_id": pay_id, "amount": 150000, "status": "processed",
                    "notes": {"razorpay_order_id": order_id, "orphan_refund_attempt": 1}}
        sent_notes, in_flight = [], {}
        orig = (razorpay_svc.refund_payment, razorpay_svc.fetch_refunds)
        try:
            def _lookup_with_late_webhook(pid):
                in_flight["result"] = _deliver_refund_webhook_now(entity_a, "refund.processed")
                return []

            def _refund_b(pid, amount_inr=None, notes=None):
                sent_notes.append(notes)
                return {"razorpay_refund_id": "rfnd_orph_b", "status": "pending", "simulated": False}
            razorpay_svc.fetch_refunds, razorpay_svc.refund_payment = _lookup_with_late_webhook, _refund_b
            out = await payment_reconciliation.retry_orphan_refund(db, order_id, {"user_id": "admin_t"})

            assert in_flight["result"]["stale"] is True and in_flight["result"]["changed"] is False
            assert sent_notes[0]["orphan_refund_attempt"] == 2
            assert out["orphan_refund_status"] == "pending" and out["orphan_refund_id"] == "rfnd_orph_b"
            tx = await db.payment_transactions.find_one({"razorpay_order_id": order_id}, {"_id": 0})
            assert tx["orphan_refund_status"] == "pending" and tx["orphan_refund_id"] == "rfnd_orph_b"
            assert tx["orphan_refund_needs_review"] is True

            entity_b = {"id": "rfnd_orph_b", "payment_id": pay_id, "status": "processed", "notes": sent_notes[0]}
            res = await payment_reconciliation.apply_refund_event(db, entity_b, "refund.processed")
            assert res["matched"] == "orphan" and res["changed"] is True
            tx = await db.payment_transactions.find_one({"razorpay_order_id": order_id}, {"_id": 0})
            assert tx["orphan_refund_status"] == "processed" and tx["orphan_refund_id"] == "rfnd_orph_b"

            report = await server.admin_reconciliation(user={"user_id": "admin_t", "role": "admin"},
                                                       gateway=None, status_filter=None, from_date=stamp, to_date=stamp)
            m = [x for x in report["mismatches"] if x.get("razorpay_order_id") == order_id]
            assert len(m) == 1 and "REVIEW" in m[0]["reason"]  # processed, but flagged for duplicate check
        finally:
            razorpay_svc.refund_payment, razorpay_svc.fetch_refunds = orig
            await _cleanup_bugc(db, order_ids=[order_id])
    _run_with_server(body())
