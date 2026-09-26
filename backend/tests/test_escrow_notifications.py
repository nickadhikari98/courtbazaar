"""Notification audit (production readiness pass) — closes real gaps found
while auditing the hearing lifecycle: cancel, rate, and dispute-resolution
previously notified nobody at all.

Same pattern as test_negotiation_notifications.py: server.py endpoint
functions called directly as plain functions (the router decorator returns
them unchanged) with server.db monkeypatched to a fresh per-test client, so
each asyncio.run() body gets its own motor client bound to its own event
loop. Each test creates its own throwaway users/hearing rows and cleans up
in a finally block.
"""
import asyncio
import os
import sys
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hearings  # noqa: E402
import negotiation  # noqa: E402
import server  # noqa: E402
from server import HearingDisputeResolve, HearingRatingCreate  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _user(prefix):
    return {"user_id": f"test_escnotif_{prefix}_{uuid.uuid4().hex[:10]}", "role": "admin" if prefix == "admin" else "customer"}


async def _insert_user(db, user):
    await db.users.insert_one({"user_id": user["user_id"], "name": f"Test {user['user_id']}"})


async def _cleanup(db, user_ids=(), hearing_ids=()):
    if user_ids:
        await db.users.delete_many({"user_id": {"$in": list(user_ids)}})
        await db.notification_events.delete_many({"user_id": {"$in": list(user_ids)}})
    if hearing_ids:
        await db.hearing_requests.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
        await db.escrow_transactions.delete_many({"context_id": {"$in": list(hearing_ids)}})
        await db.negotiations.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
        await db.professional_ratings.delete_many({"context_id": {"$in": list(hearing_ids)}})


def test_cancel_notifies_counsel_with_refund_note():
    """Broadcast (non-targeted) hearing — it never negotiates, so it reaches
    "documents_shared" (refund-eligible, escrow held, a counsel assigned)
    without a commercial lock. The paid + commercially-locked (negotiated)
    cancel-and-refund path is covered in test_cancel_after_payment.py."""
    async def body():
        db = _db()
        import unittest.mock
        with unittest.mock.patch.object(server, "db", db):
            requester, counsel = _user("requester"), _user("counsel")
            hearing_id = None
            try:
                await _insert_user(db, requester)
                await _insert_user(db, counsel)
                hearing = await hearings.create_hearing_request(
                    db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
                )
                hearing_id = hearing["hearing_id"]
                await hearings.initiate_payment(db, hearing_id, requester)
                import escrow
                await escrow.create_and_hold(
                    db, context_type="hearing", context_id=hearing_id, service_id=hearings.ESCROW_SERVICE_ID,
                    matter_id=None, payer_user_id=requester["user_id"], payee_user_id=None,
                    amount=1500.0, platform_commission_pct=0.1,
                    razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
                )
                await hearings.mark_payment_confirmed(db, hearing_id, requester)  # -> broadcast
                await hearings.accept_hearing_request(db, hearing_id, counsel)  # -> documents_shared, escrow assigned

                result = await server.cancel_hearing_request(hearing_id, requester)
                assert result["ok"] is True

                event = await db.notification_events.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
                assert event is not None
                assert event["title"] == "Hearing cancelled"
                assert "refunded" in event["body"].lower()
            finally:
                await _cleanup(db, [requester["user_id"], counsel["user_id"]], [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_cancel_before_payment_notifies_counsel_without_refund_note():
    async def body():
        db = _db()
        import unittest.mock
        with unittest.mock.patch.object(server, "db", db):
            requester, counsel = _user("requester"), _user("counsel")
            hearing_id = None
            try:
                await _insert_user(db, requester)
                await _insert_user(db, counsel)
                hearing = await hearings.create_hearing_request(
                    db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
                    target_advocate_id=counsel["user_id"],
                )
                hearing_id = hearing["hearing_id"]

                await server.cancel_hearing_request(hearing_id, requester)

                event = await db.notification_events.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
                assert event is not None
                assert event["title"] == "Hearing cancelled"
                assert "refunded" not in event["body"].lower()
            finally:
                await _cleanup(db, [requester["user_id"], counsel["user_id"]], [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_admin_cancel_attributes_to_support_and_notifies_requester():
    """Admin Cancel & Refund (B6): the counsel must not be told the requester
    cancelled, and the requester — who didn't cancel — must be told."""
    async def body():
        db = _db()
        import unittest.mock
        with unittest.mock.patch.object(server, "db", db):
            requester, counsel, admin = _user("requester"), _user("counsel"), _user("admin")
            hearing_id = None
            try:
                for u in (requester, counsel, admin):
                    await _insert_user(db, u)
                hearing = await hearings.create_hearing_request(
                    db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
                )
                hearing_id = hearing["hearing_id"]
                await hearings.initiate_payment(db, hearing_id, requester)
                import escrow
                await escrow.create_and_hold(
                    db, context_type="hearing", context_id=hearing_id, service_id=hearings.ESCROW_SERVICE_ID,
                    matter_id=None, payer_user_id=requester["user_id"], payee_user_id=None,
                    amount=1500.0, platform_commission_pct=0.1,
                    razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=f"pay_sim_{uuid.uuid4().hex[:10]}",
                )
                await hearings.mark_payment_confirmed(db, hearing_id, requester)
                await hearings.accept_hearing_request(db, hearing_id, counsel)

                result = await server.cancel_hearing_request(hearing_id, admin)
                assert result["refund_status"] == "refunded"

                to_counsel = await db.notification_events.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
                assert "cancelled by CourtBazaar support" in to_counsel["body"]
                assert "requester." not in to_counsel["body"]
                to_requester = await db.notification_events.find_one({"user_id": requester["user_id"]}, {"_id": 0})
                assert to_requester is not None and to_requester["title"] == "Hearing cancelled"
                assert "has been refunded" in to_requester["body"]
            finally:
                await _cleanup(db, [requester["user_id"], counsel["user_id"], admin["user_id"]],
                               [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_rate_notifies_the_rated_party():
    async def body():
        db = _db()
        import unittest.mock
        with unittest.mock.patch.object(server, "db", db):
            requester, counsel = _user("requester"), _user("counsel")
            hearing_id = None
            try:
                await _insert_user(db, requester)
                await _insert_user(db, counsel)
                hearing = await hearings.create_hearing_request(
                    db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
                    target_advocate_id=counsel["user_id"],
                )
                hearing_id = hearing["hearing_id"]
                await db.hearing_requests.update_one(
                    {"hearing_id": hearing_id}, {"$set": {"status": "completed", "proxy_counsel_user_id": counsel["user_id"]}},
                )

                await server.rate_hearing_request(hearing_id, HearingRatingCreate(rating=5, review="Great"), requester)

                event = await db.notification_events.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
                assert event is not None
                assert event["title"] == "Rating received"
                assert "5-star" in event["body"]
            finally:
                await _cleanup(db, [requester["user_id"], counsel["user_id"]], [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_resolve_dispute_resubmit_notifies_counsel():
    async def body():
        db = _db()
        import unittest.mock
        with unittest.mock.patch.object(server, "db", db):
            requester, counsel, admin = _user("requester"), _user("counsel"), _user("admin")
            hearing_id = None
            try:
                await _insert_user(db, requester)
                await _insert_user(db, counsel)
                hearing = await hearings.create_hearing_request(
                    db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
                    target_advocate_id=counsel["user_id"],
                )
                hearing_id = hearing["hearing_id"]
                await db.hearing_requests.update_one(
                    {"hearing_id": hearing_id}, {"$set": {"status": "disputed", "proxy_counsel_user_id": counsel["user_id"]}},
                )

                await server.resolve_hearing_dispute(hearing_id, HearingDisputeResolve(action="resubmit", remark="Please clarify"), admin)

                event = await db.notification_events.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
                assert event is not None
                assert event["title"] == "Resubmission requested"
                assert "Please clarify" in event["body"]
            finally:
                await _cleanup(db, [requester["user_id"], counsel["user_id"]], [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_resolve_dispute_refund_notifies_both_parties_distinctly():
    async def body():
        db = _db()
        import unittest.mock
        with unittest.mock.patch.object(server, "db", db):
            requester, counsel, admin = _user("requester"), _user("counsel"), _user("admin")
            hearing_id = None
            try:
                await _insert_user(db, requester)
                await _insert_user(db, counsel)
                hearing = await hearings.create_hearing_request(
                    db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
                    target_advocate_id=counsel["user_id"],
                )
                hearing_id = hearing["hearing_id"]
                await db.hearing_requests.update_one(
                    {"hearing_id": hearing_id}, {"$set": {"status": "disputed", "proxy_counsel_user_id": counsel["user_id"]}},
                )
                import escrow
                await escrow.create_and_hold(
                    db, context_type="hearing", context_id=hearing_id, service_id=hearings.ESCROW_SERVICE_ID,
                    matter_id=None, payer_user_id=requester["user_id"], payee_user_id=counsel["user_id"],
                    amount=1500.0, platform_commission_pct=0.1,
                    razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
                )

                await server.resolve_hearing_dispute(hearing_id, HearingDisputeResolve(action="refund", remark=None), admin)

                requester_event = await db.notification_events.find_one({"user_id": requester["user_id"]}, {"_id": 0})
                counsel_event = await db.notification_events.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
                assert requester_event is not None and requester_event["title"] == "Refund issued"
                assert counsel_event is not None and counsel_event["title"] == "Dispute resolved — no payout"
            finally:
                await _cleanup(db, [requester["user_id"], counsel["user_id"]], [hearing_id] if hearing_id else [])
    asyncio.run(body())


# ---------- Bug B: notifications only say "refunded" when it really is ----------

class _refund_gateway:
    """Stub razorpay_svc.refund_payment with a fixed result or exception."""
    def __init__(self, result):
        self.result = result

    def __enter__(self):
        import razorpay_svc
        self._mod, self._orig = razorpay_svc, razorpay_svc.refund_payment

        def _stub(*a, **k):
            if isinstance(self.result, Exception):
                raise self.result
            return self.result
        razorpay_svc.refund_payment = _stub
        return self

    def __exit__(self, *exc):
        self._mod.refund_payment = self._orig


async def _disputed_hearing_with_escrow(db, requester, counsel):
    hearing = await hearings.create_hearing_request(
        db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
        target_advocate_id=counsel["user_id"],
    )
    hearing_id = hearing["hearing_id"]
    await db.hearing_requests.update_one(
        {"hearing_id": hearing_id}, {"$set": {"status": "disputed", "proxy_counsel_user_id": counsel["user_id"]}},
    )
    import escrow
    await escrow.create_and_hold(
        db, context_type="hearing", context_id=hearing_id, service_id=hearings.ESCROW_SERVICE_ID,
        matter_id=None, payer_user_id=requester["user_id"], payee_user_id=counsel["user_id"],
        amount=1500.0, platform_commission_pct=0.1,
        razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=f"pay_live_{uuid.uuid4().hex[:10]}",
    )
    return hearing_id


def test_cancel_with_failed_refund_does_not_claim_refunded():
    async def body():
        db = _db()
        import unittest.mock
        with unittest.mock.patch.object(server, "db", db):
            requester, counsel = _user("requester"), _user("counsel")
            hearing_id = None
            try:
                await _insert_user(db, requester)
                await _insert_user(db, counsel)
                hearing = await hearings.create_hearing_request(
                    db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
                )
                hearing_id = hearing["hearing_id"]
                await hearings.initiate_payment(db, hearing_id, requester)
                import escrow
                await escrow.create_and_hold(
                    db, context_type="hearing", context_id=hearing_id, service_id=hearings.ESCROW_SERVICE_ID,
                    matter_id=None, payer_user_id=requester["user_id"], payee_user_id=None,
                    amount=1500.0, platform_commission_pct=0.1,
                    razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=f"pay_live_{uuid.uuid4().hex[:10]}",
                )
                await hearings.mark_payment_confirmed(db, hearing_id, requester)
                await hearings.accept_hearing_request(db, hearing_id, counsel)

                with _refund_gateway(RuntimeError("gateway down")):
                    result = await server.cancel_hearing_request(hearing_id, requester)
                assert result["ok"] is True and result["refund_status"] == "refund_failed"

                event = await db.notification_events.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
                assert event["title"] == "Hearing cancelled"
                assert "has been refunded" not in event["body"]
                assert "is being refunded to the requester" in event["body"]

                h = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
                notes = [t.get("note", "") for t in h.get("timeline", [])]
                assert any(n.startswith("Refund could not be completed automatically") for n in notes)
                assert not any(n.startswith("Payment refunded") for n in notes)
            finally:
                await _cleanup(db, [requester["user_id"], counsel["user_id"]], [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_resolve_dispute_refund_wording_follows_refund_outcome():
    """Failed or still-processing refund -> "Refund initiated" (not
    "issued"); only a completed refund says "Refund issued"."""
    async def body():
        db = _db()
        import unittest.mock
        with unittest.mock.patch.object(server, "db", db):
            outcomes = [
                (RuntimeError("gateway down"), "refund_failed", "Refund initiated"),
                ({"razorpay_refund_id": "rfnd_p", "status": "pending", "simulated": False}, "refund_processing", "Refund initiated"),
                ({"razorpay_refund_id": "rfnd_ok", "status": "processed", "simulated": False}, "refunded", "Refund issued"),
            ]
            for gateway_result, expected_status, expected_title in outcomes:
                requester, counsel, admin = _user("requester"), _user("counsel"), _user("admin")
                hearing_id = None
                try:
                    await _insert_user(db, requester)
                    await _insert_user(db, counsel)
                    hearing_id = await _disputed_hearing_with_escrow(db, requester, counsel)
                    with _refund_gateway(gateway_result):
                        result = await server.resolve_hearing_dispute(
                            hearing_id, HearingDisputeResolve(action="refund", remark=None), admin)
                    assert result["refund_status"] == expected_status

                    ev = await db.notification_events.find_one({"user_id": requester["user_id"]}, {"_id": 0})
                    assert ev["title"] == expected_title, (expected_status, ev["title"])
                    if expected_status != "refunded":
                        assert "being processed" in ev["body"]
                    counsel_ev = await db.notification_events.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
                    assert counsel_ev["title"] == "Dispute resolved — no payout"
                finally:
                    await _cleanup(db, [requester["user_id"], counsel["user_id"]], [hearing_id] if hearing_id else [])
    asyncio.run(body())
