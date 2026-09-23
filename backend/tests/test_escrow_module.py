"""Escrow Module (founder's rules 1-9): the Hiring Advocate's one-click
"Verify Hearing" (verify_and_release_payout) and the 3-day order-sheet
reminder scan (check_pending_order_sheets).

Same rationale/pattern as test_hearings_payment_broadcast_reorder.py: plain
asyncio.run() wrappers against a real Mongo instance, no HTTP layer. Test
setup jumps straight to the target hearing.status via a direct db write
where the preceding state-machine chain isn't itself under test (document
upload's auto-chain machinery is exercised by test_hearings_payment_
broadcast_reorder.py and test_negotiation.py already, not duplicated here).
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hearings  # noqa: E402
import escrow  # noqa: E402
import razorpay_svc  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _user(prefix):
    return {"user_id": f"test_escrow_{prefix}_{uuid.uuid4().hex[:10]}"}


async def _hold_escrow(db, hearing_id, requester, fee, payee_user_id):
    return await escrow.create_and_hold(
        db, context_type="hearing", context_id=hearing_id, service_id=hearings.ESCROW_SERVICE_ID,
        matter_id=None, payer_user_id=requester["user_id"], payee_user_id=payee_user_id,
        amount=fee, platform_commission_pct=0.1,
        razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
    )


async def _make_hearing_awaiting_verification(db, requester, counsel, fee=1500.0):
    """Fast-forwards a targeted hearing straight to "verification_pending"
    with escrow already held for this counsel — the state this module's new
    functions actually operate on. The chain to get there (accept ->
    documents_shared -> ... -> hearing_completed -> order sheet upload) is
    already covered by other test files; jumping here via a direct write
    keeps this file focused on verify_and_release_payout/check_pending_
    order_sheets themselves."""
    hearing = await hearings.create_hearing_request(
        db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", fee, None,
        target_advocate_id=counsel["user_id"],
    )
    hearing_id = hearing["hearing_id"]
    await _hold_escrow(db, hearing_id, requester, fee, payee_user_id=counsel["user_id"])
    await db.hearing_requests.update_one(
        {"hearing_id": hearing_id},
        {"$set": {
            "status": "verification_pending", "proxy_counsel_user_id": counsel["user_id"],
            "payment_confirmed_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return hearing_id


async def _cleanup(db, hearing_ids=(), user_ids=()):
    if hearing_ids:
        await db.hearing_requests.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
        await db.escrow_transactions.delete_many({"context_id": {"$in": list(hearing_ids)}})
    if user_ids:
        await db.proxy_counsel_profiles.delete_many({"user_id": {"$in": list(user_ids)}})
        await db.notification_events.delete_many({"user_id": {"$in": list(user_ids)}})
        await db.users.delete_many({"user_id": {"$in": list(user_ids)}})


def test_verify_and_release_payout_happy_path():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = await _make_hearing_awaiting_verification(db, requester, counsel)
        try:
            await db.proxy_counsel_profiles.insert_one({"user_id": counsel["user_id"], "cases_completed": 0})
            result = await hearings.verify_and_release_payout(db, hearing_id, requester)
            assert result["status"] == "completed"
            assert result["escrow"]["status"] == "released"

            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "completed"

            profile = await db.proxy_counsel_profiles.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
            assert profile["cases_completed"] == 1

            escrow_doc = await db.escrow_transactions.find_one({"context_id": hearing_id}, {"_id": 0})
            assert escrow_doc["status"] == "released"
        finally:
            await _cleanup(db, [hearing_id], [counsel["user_id"]])
    asyncio.run(body())


def test_verify_and_release_payout_forbidden_for_non_requester():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = await _make_hearing_awaiting_verification(db, requester, counsel)
        try:
            try:
                await hearings.verify_and_release_payout(db, hearing_id, counsel)
                assert False, "expected HTTPException"
            except HTTPException as e:
                assert e.status_code == 403

            # Nothing should have moved — still awaiting verification, escrow untouched.
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["status"] == "verification_pending"
            escrow_doc = await db.escrow_transactions.find_one({"context_id": hearing_id}, {"_id": 0})
            assert escrow_doc["status"] == "held"
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_verify_and_release_payout_rejected_when_not_awaiting_verification():
    async def body():
        db = _db()
        requester = _user("requester")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            )
            hearing_id = hearing["hearing_id"]  # still "requested" — nowhere near verification
            try:
                await hearings.verify_and_release_payout(db, hearing_id, requester)
                assert False, "expected HTTPException"
            except HTTPException as e:
                assert e.status_code == 400
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_check_pending_order_sheets_notifies_after_three_days():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing = await hearings.create_hearing_request(
            db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            target_advocate_id=counsel["user_id"],
        )
        hearing_id = hearing["hearing_id"]
        try:
            await db.users.insert_one({"user_id": counsel["user_id"], "name": "Test Counsel"})
            stale = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
            await db.hearing_requests.update_one(
                {"hearing_id": hearing_id},
                {"$set": {"status": "hearing_scheduled", "proxy_counsel_user_id": counsel["user_id"], "payment_confirmed_at": stale}},
            )
            count = await hearings.check_pending_order_sheets(db)
            assert count >= 1

            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["order_sheet_reminder_sent_at"] is not None

            event = await db.notification_events.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
            assert event is not None
            # Wording changed in 5b25d4b ("waiting in Escrow" -> "held securely
            # by CourtBazaar"); assert the reminder's current meaning instead.
            assert event["title"] == "Order sheet reminder"
            assert "held securely by CourtBazaar" in event["body"]
            assert "upload the Court Order Sheet" in event["body"]

            # Second scan must not re-notify the same hearing.
            before = event["notification_id"]
            await hearings.check_pending_order_sheets(db)
            events = await db.notification_events.find({"user_id": counsel["user_id"]}, {"_id": 0}).to_list(10)
            assert len(events) == 1
            assert events[0]["notification_id"] == before
        finally:
            await _cleanup(db, [hearing_id], [counsel["user_id"]])
    asyncio.run(body())


def test_check_pending_order_sheets_skips_recent_payment():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing = await hearings.create_hearing_request(
            db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            target_advocate_id=counsel["user_id"],
        )
        hearing_id = hearing["hearing_id"]
        try:
            await db.users.insert_one({"user_id": counsel["user_id"], "name": "Test Counsel"})
            recent = datetime.now(timezone.utc).isoformat()  # paid moments ago, well within the 3-day window
            await db.hearing_requests.update_one(
                {"hearing_id": hearing_id},
                {"$set": {"status": "hearing_scheduled", "proxy_counsel_user_id": counsel["user_id"], "payment_confirmed_at": recent}},
            )
            await hearings.check_pending_order_sheets(db)
            fetched = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert fetched["order_sheet_reminder_sent_at"] is None
            event = await db.notification_events.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
            assert event is None
        finally:
            await _cleanup(db, [hearing_id], [counsel["user_id"]])
    asyncio.run(body())


def test_refund_calls_gateway_exactly_once_under_concurrent_calls():
    """issue #50: StateMachine.apply() only validates in memory and never
    touches the database, so without the "held" -> "refund_pending" atomic
    claim, two concurrent refund() calls (e.g. an admin double-click) could
    both read status "held", both pass validation, and both hit the
    Razorpay refund API. This proves only one ever does."""
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = None
        orig_refund_payment = razorpay_svc.refund_payment
        call_count = {"n": 0}

        def fake_refund_payment(payment_id, amount_inr=None, notes=None):
            call_count["n"] += 1
            return {"razorpay_refund_id": "rfnd_fake_1", "status": "processed", "simulated": False}
        razorpay_svc.refund_payment = fake_refund_payment
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            )
            hearing_id = hearing["hearing_id"]
            # A non-simulated payment id (doesn't start with pay_sim_) so
            # refund() actually reaches the (mocked) gateway call.
            await escrow.create_and_hold(
                db, context_type="hearing", context_id=hearing_id, service_id=hearings.ESCROW_SERVICE_ID,
                matter_id=None, payer_user_id=requester["user_id"], payee_user_id=counsel["user_id"],
                amount=1500.0, platform_commission_pct=0.1,
                razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=f"pay_live_{uuid.uuid4().hex[:10]}",
            )

            results = await asyncio.gather(
                escrow.refund(db, context_type="hearing", context_id=hearing_id, reason="test"),
                escrow.refund(db, context_type="hearing", context_id=hearing_id, reason="test"),
                return_exceptions=True,
            )
            assert call_count["n"] == 1  # exactly one real gateway call, never two

            outcomes = []
            for r in results:
                if isinstance(r, HTTPException):
                    assert r.status_code == 409
                    outcomes.append("conflict")
                else:
                    assert r["status"] == "refunded"
                    outcomes.append("refunded")
            assert "refunded" in outcomes  # at least one call actually completed the refund

            escrow_doc = await db.escrow_transactions.find_one({"context_id": hearing_id}, {"_id": 0})
            assert escrow_doc["status"] == "refunded"
            assert escrow_doc["gateway_refund_id"] == "rfnd_fake_1"
        finally:
            razorpay_svc.refund_payment = orig_refund_payment
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_refund_gateway_failure_records_refund_failed_not_refunded():
    """Bug B (supersedes the old "released back to held and re-raised"
    behaviour): a failed gateway call must never leave the ledger claiming
    money moved. The escrow lands on the explicit, retryable
    "refund_failed" status with the error recorded, refund() returns
    instead of raising (the caller's cancel/dispute already committed), no
    wallet mutation happens, and retry_refund() completes it later."""
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = None
        orig_refund_payment = razorpay_svc.refund_payment
        orig_fetch = razorpay_svc.fetch_refunds
        razorpay_svc.refund_payment = MagicMock(side_effect=RuntimeError("gateway unreachable"))
        razorpay_svc.fetch_refunds = lambda payment_id: []
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
            )
            hearing_id = hearing["hearing_id"]
            await escrow.create_and_hold(
                db, context_type="hearing", context_id=hearing_id, service_id=hearings.ESCROW_SERVICE_ID,
                matter_id=None, payer_user_id=requester["user_id"], payee_user_id=counsel["user_id"],
                amount=1500.0, platform_commission_pct=0.1,
                razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=f"pay_live_{uuid.uuid4().hex[:10]}",
            )
            before = await db.users.find_one({"user_id": counsel["user_id"]}, {"_id": 0}) or {}

            result = await escrow.refund(db, context_type="hearing", context_id=hearing_id, reason="test")
            assert result["status"] == "refund_failed"  # not refunded, not silently back to "held"

            escrow_doc = await db.escrow_transactions.find_one({"context_id": hearing_id}, {"_id": 0})
            assert escrow_doc["status"] == "refund_failed"
            assert "gateway unreachable" in escrow_doc["refund_last_error"]
            assert escrow_doc["refund_failed_at"] and escrow_doc["refund_requested_at"]
            assert escrow_doc["refund_attempts"] == 1

            after = await db.users.find_one({"user_id": counsel["user_id"]}, {"_id": 0}) or {}
            assert after.get("wallet_held_balance") == before.get("wallet_held_balance")  # no wallet mutation happened

            # A second refund() call must not request another refund — retry is retry_refund()'s job.
            again = await escrow.refund(db, context_type="hearing", context_id=hearing_id, reason="test")
            assert again["status"] == "refund_failed"
            assert razorpay_svc.refund_payment.call_count == 1

            # Retry succeeds once the gateway is healthy again.
            razorpay_svc.refund_payment = lambda payment_id, amount_inr=None, notes=None: {
                "razorpay_refund_id": "rfnd_retry_1", "status": "processed", "simulated": False,
            }
            result = await escrow.retry_refund(db, escrow_doc["escrow_id"], {"user_id": "admin_test"})
            assert result["status"] == "refunded"
            assert result["gateway_refund_id"] == "rfnd_retry_1"
        finally:
            razorpay_svc.refund_payment = orig_refund_payment
            razorpay_svc.fetch_refunds = orig_fetch
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


# ---------- Bug B: refund outcomes, retry and idempotency ----------
# Razorpay is always stubbed here (refund_payment / fetch_refunds), so no
# test ever reaches the real gateway.

class _gateway:
    """Context manager stubbing razorpay_svc.refund_payment and
    fetch_refunds. `refund` / `existing` may be a dict/list or a callable;
    every call is counted."""
    def __init__(self, refund=None, existing=None):
        self.refund, self.existing = refund, existing if existing is not None else []
        self.refund_calls, self.fetch_calls = [], []

    def __enter__(self):
        self._orig = (razorpay_svc.refund_payment, razorpay_svc.fetch_refunds)

        def _refund(payment_id, amount_inr=None, notes=None):
            self.refund_calls.append({"payment_id": payment_id, "amount_inr": amount_inr})
            r = self.refund(payment_id, amount_inr) if callable(self.refund) else self.refund
            if isinstance(r, Exception):
                raise r
            return r

        def _fetch(payment_id):
            self.fetch_calls.append(payment_id)
            return self.existing(payment_id) if callable(self.existing) else self.existing
        razorpay_svc.refund_payment, razorpay_svc.fetch_refunds = _refund, _fetch
        return self

    def __exit__(self, *exc):
        razorpay_svc.refund_payment, razorpay_svc.fetch_refunds = self._orig


async def _held_escrow(db, counsel, amount=1500.0):
    context_id = f"hearing_bugb_{uuid.uuid4().hex[:10]}"
    await db.users.insert_one({"user_id": counsel["user_id"], "wallet_held_balance": 0})
    doc = await escrow.create_and_hold(
        db, context_type="hearing", context_id=context_id, service_id=hearings.ESCROW_SERVICE_ID,
        matter_id=None, payer_user_id=_user("payer")["user_id"], payee_user_id=counsel["user_id"],
        amount=amount, platform_commission_pct=0.2,
        razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=f"pay_live_{uuid.uuid4().hex[:10]}",
    )
    return context_id, doc


async def _held_balance(db, user_id):
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0}) or {}
    return u.get("wallet_held_balance", 0)


def _processed(rid="rfnd_ok"):
    return {"razorpay_refund_id": rid, "status": "processed", "simulated": False}


def test_bugb_successful_refund_and_repeat_is_idempotent():
    async def body():
        db = _db()
        counsel = _user("counsel")
        context_id, doc = await _held_escrow(db, counsel)
        try:
            assert await _held_balance(db, counsel["user_id"]) == doc["payee_amount"]
            with _gateway(refund=_processed()) as gw:
                first = await escrow.refund(db, context_type="hearing", context_id=context_id, reason="t")
                second = await escrow.refund(db, context_type="hearing", context_id=context_id, reason="t")
                retry = await escrow.retry_refund(db, doc["escrow_id"], {"user_id": "admin_t"})
            assert first["status"] == second["status"] == retry["status"] == "refunded"
            assert len(gw.refund_calls) == 1  # never a second refund
            e = await db.escrow_transactions.find_one({"escrow_id": doc["escrow_id"]}, {"_id": 0})
            assert e["gateway_refund_id"] == "rfnd_ok" and e["refund_completed_at"]
            assert await _held_balance(db, counsel["user_id"]) == 0  # reversed exactly once
        finally:
            await _cleanup(db, [context_id], [counsel["user_id"]])
    asyncio.run(body())


def test_bugb_pending_gateway_refund_is_processing_then_settles_without_new_refund():
    async def body():
        db = _db()
        counsel = _user("counsel")
        context_id, doc = await _held_escrow(db, counsel)
        try:
            with _gateway(refund={"razorpay_refund_id": "rfnd_p1", "status": "pending", "simulated": False}) as gw:
                r = await escrow.refund(db, context_type="hearing", context_id=context_id, reason="t")
            assert r["status"] == "refund_processing"  # NOT refunded just because it was requested
            assert await _held_balance(db, counsel["user_id"]) == 0

            with _gateway(refund=_processed("rfnd_new"),
                          existing=[{"razorpay_refund_id": "rfnd_p1", "amount_inr": 1500.0, "status": "processed"}]) as gw:
                r = await escrow.retry_refund(db, doc["escrow_id"], {"user_id": "admin_t"})
            assert r["status"] == "refunded"
            assert gw.refund_calls == []  # found at Razorpay — no second refund
            assert r["gateway_refund_id"] == "rfnd_p1"
            assert await _held_balance(db, counsel["user_id"]) == 0  # not reversed twice
        finally:
            await _cleanup(db, [context_id], [counsel["user_id"]])
    asyncio.run(body())


def test_bugb_timeout_but_refund_exists_at_razorpay_is_not_refunded_twice():
    """First call raises (timeout) although Razorpay actually created the
    refund; the retry must detect it instead of requesting another."""
    async def body():
        db = _db()
        counsel = _user("counsel")
        context_id, doc = await _held_escrow(db, counsel)
        try:
            with _gateway(refund=TimeoutError("read timed out")):
                r = await escrow.refund(db, context_type="hearing", context_id=context_id, reason="t")
            assert r["status"] == "refund_failed"
            assert await _held_balance(db, counsel["user_id"]) == doc["payee_amount"]  # nothing reversed on failure

            with _gateway(refund=_processed("rfnd_dup"),
                          existing=[{"razorpay_refund_id": "rfnd_real", "amount_inr": 1500.0, "status": "processed"}]) as gw:
                r = await escrow.retry_refund(db, doc["escrow_id"], {"user_id": "admin_t"})
            assert r["status"] == "refunded" and gw.refund_calls == []
            assert r["gateway_refund_id"] == "rfnd_real"
        finally:
            await _cleanup(db, [context_id], [counsel["user_id"]])
    asyncio.run(body())


def test_bugb_retry_requests_only_the_unrefunded_remainder():
    async def body():
        db = _db()
        counsel = _user("counsel")
        context_id, doc = await _held_escrow(db, counsel)
        try:
            with _gateway(refund=RuntimeError("boom")):
                await escrow.refund(db, context_type="hearing", context_id=context_id, reason="t")
            with _gateway(refund=_processed("rfnd_rest"),
                          existing=[{"razorpay_refund_id": "rfnd_part", "amount_inr": 500.0, "status": "processed"}]) as gw:
                r = await escrow.retry_refund(db, doc["escrow_id"], {"user_id": "admin_t"})
            assert r["status"] == "refunded"
            assert [c["amount_inr"] for c in gw.refund_calls] == [1000.0]
        finally:
            await _cleanup(db, [context_id], [counsel["user_id"]])
    asyncio.run(body())


def test_bugb_gateway_reports_failed_status_is_refund_failed():
    async def body():
        db = _db()
        counsel = _user("counsel")
        context_id, doc = await _held_escrow(db, counsel)
        try:
            with _gateway(refund={"razorpay_refund_id": "rfnd_f", "status": "failed", "simulated": False}):
                r = await escrow.refund(db, context_type="hearing", context_id=context_id, reason="t")
            assert r["status"] == "refund_failed"
            assert r["refund_last_error"] and r["gateway_refund_id"] == "rfnd_f"
            assert await _held_balance(db, counsel["user_id"]) == doc["payee_amount"]
        finally:
            await _cleanup(db, [context_id], [counsel["user_id"]])
    asyncio.run(body())


def test_bugb_concurrent_admin_retries_refund_once():
    async def body():
        db = _db()
        counsel = _user("counsel")
        context_id, doc = await _held_escrow(db, counsel)
        try:
            with _gateway(refund=RuntimeError("down")):
                await escrow.refund(db, context_type="hearing", context_id=context_id, reason="t")
            with _gateway(refund=_processed("rfnd_c")) as gw:
                results = await asyncio.gather(
                    escrow.retry_refund(db, doc["escrow_id"], {"user_id": "admin_a"}),
                    escrow.retry_refund(db, doc["escrow_id"], {"user_id": "admin_b"}),
                    return_exceptions=True,
                )
            assert len(gw.refund_calls) == 1
            outcomes = sorted("conflict" if isinstance(r, HTTPException) and r.status_code == 409 else r["status"]
                              for r in results)
            assert outcomes in (["conflict", "refunded"], ["refunded", "refunded"])
            e = await db.escrow_transactions.find_one({"escrow_id": doc["escrow_id"]}, {"_id": 0})
            assert e["status"] == "refunded" and e["refund_attempts"] == 2
            assert await _held_balance(db, counsel["user_id"]) == 0
        finally:
            await _cleanup(db, [context_id], [counsel["user_id"]])
    asyncio.run(body())


def test_bugb_retry_rules_for_pending_and_held():
    """A fresh in-flight refund_pending can't be retried (409); a stale one
    can. A held escrow (no refund requested) can't be 'retried' at all."""
    async def body():
        db = _db()
        counsel = _user("counsel")
        context_id, doc = await _held_escrow(db, counsel)
        try:
            try:
                await escrow.retry_refund(db, doc["escrow_id"], {"user_id": "admin_t"})
                raise AssertionError("retry on held must be refused")
            except HTTPException as e:
                assert e.status_code == 400

            fresh = datetime.now(timezone.utc).isoformat()
            await db.escrow_transactions.update_one({"escrow_id": doc["escrow_id"]},
                                                    {"$set": {"status": "refund_pending", "updated_at": fresh}})
            try:
                await escrow.retry_refund(db, doc["escrow_id"], {"user_id": "admin_t"})
                raise AssertionError("retry on a fresh in-flight claim must be refused")
            except HTTPException as e:
                assert e.status_code == 409

            stale = (datetime.now(timezone.utc) - timedelta(minutes=escrow.STALE_REFUND_PENDING_MINUTES + 5)).isoformat()
            await db.escrow_transactions.update_one({"escrow_id": doc["escrow_id"]}, {"$set": {"updated_at": stale}})
            with _gateway(refund=_processed("rfnd_s")) as gw:
                r = await escrow.retry_refund(db, doc["escrow_id"], {"user_id": "admin_t"})
            assert r["status"] == "refunded" and len(gw.fetch_calls) == 1 and len(gw.refund_calls) == 1
        finally:
            await _cleanup(db, [context_id], [counsel["user_id"]])
    asyncio.run(body())
