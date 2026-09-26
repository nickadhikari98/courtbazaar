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
    """Stub Razorpay: fetch_refund answers from `refunds` ({refund_id: status}
    or an Exception to raise); any refund-creating call fails the test."""
    def __init__(self, refunds):
        self.refunds, self.fetches = refunds, []

    def __enter__(self):
        self._orig = (razorpay_svc.fetch_refund, razorpay_svc.refund_payment, razorpay_svc.fetch_refunds)

        def fetch_refund(payment_id, refund_id):
            self.fetches.append(refund_id)
            answer = self.refunds[refund_id]
            if isinstance(answer, Exception):
                raise answer
            return {"razorpay_refund_id": refund_id, "payment_id": payment_id, "amount_inr": 1000.0,
                    "status": answer, "notes": {}}

        def must_not_refund(*a, **k):
            raise AssertionError("recovery must never request a refund")
        razorpay_svc.fetch_refund = fetch_refund
        razorpay_svc.refund_payment = must_not_refund
        razorpay_svc.fetch_refunds = must_not_refund
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
    """_gateway fails the test on refund_payment / fetch_refunds. Covers every
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
        assert counts == {"checked": 3, "settled": 1, "still_pending": 1, "errors": 1}
        # Recently accepted refunds are left to the webhook; refund_failed is never swept.
        assert young["gateway_refund_id"] not in gw.fetches
        assert (await _get(db, processed["escrow_id"]))["status"] == "refunded"
        for e in (pending, broken, young):
            assert (await _get(db, e["escrow_id"]))["status"] == "refund_processing"
        assert (await _get(db, failed_no_id["escrow_id"]))["status"] == "refund_failed"
    _run(body)
