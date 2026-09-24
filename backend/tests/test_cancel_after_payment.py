"""B6 — cancel after payment (hearings.cancel_hearing_request).

Founder decision: the commercial lock (fee agreed via negotiation or
Accept-at-listed-rate) only blocks cancelling BEFORE payment. Once the fee is
paid and held in escrow, the requester (or an admin) may cancel and is
refunded through the existing escrow.refund() path — never a new refund
implementation.

Same convention as test_negotiation.py / test_razorpay_live_mode.py: drives
hearings/negotiation/escrow/payment_reconciliation directly via Motor with
plain asyncio.run() wrappers, no HTTP layer. Payments go through the real
capture path (payment_reconciliation.finalize_hearing_payment); the Razorpay
refund call is replaced by a counting stub, so no network call is made and
"refund exactly once" is asserted on the gateway call itself.
"""
import asyncio
import os
import sys
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import escrow  # noqa: E402
import hearings  # noqa: E402
import negotiation  # noqa: E402
import payment_reconciliation  # noqa: E402
import razorpay_svc  # noqa: E402
from fastapi import HTTPException  # noqa: E402

PAID_FEE = 3000.0


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _user(prefix, **extra):
    return {"user_id": f"test_b6_{prefix}_{uuid.uuid4().hex[:10]}", **extra}


async def _noop_notify(*_args, **_kwargs):
    return None


class _refund_stub:
    """Replace razorpay_svc.refund_payment/fetch_refunds with a counting stub
    (no network). `status` is what the fake gateway reports for the refund."""

    def __init__(self, status="pending"):
        self.status = status
        self.calls = []

    def __enter__(self):
        self._orig = (razorpay_svc.refund_payment, razorpay_svc.fetch_refunds)

        def _refund(payment_id, amount_inr=None, notes=None):
            self.calls.append({"payment_id": payment_id, "amount_inr": amount_inr, "notes": notes})
            return {"razorpay_refund_id": f"rfnd_b6_{uuid.uuid4().hex[:10]}", "status": self.status, "simulated": False}
        razorpay_svc.refund_payment = _refund
        razorpay_svc.fetch_refunds = lambda payment_id: []
        return self

    def __exit__(self, *exc):
        razorpay_svc.refund_payment, razorpay_svc.fetch_refunds = self._orig


class _Fixture:
    def __init__(self):
        self.requester = _user("requester")
        self.counsel = _user("counsel", capabilities=["can_practice_proxy_counsel"])
        self.hearing_ids = []
        self.order_ids = []

    async def setup_users(self, db):
        await db.users.insert_one({"user_id": self.counsel["user_id"], "wallet_held_balance": 0.0})
        await db.proxy_counsel_profiles.insert_one({"user_id": self.counsel["user_id"], "negotiation_enabled": True})

    async def locked_hearing(self, db):
        """Targeted hearing with a fee agreed through real negotiation —
        status "requested", commercially_locked True, nothing paid."""
        hearing = await hearings.create_hearing_request(
            db, self.requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            target_advocate_id=self.counsel["user_id"],
        )
        hearing_id = hearing["hearing_id"]
        self.hearing_ids.append(hearing_id)
        await negotiation.propose_offer(db, hearing_id, self.requester, PAID_FEE, None)
        offer_id = (await negotiation.get_negotiation(db, hearing_id))["current_offer_id"]
        await negotiation.accept_offer(db, hearing_id, offer_id, self.counsel)
        locked = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
        assert locked["commercially_locked"] is True and locked["status"] == "requested"
        return hearing_id

    async def awaiting_payment(self, db):
        """Locked hearing moved to payment_pending with a pending Razorpay
        order row — the real precondition for a capture."""
        hearing_id = await self.locked_hearing(db)
        await hearings.initiate_payment(db, hearing_id, self.requester)
        order_id = f"order_b6_{uuid.uuid4().hex[:10]}"
        self.order_ids.append(order_id)
        await db.payment_transactions.insert_one({
            "razorpay_order_id": order_id, "context_type": "hearing", "context_id": hearing_id,
            "user_id": self.requester["user_id"], "amount": PAID_FEE, "currency": "INR", "gateway": "razorpay",
            "status": "initiated", "payment_status": "pending", "simulated": False,
        })
        hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
        tx = await db.payment_transactions.find_one({"razorpay_order_id": order_id}, {"_id": 0})
        return hearing, tx

    async def capture(self, db, hearing, tx, payment_id=None):
        return await payment_reconciliation.finalize_hearing_payment(
            db, hearing, tx, payment_id or f"pay_b6_{uuid.uuid4().hex[:10]}",
            platform_commission_pct=0.2, notify_hearing_event=_noop_notify,
        )

    async def paid_locked_hearing(self, db, accepted=False):
        """Locked hearing paid through the real capture path -> "broadcast"
        (escrow held, payee deferred). accepted=True also has the targeted
        counsel accept -> "documents_shared" with the payee assigned."""
        hearing, tx = await self.awaiting_payment(db)
        assert await self.capture(db, hearing, tx) is True
        hearing_id = hearing["hearing_id"]
        if accepted:
            await hearings.accept_hearing_request(db, hearing_id, self.counsel)
        paid = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
        assert paid["commercially_locked"] is True
        assert paid["status"] == ("documents_shared" if accepted else "broadcast")
        return hearing_id

    async def cleanup(self, db):
        ids = list(self.hearing_ids)
        if ids:
            await db.hearing_requests.delete_many({"hearing_id": {"$in": ids}})
            await db.escrow_transactions.delete_many({"context_id": {"$in": ids}})
            await db.payment_transactions.delete_many({"context_id": {"$in": ids}})
            await db.negotiations.delete_many({"hearing_id": {"$in": ids}})
            await db.notification_events.delete_many({"related_entity_id": {"$in": ids}})
            await db.audit_log.delete_many({"details.context_id": {"$in": ids}})
            await db.audit_log.delete_many({"details.hearing_id": {"$in": ids}})
        if self.order_ids:
            await db.audit_log.delete_many({"details.razorpay_order_id": {"$in": self.order_ids}})
        await db.users.delete_many({"user_id": self.counsel["user_id"]})
        await db.proxy_counsel_profiles.delete_many({"user_id": self.counsel["user_id"]})


async def _escrow(db, hearing_id):
    return await db.escrow_transactions.find_one({"context_type": "hearing", "context_id": hearing_id}, {"_id": 0})


async def _hearing(db, hearing_id):
    return await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})


# ---------- TEST 1: paid + locked -> client can cancel, refunded once ----------

def test_client_cancels_paid_locked_hearing_and_escrow_refund_is_initiated():
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing_id = await fx.paid_locked_hearing(db)
            with _refund_stub(status="pending") as refunds:
                result = await hearings.cancel_hearing_request(db, hearing_id, fx.requester)
            assert result == {"ok": True, "refund_status": "refund_processing"}

            hearing = await _hearing(db, hearing_id)
            assert hearing["status"] == "cancelled"
            assert hearing["commercially_locked"] is True  # the lock itself is untouched

            # Refund went through the existing escrow.refund() exactly once.
            assert len(refunds.calls) == 1
            assert refunds.calls[0]["amount_inr"] == PAID_FEE
            assert refunds.calls[0]["notes"]["context_id"] == hearing_id
            esc = await _escrow(db, hearing_id)
            assert esc["status"] == "refund_processing"
            assert esc["refund_attempts"] == 1
            assert esc["refund_reason"] == "Hearing cancelled after payment was held"
            assert esc["gateway_refund_id"].startswith("rfnd_b6_")
            notes = [t.get("note", "") for t in hearing["timeline"]]
            assert any(n.startswith("Refund initiated, awaiting bank processing") for n in notes)
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


def test_cancel_after_counsel_accepted_refunds_and_reverses_payee_hold_once():
    """documents_shared: the counsel is assigned as payee, so the escrow's
    payee hold was credited to their wallet_held_balance — a processed
    refund must reverse it exactly once."""
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing_id = await fx.paid_locked_hearing(db, accepted=True)
            esc = await _escrow(db, hearing_id)
            payee = await db.users.find_one({"user_id": fx.counsel["user_id"]})
            assert esc["payee_user_id"] == fx.counsel["user_id"]
            assert payee["wallet_held_balance"] == esc["payee_amount"]

            with _refund_stub(status="processed") as refunds:
                result = await hearings.cancel_hearing_request(db, hearing_id, fx.requester)
                # A retry after completion must neither refund again nor reverse the hold twice.
                again = await escrow.retry_refund(db, esc["escrow_id"], {"user_id": "test_b6_admin"})
            assert result == {"ok": True, "refund_status": "refunded"}
            assert again["status"] == "refunded"
            assert len(refunds.calls) == 1
            assert (await _hearing(db, hearing_id))["status"] == "cancelled"
            esc = await _escrow(db, hearing_id)
            assert esc["status"] == "refunded" and esc["payee_hold_reversed"] is True
            payee = await db.users.find_one({"user_id": fx.counsel["user_id"]})
            assert payee["wallet_held_balance"] == 0
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


# ---------- TEST 2: unpaid + locked -> still refused, nothing changes ----------

@pytest.mark.parametrize("stage", ["requested", "payment_pending"])
def test_unpaid_locked_hearing_cancel_still_refused(stage):
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            if stage == "requested":
                hearing_id = await fx.locked_hearing(db)
            else:
                hearing_id = (await fx.awaiting_payment(db))[0]["hearing_id"]
            before = await _hearing(db, hearing_id)
            assert before["status"] == stage

            with _refund_stub() as refunds:
                with pytest.raises(HTTPException) as exc_info:
                    await hearings.cancel_hearing_request(db, hearing_id, fx.requester)
            assert exc_info.value.status_code == 400
            assert "Proceed to payment" in exc_info.value.detail  # unchanged pre-payment message

            after = await _hearing(db, hearing_id)
            assert after["status"] == stage
            assert after["commercially_locked"] is True
            assert after["timeline"] == before["timeline"]
            assert await _escrow(db, hearing_id) is None
            assert refunds.calls == []
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


# ---------- TEST 3: admin can cancel a paid locked hearing ----------

def test_admin_can_cancel_paid_locked_hearing():
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing_id = await fx.paid_locked_hearing(db)
            admin = {"user_id": _user("admin")["user_id"], "role": "admin"}
            with _refund_stub(status="processed") as refunds:
                result = await hearings.cancel_hearing_request(db, hearing_id, admin)
            assert result == {"ok": True, "refund_status": "refunded"}
            assert (await _hearing(db, hearing_id))["status"] == "cancelled"
            assert (await _escrow(db, hearing_id))["status"] == "refunded"
            assert len(refunds.calls) == 1
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


def test_non_requester_non_admin_cannot_cancel_paid_locked_hearing():
    """Opening the post-payment path must not widen who may cancel — the
    targeted counsel (a participant, but not the requester) still gets 403."""
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing_id = await fx.paid_locked_hearing(db, accepted=True)
            with _refund_stub() as refunds:
                for actor in (fx.counsel, {"user_id": _user("stranger")["user_id"], "role": "client"}):
                    with pytest.raises(HTTPException) as exc_info:
                        await hearings.cancel_hearing_request(db, hearing_id, actor)
                    assert exc_info.value.status_code == 403
            assert (await _hearing(db, hearing_id))["status"] == "documents_shared"
            assert (await _escrow(db, hearing_id))["status"] == "held"
            assert refunds.calls == []
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


# ---------- TEST 4: double cancellation -> second rejected, one refund ----------

def test_second_cancel_is_rejected_and_never_refunds_twice():
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing_id = await fx.paid_locked_hearing(db)
            with _refund_stub(status="pending") as refunds:
                await hearings.cancel_hearing_request(db, hearing_id, fx.requester)
                with pytest.raises(HTTPException) as exc_info:
                    await hearings.cancel_hearing_request(db, hearing_id, fx.requester)
            assert exc_info.value.status_code == 400
            assert len(refunds.calls) == 1
            assert (await _escrow(db, hearing_id))["refund_attempts"] == 1
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


def test_concurrent_cancels_only_one_wins_and_refunds_once():
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing_id = await fx.paid_locked_hearing(db)
            with _refund_stub(status="pending") as refunds:
                results = await asyncio.gather(
                    *[hearings.cancel_hearing_request(db, hearing_id, fx.requester) for _ in range(3)],
                    return_exceptions=True,
                )
            wins = [r for r in results if isinstance(r, dict)]
            losses = [r for r in results if isinstance(r, HTTPException)]
            assert len(wins) == 1 and len(losses) == 2, results
            assert all(e.status_code in (400, 409) for e in losses)
            assert len(refunds.calls) == 1
            esc = await _escrow(db, hearing_id)
            assert esc["refund_attempts"] == 1 and esc["status"] == "refund_processing"
            assert (await _hearing(db, hearing_id))["status"] == "cancelled"
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


# ---------- TEST 5: negotiation stays closed ----------

def test_end_negotiation_and_counsel_reject_still_refused_on_paid_locked_hearing():
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing_id = await fx.paid_locked_hearing(db)
            with pytest.raises(HTTPException) as exc_info:
                await hearings.end_negotiation(db, hearing_id, fx.requester)
            assert exc_info.value.status_code == 400
            with pytest.raises(HTTPException) as exc_info:
                await hearings.reject_hearing_request(db, hearing_id, fx.counsel)
            assert exc_info.value.status_code == 400
            hearing = await _hearing(db, hearing_id)
            assert hearing["status"] == "broadcast"
            assert (await _escrow(db, hearing_id))["status"] == "held"
            assert (await negotiation.get_negotiation(db, hearing_id))["status"] == "agreed"
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


def test_cancelled_paid_hearing_cannot_reopen_negotiation():
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing_id = await fx.paid_locked_hearing(db)
            with _refund_stub():
                await hearings.cancel_hearing_request(db, hearing_id, fx.requester)
            for actor in (fx.requester, fx.counsel):
                with pytest.raises(HTTPException) as exc_info:
                    await negotiation.propose_offer(db, hearing_id, actor, 2500.0, "reopen?")
                assert exc_info.value.status_code == 400
            neg = await negotiation.get_negotiation(db, hearing_id)
            assert neg["status"] == "agreed" and neg["locked_amount"] == PAID_FEE
            assert len(neg["offers"]) == 1
            with pytest.raises(HTTPException):
                await hearings.initiate_payment(db, hearing_id, fx.requester)
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


# ---------- TEST 6: payment confirmation vs cancellation race ----------

async def _assert_consistent(db, hearing_id, refunds, order_id):
    """Whatever the interleaving, the end state must be one of exactly two
    coherent outcomes, with no duplicate escrow or refund."""
    hearing = await _hearing(db, hearing_id)
    assert await db.escrow_transactions.count_documents({"context_type": "hearing", "context_id": hearing_id}) <= 1
    esc = await _escrow(db, hearing_id)
    tx = await db.payment_transactions.find_one({"razorpay_order_id": order_id}, {"_id": 0})
    assert tx["payment_status"] == "paid"
    assert not tx.get("orphaned")  # the capture always attached; nothing orphaned
    if hearing["status"] == "broadcast":
        # Cancel lost (pre-payment lock / claim guard); payment stands.
        assert esc["status"] == "held"
        assert refunds.calls == []
    elif hearing["status"] == "cancelled":
        # Payment confirmed first, then the post-payment cancel refunded it.
        assert esc["status"] in ("refund_processing", "refunded")
        assert esc["refund_attempts"] == 1
        assert len(refunds.calls) == 1
    else:
        raise AssertionError(f"inconsistent end state: {hearing['status']}")
    return hearing["status"]


def test_payment_confirmation_and_cancel_racing_never_duplicate_escrow_or_refund():
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        outcomes = []
        try:
            for _ in range(8):
                hearing, tx = await fx.awaiting_payment(db)
                with _refund_stub(status="pending") as refunds:
                    capture, cancel = await asyncio.gather(
                        fx.capture(db, hearing, tx),
                        hearings.cancel_hearing_request(db, hearing["hearing_id"], fx.requester),
                        return_exceptions=True,
                    )
                    assert capture is True
                    if isinstance(cancel, HTTPException):
                        assert cancel.status_code in (400, 409)
                    else:
                        assert cancel["ok"] is True
                    outcomes.append(await _assert_consistent(db, hearing["hearing_id"], refunds, tx["razorpay_order_id"]))
        finally:
            await fx.cleanup(db)
        assert outcomes  # every iteration landed in a coherent state
    asyncio.run(body())


def test_cancel_before_capture_is_refused_then_capture_confirms_payment():
    """Deterministic ordering of the race: the cancel reads payment_pending
    (still pre-payment, still locked) and is refused, so the capture that
    follows attaches normally — no orphan refund, no cancellation."""
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing, tx = await fx.awaiting_payment(db)
            with _refund_stub() as refunds:
                with pytest.raises(HTTPException) as exc_info:
                    await hearings.cancel_hearing_request(db, hearing["hearing_id"], fx.requester)
                assert exc_info.value.status_code == 400
                assert await fx.capture(db, hearing, tx) is True
                assert await _assert_consistent(db, hearing["hearing_id"], refunds, tx["razorpay_order_id"]) == "broadcast"
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


def test_duplicate_capture_after_cancel_refund_does_not_corrupt_state():
    """Capture -> cancel (refund) -> the same capture replayed (duplicate
    webhook / verify retry): the replay is a no-op — no second escrow, no
    second refund, hearing stays cancelled."""
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing, tx = await fx.awaiting_payment(db)
            payment_id = f"pay_b6_{uuid.uuid4().hex[:10]}"
            with _refund_stub(status="pending") as refunds:
                assert await fx.capture(db, hearing, tx, payment_id) is True
                await hearings.cancel_hearing_request(db, hearing["hearing_id"], fx.requester)
                assert await fx.capture(db, hearing, tx, payment_id) is False
                assert await _assert_consistent(db, hearing["hearing_id"], refunds, tx["razorpay_order_id"]) == "cancelled"
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


# ---------- Regression: unlocked (broadcast-to-all) paths unchanged ----------

def test_unlocked_unpaid_cancel_still_works_without_refund():
    async def body():
        db, fx = _db(), _Fixture()
        try:
            hearing = await hearings.create_hearing_request(
                db, fx.requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            )
            fx.hearing_ids.append(hearing["hearing_id"])
            with _refund_stub() as refunds:
                result = await hearings.cancel_hearing_request(db, hearing["hearing_id"], fx.requester)
            assert result == {"ok": True}
            assert (await _hearing(db, hearing["hearing_id"]))["status"] == "cancelled"
            assert refunds.calls == []
        finally:
            await fx.cleanup(db)
    asyncio.run(body())
