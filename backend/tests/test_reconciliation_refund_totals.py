"""B7: /admin/reconciliation must not count refunded / refunding payments as
collected. A refund never changes payment_transactions (payment_status stays
"paid"); it lives on the escrow row for the same razorpay_order_id, so the
report reads the escrow status (payment_reconciliation.collection_state).

Rows are inserted directly (reconciliation only reads them) with created_at
inside a far-future window, and the report is queried with that window, so
the totals asserted here come only from this test's rows. server.db is
patched to a per-test client, same pattern as test_escrow_notifications.py.
"""
import asyncio
import csv
import io
import os
import sys
import unittest.mock
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import payment_reconciliation  # noqa: E402
import server  # noqa: E402

ADMIN = {"role": "admin", "user_id": "test_recon_admin"}
WINDOW_FROM, WINDOW_TO = "9999-06-01T00:00:00+00:00", "9999-06-01T23:59:59+00:00"


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


# (label, payment_status, escrow status or None, amount) — one row per state.
CASES = [
    ("paid_held", "paid", "held", 1000.0),
    ("paid_released", "paid", "released", 2000.0),
    ("refund_pending", "paid", "refund_pending", 300.0),
    ("refund_processing", "paid", "refund_processing", 400.0),
    ("refunded", "paid", "refunded", 500.0),
    ("refund_failed", "paid", "refund_failed", 700.0),
    ("pending", "pending", None, 50.0),
]


async def _seed(db):
    run = uuid.uuid4().hex[:8]
    order_ids = {}
    for i, (label, pstatus, escrow_status, amount) in enumerate(CASES):
        order_id = f"order_recon_{run}_{label}"
        order_ids[label] = order_id
        hearing_id = f"hearing_recon_{run}_{i}"
        await db.payment_transactions.insert_one({
            "razorpay_order_id": order_id, "razorpay_payment_id": f"pay_sim_{run}_{i}" if pstatus == "paid" else None,
            "session_id": order_id, "context_type": "hearing", "context_id": hearing_id,
            "user_id": "test_recon_client", "amount": amount, "currency": "INR", "gateway": "razorpay",
            "status": "complete" if pstatus == "paid" else "initiated", "payment_status": pstatus,
            "simulated": True, "created_at": f"9999-06-01T00:00:{i:02d}+00:00",
        })
        if escrow_status:
            await db.escrow_transactions.insert_one({
                "escrow_id": f"escrow_recon_{run}_{i}", "context_type": "hearing", "context_id": hearing_id,
                "amount": amount, "status": escrow_status, "razorpay_order_id": order_id,
                # Far future, so the refund_pending row is never "stale" —
                # the stale-claim mismatch list is irrelevant to totals.
                "updated_at": "9999-06-01T00:00:00+00:00",
            })
    return order_ids


async def _cleanup(db, order_ids):
    ids = list(order_ids.values())
    await db.payment_transactions.delete_many({"razorpay_order_id": {"$in": ids}})
    await db.escrow_transactions.delete_many({"razorpay_order_id": {"$in": ids}})


def _run(body):
    async def wrapped():
        db = _db()
        with unittest.mock.patch.object(server, "db", db):
            order_ids = await _seed(db)
            try:
                await body(db, order_ids)
            finally:
                await _cleanup(db, order_ids)
    asyncio.run(wrapped())


async def _report():
    return await server.admin_reconciliation(user=ADMIN, gateway=None, status_filter=None,
                                             from_date=WINDOW_FROM, to_date=WINDOW_TO)


def test_collection_state_for_every_refund_state():
    cs = payment_reconciliation.collection_state
    paid = {"payment_status": "paid"}
    assert cs(paid, None) == "paid"                    # no escrow (e.g. marketplace order)
    assert cs(paid, "held") == "paid"
    assert cs(paid, "released") == "paid"
    assert cs(paid, "refund_pending") == "refunding"
    assert cs(paid, "refund_processing") == "refunding"
    assert cs(paid, "refunded") == "refunded"
    assert cs(paid, "refund_failed") == "paid"         # never refunded — still collected
    assert cs({"payment_status": "pending"}, None) == "pending"
    assert cs({"payment_status": "failed"}, None) == "failed"
    assert cs({"payment_status": "paid", "orphaned": True}, None) == "orphaned"


def test_paid_totals_exclude_refunded_and_refunding():
    async def body(db, order_ids):
        totals = (await _report())["totals"]
        rzp = totals["razorpay"]
        # held 1000 + released 2000 + refund_failed 700 are collected.
        assert rzp["paid"] == 3 and rzp["paid_amount"] == 3700.0
        # refund_pending 300 + refund_processing 400 are on their way back.
        assert rzp["refunding"] == 2 and rzp["refunding_amount"] == 700.0
        assert rzp["refunded"] == 1 and rzp["refunded_amount"] == 500.0
        assert rzp["pending"] == 1 and rzp["failed"] == 0 and rzp["orphaned"] == 0
        assert totals["grand_total_paid"] == 3700.0
        assert totals["grand_total_refunding"] == 700.0
        assert totals["grand_total_refunded"] == 500.0
        assert totals["transaction_count"] == len(CASES)
    _run(body)


def test_rows_carry_refund_status_and_collection_state():
    async def body(db, order_ids):
        rows = {r["razorpay_order_id"]: r for r in (await _report())["rows"]}
        expect = {
            "paid_held": (None, "paid"),
            "paid_released": (None, "paid"),
            "refund_pending": ("refund_pending", "refunding"),
            "refund_processing": ("refund_processing", "refunding"),
            "refunded": ("refunded", "refunded"),
            "refund_failed": ("refund_failed", "paid"),
            "pending": (None, "pending"),
        }
        for label, (refund_status, collection) in expect.items():
            row = rows[order_ids[label]]
            assert row["refund_status"] == refund_status, label
            assert row["collection_state"] == collection, label
            assert row["payment_status"] == ("pending" if label == "pending" else "paid"), label
        # Displayed paid total == sum of the rows counted as paid.
        report = await _report()
        assert sum(r["amount"] for r in report["rows"] if r["collection_state"] == "paid") == report["totals"]["grand_total_paid"]
    _run(body)


def test_csv_export_matches_paid_totals():
    async def body(db, order_ids):
        resp = await server.admin_reconciliation_csv(user=ADMIN)
        reader = csv.DictReader(io.StringIO(resp.body.decode()))
        ours = {r["session_id"]: r for r in reader if r["session_id"] in set(order_ids.values())}
        assert len(ours) == len(CASES)
        assert ours[order_ids["refunded"]]["refund_status"] == "refunded"
        assert ours[order_ids["refunded"]]["counted_as_paid"] == "False"
        assert ours[order_ids["refund_processing"]]["counted_as_paid"] == "False"
        assert ours[order_ids["refund_pending"]]["counted_as_paid"] == "False"
        assert ours[order_ids["refund_failed"]]["refund_status"] == "refund_failed"
        assert ours[order_ids["refund_failed"]]["counted_as_paid"] == "True"
        assert ours[order_ids["paid_held"]]["refund_status"] == ""
        csv_paid = sum(float(r["amount"]) for r in ours.values() if r["counted_as_paid"] == "True")
        assert csv_paid == (await _report())["totals"]["grand_total_paid"] == 3700.0
    _run(body)
