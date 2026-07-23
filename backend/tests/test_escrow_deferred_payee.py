"""Escrow deferred-payee support (Counsel Matching Agent roadmap M2).

Unlike test_courtbazaar_api.py / test_dpdp_token_fix.py, this file exercises
escrow.py directly rather than through HTTP: create_and_hold(payee_user_id=None)
and assign_payee() have no API endpoint yet (that lands in M11/M12), so a
black-box HTTP test has nothing to call. Plain asyncio.run() wrappers are used
instead of pytest-asyncio, which isn't a dependency of this project.

Each test creates its own throwaway users/escrow rows (unique uuids) and
cleans them up in a finally block, same spirit as test_dpdp_token_fix.py's
throwaway TEST_* accounts.
"""
import asyncio
import os
import sys
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import escrow  # noqa: E402

from fastapi import HTTPException  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


async def _make_user(db, wallet_held_balance=0):
    user_id = f"test_escrow_payee_{uuid.uuid4().hex[:10]}"
    await db.users.insert_one({"user_id": user_id, "wallet_held_balance": wallet_held_balance, "wallet_balance": 0})
    return user_id


async def _wallet_held(db, user_id):
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "wallet_held_balance": 1})
    return (u or {}).get("wallet_held_balance", 0)


async def _cleanup(db, *, user_ids=(), context_ids=()):
    if user_ids:
        await db.users.delete_many({"user_id": {"$in": list(user_ids)}})
    if context_ids:
        await db.escrow_transactions.delete_many({"context_id": {"$in": list(context_ids)}})
        await db.wallet_transactions.delete_many({"related_entity_id": {"$in": list(context_ids)}})


def test_create_and_hold_with_payee_credits_wallet_immediately():
    """Existing behavior, unchanged: payee known at hold time -> credited now."""
    async def body():
        db = _db()
        payee = await _make_user(db)
        context_id = f"test_ctx_{uuid.uuid4().hex[:10]}"
        try:
            doc = await escrow.create_and_hold(
                db, context_type="hearing", context_id=context_id, service_id="hire_proxy_counsel",
                matter_id=None, payer_user_id="test_payer", payee_user_id=payee,
                amount=1000.0, platform_commission_pct=0.20,
                razorpay_order_id=None, razorpay_payment_id=None,
            )
            assert doc["status"] == "held"
            assert doc["payee_user_id"] == payee
            assert doc["payee_amount"] == 800.0
            assert await _wallet_held(db, payee) == 800.0
        finally:
            await _cleanup(db, user_ids=[payee], context_ids=[context_id])
    asyncio.run(body())


def test_create_and_hold_without_payee_defers_credit():
    """New behavior: payee_user_id=None holds funds without crediting anyone."""
    async def body():
        db = _db()
        context_id = f"test_ctx_{uuid.uuid4().hex[:10]}"
        try:
            doc = await escrow.create_and_hold(
                db, context_type="hearing", context_id=context_id, service_id="hire_proxy_counsel",
                matter_id=None, payer_user_id="test_payer", payee_user_id=None,
                amount=1000.0, platform_commission_pct=0.20,
                razorpay_order_id=None, razorpay_payment_id=None,
            )
            assert doc["status"] == "held"
            assert doc["payee_user_id"] is None
            assert doc["payee_amount"] == 800.0
            stored = await db.escrow_transactions.find_one({"context_id": context_id}, {"_id": 0})
            assert stored["payee_user_id"] is None
        finally:
            await _cleanup(db, context_ids=[context_id])
    asyncio.run(body())


def test_assign_payee_credits_wallet_and_is_idempotent():
    async def body():
        db = _db()
        payee = await _make_user(db)
        context_id = f"test_ctx_{uuid.uuid4().hex[:10]}"
        try:
            await escrow.create_and_hold(
                db, context_type="hearing", context_id=context_id, service_id="hire_proxy_counsel",
                matter_id=None, payer_user_id="test_payer", payee_user_id=None,
                amount=1000.0, platform_commission_pct=0.20,
                razorpay_order_id=None, razorpay_payment_id=None,
            )
            assert await _wallet_held(db, payee) == 0

            updated = await escrow.assign_payee(db, context_type="hearing", context_id=context_id, payee_user_id=payee)
            assert updated["payee_user_id"] == payee
            assert await _wallet_held(db, payee) == 800.0

            # Retry with the same payee -> idempotent, no second credit
            again = await escrow.assign_payee(db, context_type="hearing", context_id=context_id, payee_user_id=payee)
            assert again["payee_user_id"] == payee
            assert await _wallet_held(db, payee) == 800.0
        finally:
            await _cleanup(db, user_ids=[payee], context_ids=[context_id])
    asyncio.run(body())


def test_assign_payee_conflict_when_different_payee():
    async def body():
        db = _db()
        payee_a = await _make_user(db)
        payee_b = await _make_user(db)
        context_id = f"test_ctx_{uuid.uuid4().hex[:10]}"
        try:
            await escrow.create_and_hold(
                db, context_type="hearing", context_id=context_id, service_id="hire_proxy_counsel",
                matter_id=None, payer_user_id="test_payer", payee_user_id=None,
                amount=500.0, platform_commission_pct=0.20,
                razorpay_order_id=None, razorpay_payment_id=None,
            )
            await escrow.assign_payee(db, context_type="hearing", context_id=context_id, payee_user_id=payee_a)

            with pytest.raises(HTTPException) as exc_info:
                await escrow.assign_payee(db, context_type="hearing", context_id=context_id, payee_user_id=payee_b)
            assert exc_info.value.status_code == 409

            stored = await db.escrow_transactions.find_one({"context_id": context_id}, {"_id": 0})
            assert stored["payee_user_id"] == payee_a
            assert await _wallet_held(db, payee_b) == 0
        finally:
            await _cleanup(db, user_ids=[payee_a, payee_b], context_ids=[context_id])
    asyncio.run(body())


def test_assign_payee_missing_context_404():
    async def body():
        db = _db()
        with pytest.raises(HTTPException) as exc_info:
            await escrow.assign_payee(db, context_type="hearing", context_id="nonexistent_ctx", payee_user_id="whoever")
        assert exc_info.value.status_code == 404
    asyncio.run(body())


def test_refund_without_assigned_payee_no_wallet_mutation():
    async def body():
        db = _db()
        context_id = f"test_ctx_{uuid.uuid4().hex[:10]}"
        try:
            await escrow.create_and_hold(
                db, context_type="hearing", context_id=context_id, service_id="hire_proxy_counsel",
                matter_id=None, payer_user_id="test_payer", payee_user_id=None,
                amount=1000.0, platform_commission_pct=0.20,
                razorpay_order_id=None, razorpay_payment_id=None,
            )
            refunded = await escrow.refund(db, context_type="hearing", context_id=context_id, reason="No counsel available within SLA")
            assert refunded["status"] == "refunded"
            assert refunded["refund_reason"] == "No counsel available within SLA"
        finally:
            await _cleanup(db, context_ids=[context_id])
    asyncio.run(body())


def test_release_without_assigned_payee_raises():
    async def body():
        db = _db()
        context_id = f"test_ctx_{uuid.uuid4().hex[:10]}"
        try:
            await escrow.create_and_hold(
                db, context_type="hearing", context_id=context_id, service_id="hire_proxy_counsel",
                matter_id=None, payer_user_id="test_payer", payee_user_id=None,
                amount=1000.0, platform_commission_pct=0.20,
                razorpay_order_id=None, razorpay_payment_id=None,
            )
            with pytest.raises(HTTPException) as exc_info:
                await escrow.release(db, context_type="hearing", context_id=context_id, released_by_user_id="admin")
            assert exc_info.value.status_code == 400

            stored = await db.escrow_transactions.find_one({"context_id": context_id}, {"_id": 0})
            assert stored["status"] == "held"  # unchanged — release must not have proceeded
        finally:
            await _cleanup(db, context_ids=[context_id])
    asyncio.run(body())
