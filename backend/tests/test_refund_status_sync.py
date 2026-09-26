"""Missed refund webhook recovery (escrow.sync_refund_status /
sync_processing_refunds): a refund Razorpay accepted stays refund_processing
until its refund.processed / refund.failed webhook arrives; if it never does,
the sync reads that refund's status from Razorpay and settles through the
webhook's own settle_refund_from_gateway. It must never request a refund.

Runs against its own throwaway database (not DB_NAME): the sweep scans every
refund_processing escrow, and the shared dev DB holds real QA escrows that
these tests must never settle. The gateway is stubbed — fetch_refund answers
from a dict; refund_payment / fetch_refunds raise if anything calls them.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import escrow  # noqa: E402
import razorpay_svc  # noqa: E402

OLD = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()


class _gateway:
    """Stub Razorpay. fetch_refund answers from `refunds` ({refund_id: status}
    or an Exception to raise). fetch_refunds (read-only list for a payment)
    answers from `payment_refunds` ({payment_id: [refund dicts]}); by default
    the fetched refund is the payment's only refund, for the full ₹1,000.
    refund_payment — the only call that creates a refund — fails the test
    unless `allow_refund` is set, in which case it is recorded."""
    def __init__(self, refunds, payment_refunds=None, allow_refund=None):
        self.refunds, self.payment_refunds, self.allow_refund = refunds, payment_refunds or {}, allow_refund
        self.fetches, self.refund_requests, self._payment_of = [], [], {}

    def __enter__(self):
        self._orig = (razorpay_svc.fetch_refund, razorpay_svc.refund_payment, razorpay_svc.fetch_refunds)

        def fetch_refund(payment_id, refund_id):
            self.fetches.append(refund_id)
            answer = self.refunds[refund_id]
            if isinstance(answer, Exception):
                raise answer
            self._payment_of[payment_id] = (refund_id, answer)
            return {"razorpay_refund_id": refund_id, "payment_id": payment_id, "amount_inr": 1000.0,
                    "status": answer, "notes": {}}

        def fetch_refunds(payment_id):
            if payment_id in self.payment_refunds:
                return self.payment_refunds[payment_id]
            refund_id, status = self._payment_of.get(payment_id, (None, None))
            return [{"razorpay_refund_id": refund_id, "amount_inr": 1000.0, "status": status}] if refund_id else []

        def refund_payment(payment_id, amount_inr=None, notes=None):
            if not self.allow_refund:
                raise AssertionError("recovery must never request a refund")
            self.refund_requests.append({"payment_id": payment_id, "amount_inr": amount_inr, "notes": notes})
            return self.allow_refund
        razorpay_svc.fetch_refund = fetch_refund
        razorpay_svc.refund_payment = refund_payment
        razorpay_svc.fetch_refunds = fetch_refunds
        return self

    def __exit__(self, *exc):
        razorpay_svc.fetch_refund, razorpay_svc.refund_payment, razorpay_svc.fetch_refunds = self._orig


def _run(body):
    async def wrapped():
        client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = client[f"cb_test_refund_sync_{uuid.uuid4().hex[:8]}"]
        try:
            await body(db)
        finally:
            await client.drop_database(db.name)
    asyncio.run(wrapped())


async def _escrow(db, status="refund_processing", refund_id="auto", payee=True, updated_at=OLD):
    n = uuid.uuid4().hex[:10]
    doc = {
        "escrow_id": f"escrow_{n}", "context_type": "hearing", "context_id": f"hearing_{n}",
        "amount": 1000.0, "payee_amount": 800.0, "status": status,
        "payee_user_id": f"user_payee_{n}" if payee else None,
        "razorpay_order_id": f"order_{n}", "razorpay_payment_id": f"pay_{n}",
        "refund_attempts": 1, "updated_at": updated_at, "timeline": [],
        "gateway_refund_id": f"rfnd_{n}" if refund_id == "auto" else refund_id,
        "gateway_refund_status": "pending" if status == "refund_processing" else None,
    }
    if payee:
        await db.users.insert_one({"user_id": doc["payee_user_id"], "wallet_held_balance": 800.0})
    await db.escrow_transactions.insert_one(dict(doc))
    return doc


async def _get(db, escrow_id):
    return await db.escrow_transactions.find_one({"escrow_id": escrow_id}, {"_id": 0})


async def _held(db, user_id):
    return (await db.users.find_one({"user_id": user_id}))["wallet_held_balance"]


def test_processed_refund_with_missed_webhook_settles_to_refunded():
    async def body(db):
        e = await _escrow(db)
        with _gateway({e["gateway_refund_id"]: "processed"}):
            result = await escrow.sync_refund_status(db, e["escrow_id"])
        assert result["refund_sync"] == "settled" and result["status"] == "refunded"
        stored = await _get(db, e["escrow_id"])
        assert stored["status"] == "refunded"
        assert stored["gateway_refund_status"] == "processed" and stored["refund_completed_at"]
        assert stored["gateway_refund_id"] == e["gateway_refund_id"]
        # Full refund: Razorpay's processed total equals the escrow amount.
        assert stored["refunded_amount"] == 1000.0 and stored["refund_partial"] is False
        assert stored["timeline"][-1]["status"] == "refunded"
        assert stored["timeline"][-1]["by"] == "refund_status_sync"
        # Same side effect the webhook applies: the payee's held balance is released once.
        assert stored["payee_hold_reversed"] is True
        assert await _held(db, e["payee_user_id"]) == 0.0
    _run(body)


def test_pending_refund_stays_processing_and_is_not_written():
    async def body(db):
        e = await _escrow(db)
        for pending in ("pending", "created"):
            with _gateway({e["gateway_refund_id"]: pending}):
                result = await escrow.sync_refund_status(db, e["escrow_id"])
            assert result["refund_sync"] == "still_pending"
        stored = await _get(db, e["escrow_id"])
        assert stored["status"] == "refund_processing" and stored["updated_at"] == OLD
        assert stored["timeline"] == [] and not stored.get("payee_hold_reversed")
        assert await _held(db, e["payee_user_id"]) == 800.0
    _run(body)


def test_failed_refund_settles_to_refund_failed():
    async def body(db):
        e = await _escrow(db)
        with _gateway({e["gateway_refund_id"]: "failed"}):
            result = await escrow.sync_refund_status(db, e["escrow_id"])
        assert result["refund_sync"] == "settled" and result["status"] == "refund_failed"
        stored = await _get(db, e["escrow_id"])
        assert stored["status"] == "refund_failed" and stored["gateway_refund_status"] == "failed"
        assert stored["refund_last_error"] and stored["refund_failed_at"]
        # A failed refund returned no money: the payee hold stays until a retry succeeds.
        assert not stored.get("payee_hold_reversed") and await _held(db, e["payee_user_id"]) == 800.0
    _run(body)


def test_recovery_never_requests_a_refund():
    """_gateway fails the test on refund_payment. Covers every
    outcome, plus escrows sync must leave alone (no refund id — e.g. a
    refund_failed call that never created a refund — and simulated payments)."""
    async def body(db):
        processed, pending, failed = await _escrow(db), await _escrow(db), await _escrow(db)
        no_refund_id = await _escrow(db, status="refund_failed", refund_id=None)
        processing_without_id = await _escrow(db, refund_id=None)
        refunds = {processed["gateway_refund_id"]: "processed", pending["gateway_refund_id"]: "pending",
                   failed["gateway_refund_id"]: "failed"}
        with _gateway(refunds) as gw:
            for e in (processed, pending, failed):
                await escrow.sync_refund_status(db, e["escrow_id"])
            for e in (no_refund_id, processing_without_id):
                assert (await escrow.sync_refund_status(db, e["escrow_id"]))["refund_sync"] == "not_applicable"
        # Only the three stored refund ids were looked up — nothing else touched Razorpay.
        assert sorted(gw.fetches) == sorted(refunds)
        assert (await _get(db, no_refund_id["escrow_id"]))["status"] == "refund_failed"
        assert (await _get(db, processing_without_id["escrow_id"]))["status"] == "refund_processing"

        sim = await _escrow(db)
        await db.escrow_transactions.update_one({"escrow_id": sim["escrow_id"]},
                                                {"$set": {"razorpay_payment_id": "pay_sim_x"}})
        with _gateway({}) as gw:
            assert (await escrow.sync_refund_status(db, sim["escrow_id"]))["refund_sync"] == "not_applicable"
        assert gw.fetches == []
    _run(body)


def test_repeated_and_concurrent_recovery_is_idempotent():
    async def body(db):
        e = await _escrow(db)
        with _gateway({e["gateway_refund_id"]: "processed"}):
            results = await asyncio.gather(*(escrow.sync_refund_status(db, e["escrow_id"]) for _ in range(5)))
            again = await escrow.sync_refund_status(db, e["escrow_id"])
        assert [r["refund_sync"] for r in results].count("settled") == 1
        assert again["refund_sync"] == "not_applicable" and again["status"] == "refunded"
        stored = await _get(db, e["escrow_id"])
        assert [t["status"] for t in stored["timeline"]] == ["refunded"]
        assert await _held(db, e["payee_user_id"]) == 0.0  # reversed exactly once
        # A late webhook after recovery is the normal duplicate-event no-op.
        late = await escrow.settle_refund_from_gateway(db, refund_id=e["gateway_refund_id"],
                                                       payment_id=e["razorpay_payment_id"], gateway_status="processed")
        assert late["refund_settled"] is False and await _held(db, e["payee_user_id"]) == 0.0
    _run(body)


def test_gateway_error_changes_nothing():
    async def body(db):
        e = await _escrow(db)
        with _gateway({e["gateway_refund_id"]: RuntimeError("TLS handshake failed")}):
            with pytest.raises(HTTPException) as exc:
                await escrow.sync_refund_status(db, e["escrow_id"])
        assert exc.value.status_code == 502 and "nothing was changed" in exc.value.detail
        stored = await _get(db, e["escrow_id"])
        assert stored["status"] == "refund_processing" and stored["updated_at"] == OLD
    _run(body)


def test_sweep_settles_old_processing_refunds_only():
    async def body(db):
        processed, pending, broken = await _escrow(db), await _escrow(db), await _escrow(db)
        young = await _escrow(db, updated_at=datetime.now(timezone.utc).isoformat())
        failed_no_id = await _escrow(db, status="refund_failed", refund_id=None)
        with _gateway({processed["gateway_refund_id"]: "processed", pending["gateway_refund_id"]: "pending",
                       broken["gateway_refund_id"]: RuntimeError("gateway down")}) as gw:
            counts = await escrow.sync_processing_refunds(db)
        assert counts == {"checked": 3, "settled": 1, "still_pending": 1, "errors": 1, "batches": 1}
        # Recently accepted refunds are left to the webhook; refund_failed is never swept.
        assert young["gateway_refund_id"] not in gw.fetches
        assert (await _get(db, processed["escrow_id"]))["status"] == "refunded"
        for e in (pending, broken, young):
            assert (await _get(db, e["escrow_id"]))["status"] == "refund_processing"
        assert (await _get(db, failed_no_id["escrow_id"]))["status"] == "refund_failed"
    _run(body)


# ---------- Partial refunds ----------

def test_partial_refund_is_never_marked_refunded():
    async def body(db):
        e = await _escrow(db)
        partial = [{"razorpay_refund_id": e["gateway_refund_id"], "amount_inr": 400.0, "status": "processed"}]
        with _gateway({e["gateway_refund_id"]: "processed"}, {e["razorpay_payment_id"]: partial}):
            result = await escrow.sync_refund_status(db, e["escrow_id"])
        assert result["status"] == "refund_failed" and result["refund_sync"] == "settled"
        stored = await _get(db, e["escrow_id"])
        assert stored["status"] == "refund_failed" and stored["refund_partial"] is True
        assert stored["refunded_amount"] == 400.0 and stored["gateway_refund_status"] == "processed"
        assert "Rs.400 of Rs.1000" in stored["refund_last_error"]
        assert "Rs.600 is still owed" in stored["refund_last_error"]
        assert not stored.get("refund_completed_at")
        # Money is still owed, so the payee's held balance stays locked.
        assert not stored.get("payee_hold_reversed") and await _held(db, e["payee_user_id"]) == 800.0
    _run(body)


def test_partial_refund_retry_requests_only_the_remainder():
    async def body(db):
        e = await _escrow(db)
        partial = [{"razorpay_refund_id": e["gateway_refund_id"], "amount_inr": 400.0, "status": "processed"}]
        with _gateway({e["gateway_refund_id"]: "processed"}, {e["razorpay_payment_id"]: partial},
                      allow_refund={"razorpay_refund_id": "rfnd_rest", "status": "processed"}) as gw:
            await escrow.sync_refund_status(db, e["escrow_id"])
            result = await escrow.retry_refund(db, e["escrow_id"], {"user_id": "admin_test"})
        assert [r["amount_inr"] for r in gw.refund_requests] == [600.0]
        assert result["status"] == "refunded"
        stored = await _get(db, e["escrow_id"])
        assert stored["status"] == "refunded" and stored["gateway_refund_id"] == "rfnd_rest"
        # The partial outcome is archived, not lost.
        assert stored["refund_error_history"][0]["error"].startswith("Partial refund")
        assert await _held(db, e["payee_user_id"]) == 0.0
    _run(body)


def test_several_processed_refunds_adding_up_to_full_are_refunded():
    async def body(db):
        e = await _escrow(db)
        split = [{"razorpay_refund_id": "rfnd_a", "amount_inr": 400.0, "status": "processed"},
                 {"razorpay_refund_id": e["gateway_refund_id"], "amount_inr": 600.0, "status": "processed"},
                 {"razorpay_refund_id": "rfnd_failed", "amount_inr": 1000.0, "status": "failed"}]
        with _gateway({e["gateway_refund_id"]: "processed"}, {e["razorpay_payment_id"]: split}):
            result = await escrow.sync_refund_status(db, e["escrow_id"])
        assert result["status"] == "refunded"
        assert (await _get(db, e["escrow_id"]))["refunded_amount"] == 1000.0  # the failed one isn't counted
    _run(body)


def test_webhook_settle_without_amount_is_unchanged():
    """The webhook doesn't pass refunded_amount: a processed event still
    settles to refunded exactly as before."""
    async def body(db):
        e = await _escrow(db)
        result = await escrow.settle_refund_from_gateway(db, refund_id=e["gateway_refund_id"],
                                                         payment_id=e["razorpay_payment_id"], gateway_status="processed")
        assert result["refund_settled"] is True and result["status"] == "refunded"
        stored = await _get(db, e["escrow_id"])
        assert "refunded_amount" not in stored and "refund_partial" not in stored
        assert stored["timeline"][-1]["by"] == "razorpay_webhook"
    _run(body)


# ---------- Failed-refund retry (retry_refund) ----------

async def _failed_escrow(db, error="invalid request sent"):
    e = await _escrow(db, status="refund_failed", refund_id=None)
    await db.escrow_transactions.update_one({"escrow_id": e["escrow_id"]}, {"$set": {
        "refund_last_error": error, "refund_failed_at": "2026-09-24T14:40:50+00:00"}})
    return e


def test_failed_refund_retry_preserves_original_error_and_refunds_once():
    async def body(db):
        e = await _failed_escrow(db)
        with _gateway({}, {e["razorpay_payment_id"]: []},
                      allow_refund={"razorpay_refund_id": "rfnd_new", "status": "processed"}) as gw:
            result = await escrow.retry_refund(db, e["escrow_id"], {"user_id": "admin_test"})
        assert len(gw.refund_requests) == 1 and gw.refund_requests[0]["amount_inr"] == 1000.0
        assert gw.refund_requests[0]["notes"]["refund_attempt"] == 2
        assert result["status"] == "refunded"
        stored = await _get(db, e["escrow_id"])
        assert stored["refund_attempts"] == 2 and stored["gateway_refund_id"] == "rfnd_new"
        assert stored["refund_error_history"] == [{
            "attempt": 1, "status": "refund_failed", "error": "invalid request sent",
            "failed_at": "2026-09-24T14:40:50+00:00", "gateway_refund_id": None,
            "archived_at": stored["refund_last_retry_at"]}]
    _run(body)


def test_failed_retry_keeps_every_earlier_error():
    async def body(db):
        e = await _failed_escrow(db)
        with _gateway({}, {e["razorpay_payment_id"]: []}):
            orig = razorpay_svc.refund_payment

            def rejected(*a, **k):
                raise RuntimeError("invalid request sent (again)")
            razorpay_svc.refund_payment = rejected
            try:
                result = await escrow.retry_refund(db, e["escrow_id"], {"user_id": "admin_test"})
            finally:
                razorpay_svc.refund_payment = orig
        assert result["status"] == "refund_failed"
        stored = await _get(db, e["escrow_id"])
        assert stored["refund_last_error"] == "invalid request sent (again)"
        assert [h["error"] for h in stored["refund_error_history"]] == ["invalid request sent"]
    _run(body)


def test_retry_never_duplicates_an_existing_refund():
    async def body(db):
        done, inflight = await _failed_escrow(db), await _failed_escrow(db)
        existing = {
            done["razorpay_payment_id"]: [{"razorpay_refund_id": "rfnd_done", "amount_inr": 1000.0, "status": "processed"}],
            inflight["razorpay_payment_id"]: [{"razorpay_refund_id": "rfnd_pend", "amount_inr": 1000.0, "status": "pending"}],
        }
        with _gateway({}, existing) as gw:  # refund_payment would fail the test
            r1 = await escrow.retry_refund(db, done["escrow_id"], {"user_id": "admin_test"})
            r2 = await escrow.retry_refund(db, inflight["escrow_id"], {"user_id": "admin_test"})
        assert gw.refund_requests == []
        assert r1["status"] == "refunded" and r1["gateway_refund_id"] == "rfnd_done"
        assert r2["status"] == "refund_processing" and r2["gateway_refund_id"] == "rfnd_pend"
    _run(body)


def test_concurrent_retries_request_at_most_one_refund():
    async def body(db):
        e = await _failed_escrow(db)
        with _gateway({}, {e["razorpay_payment_id"]: []},
                      allow_refund={"razorpay_refund_id": "rfnd_once", "status": "processed"}) as gw:
            results = await asyncio.gather(*(escrow.retry_refund(db, e["escrow_id"], {"user_id": "admin_test"})
                                             for _ in range(5)), return_exceptions=True)
        assert len(gw.refund_requests) == 1
        ok = [r for r in results if isinstance(r, dict)]
        assert ok and all(r["status"] == "refunded" for r in ok)
        assert all(isinstance(r, HTTPException) and r.status_code in (400, 409)
                   for r in results if not isinstance(r, dict))
        stored = await _get(db, e["escrow_id"])
        assert stored["refund_attempts"] == 2 and len(stored["refund_error_history"]) == 1
    _run(body)


# ---------- Sweep: batching and no starvation ----------

def test_sweep_pages_through_more_than_one_batch():
    async def body(db):
        escrows = [await _escrow(db, payee=False) for _ in range(60)]
        with _gateway({e["gateway_refund_id"]: "processed" for e in escrows}) as gw:
            counts = await escrow.sync_processing_refunds(db)
        assert counts["checked"] == 60 and counts["settled"] == 60 and counts["batches"] == 2
        assert len(gw.fetches) == 60  # each checked exactly once
        assert await db.escrow_transactions.count_documents({"status": "refund_processing"}) == 0
    _run(body)


def test_stuck_backlog_cannot_starve_newer_refunds(monkeypatch):
    """Per-run capacity shrunk to 10 checks; 30 older refunds stay pending at
    Razorpay forever. A newer processed refund must still be settled within a
    few runs (ordering by updated_at alone re-checked the same oldest escrows
    every run, so it never would be), and the backlog is checked round-robin."""
    monkeypatch.setattr(escrow, "REFUND_SYNC_BATCH", 5)
    monkeypatch.setattr(escrow, "REFUND_SYNC_MAX_BATCHES", 2)

    async def body(db):
        base = datetime.now(timezone.utc) - timedelta(days=3)
        stuck = [await _escrow(db, payee=False, updated_at=(base + timedelta(minutes=i)).isoformat())
                 for i in range(30)]
        newer = await _escrow(db, payee=False)  # 2h old: newer than the whole backlog
        answers = {e["gateway_refund_id"]: "pending" for e in stuck}
        answers[newer["gateway_refund_id"]] = "processed"
        runs = 0
        with _gateway(answers) as gw:
            while (await _get(db, newer["escrow_id"]))["status"] != "refunded":
                runs += 1
                assert runs <= 4, "newer refund starved behind the stuck backlog"
                counts = await escrow.sync_processing_refunds(db)
                assert counts["checked"] <= 10
        # Round-robin: all 31 were checked once before anyone was re-checked.
        first_round = gw.fetches[:31]
        assert len(set(first_round)) == 31 and newer["gateway_refund_id"] in first_round
        for e in stuck:
            assert (await _get(db, e["escrow_id"]))["status"] == "refund_processing"
    _run(body)


def test_concurrent_sweeps_check_each_refund_once():
    async def body(db):
        escrows = [await _escrow(db, payee=False) for _ in range(20)]
        with _gateway({e["gateway_refund_id"]: "pending" for e in escrows}) as gw:
            results = await asyncio.gather(escrow.sync_processing_refunds(db), escrow.sync_processing_refunds(db))
        assert sum(r["checked"] for r in results) == 20
        assert sorted(gw.fetches) == sorted(e["gateway_refund_id"] for e in escrows)
    _run(body)
