"""Paid targeted request escalation (founder decisions D1–D5, 2026-11).

A targeted request never opens a matching session, so before this change a
paid request whose chosen counsel lapsed (or never accepted) sat in
"broadcast" with nobody able to take it, no escalation, and — after the
client's 1-hour window — no way for the client to cancel.

Same pattern as test_ineligible_counsel_broadcast_access.py: hearings /
counsel_matching / server functions called directly, server.db patched to the
per-session throwaway test DB (conftest: email/SMS/WhatsApp mocked, Razorpay
simulated, outbound network blocked).
"""
import asyncio
import os
import sys
import unittest.mock
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import counsel_matching  # noqa: E402
import escrow  # noqa: E402
import hearings  # noqa: E402
import practice  # noqa: E402
import server  # noqa: E402
from tests._verified_counsel import verify_counsel  # noqa: E402

INELIGIBLE, TIMEOUT = counsel_matching.TARGETED_INELIGIBLE, counsel_matching.TARGETED_TIMEOUT


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _uid(prefix):
    return f"test_esc_{prefix}_{uuid.uuid4().hex[:10]}"


def _counsel(prefix="counsel"):
    return {"user_id": _uid(prefix), "role": "advocate", "capabilities": ["can_practice_proxy_counsel", "can_hire_proxy_counsel"]}


def _client(prefix="client"):
    return {"user_id": _uid(prefix), "role": "client", "capabilities": ["can_hire_proxy_counsel"]}


ADMIN = {"user_id": "test_esc_admin", "role": "admin", "capabilities": ["is_admin"]}


async def _make_ineligible(db, user_id, how):
    if how == "revoked":
        await practice.revoke_verification(db, user_id)
    elif how == "deactivated":
        await db.users.update_one({"user_id": user_id}, {"$set": {"deleted": True}}, upsert=True)
    else:
        raise AssertionError(how)


class _Ctx:
    def __init__(self, db):
        self.db = db
        self.hearing_ids, self.user_ids = [], []

    def track(self, *users):
        self.user_ids += [u["user_id"] for u in users]
        return users

    async def locked(self, requester, target):
        """A targeted request with its fee agreed, not yet paid."""
        await verify_counsel(self.db, target["user_id"])
        hearing = await hearings.create_hearing_request(
            self.db, requester["user_id"], "court_tishazari", "2026-08-01", "Escalation test", 1500.0, None,
            target_advocate_id=target["user_id"],
        )
        self.hearing_ids.append(hearing["hearing_id"])
        assert await hearings.set_negotiated_fee(self.db, hearing["hearing_id"], 1500.0)
        return hearing["hearing_id"]

    async def paid(self, requester, target, paid_ago=None):
        """A paid targeted request ("broadcast", escrow held). paid_ago backdates
        payment_confirmed_at (the 1-hour client window and the 24h timeout)."""
        db = self.db
        hearing_id = await self.locked(requester, target)
        await hearings.initiate_payment(db, hearing_id, requester)
        await escrow.create_and_hold(
            db, context_type="hearing", context_id=hearing_id, service_id=hearings.ESCROW_SERVICE_ID,
            matter_id=None, payer_user_id=requester["user_id"], payee_user_id=None, amount=1500.0,
            platform_commission_pct=0.1, razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}",
            razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
        )
        await hearings.mark_payment_confirmed(db, hearing_id, requester)
        if paid_ago is not None:
            at = (datetime.now(timezone.utc) - paid_ago).isoformat()
            await db.hearing_requests.update_one({"hearing_id": hearing_id}, {"$set": {"payment_confirmed_at": at}})
        return hearing_id

    async def cleanup(self):
        db, ids = self.db, self.hearing_ids
        if ids:
            for coll, key in (("hearing_requests", "hearing_id"), ("escrow_transactions", "context_id"),
                              ("counsel_matching_log", "hearing_id"), ("negotiations", "hearing_id"),
                              ("notification_events", "entity_id")):
                await db[coll].delete_many({key: {"$in": ids}})
            await db.audit_log.delete_many({"details.hearing_id": {"$in": ids}})
        if self.user_ids:
            await db.proxy_counsel_profiles.delete_many({"user_id": {"$in": self.user_ids}})
            await db.users.delete_many({"user_id": {"$in": self.user_ids}})


def _run(body):
    async def wrapper():
        db = _db()
        ctx = _Ctx(db)
        with unittest.mock.patch.object(server, "db", db):
            try:
                await body(db, ctx)
            finally:
                await ctx.cleanup()
    asyncio.run(wrapper())


async def _expect(status_code, coro):
    with pytest.raises(HTTPException) as exc_info:
        await coro
    assert exc_info.value.status_code == status_code
    return exc_info.value.detail


async def _hearing(db, hearing_id):
    return await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})


async def _escrow(db, hearing_id):
    return await db.escrow_transactions.find_one({"context_id": hearing_id}, {"_id": 0})


async def _watchdog_ids(db, now=None):
    return {item["hearing"]["hearing_id"]: item["reason"]
            for item in await counsel_matching.check_stalled_targeted_requests(db, now=now)}


# --- D2: target lapses BEFORE payment ---------------------------------------
@pytest.mark.parametrize("how", ["revoked", "deactivated"])
def test_target_lapsed_before_payment_blocks_payment_and_allows_cancel(how):
    async def body(db, ctx):
        requester, target = ctx.track(_client(), _counsel("target"))
        hearing_id = await ctx.locked(requester, target)
        await _make_ineligible(db, target["user_id"], how)

        assert (await hearings.get_hearing_request(db, hearing_id, requester))["target_unavailable"] is True
        assert await _expect(400, hearings.initiate_payment(db, hearing_id, requester)) == hearings.TARGET_UNAVAILABLE_MESSAGE
        result = await hearings.cancel_hearing_request(db, hearing_id, requester)  # fee-locked, yet cancellable
        assert result == {"ok": True}  # nothing was paid, nothing to refund
        assert (await _hearing(db, hearing_id))["status"] == "cancelled"
        assert await _escrow(db, hearing_id) is None
    _run(body)


def test_eligible_target_locked_request_unchanged():
    async def body(db, ctx):
        requester, target = ctx.track(_client(), _counsel("target"))
        hearing_id = await ctx.locked(requester, target)
        assert (await hearings.get_hearing_request(db, hearing_id, requester))["target_unavailable"] is False
        await _expect(400, hearings.cancel_hearing_request(db, hearing_id, requester))  # still "proceed to payment"
        assert (await hearings.initiate_payment(db, hearing_id, requester))["status"] == "payment_pending"
    _run(body)


# --- D1: target lapses AFTER payment -> immediate escalation ------------------
@pytest.mark.parametrize("how", ["revoked", "deactivated"])
def test_target_lapsed_after_payment_escalates_immediately(how):
    async def body(db, ctx):
        requester, target = ctx.track(_client(), _counsel("target"))
        hearing_id = await ctx.paid(requester, target)
        assert hearing_id not in await _watchdog_ids(db)  # eligible and fresh: left alone
        await _make_ineligible(db, target["user_id"], how)

        assert (await _watchdog_ids(db))[hearing_id] == INELIGIBLE
        h = await _hearing(db, hearing_id)
        assert h["status"] == "broadcast" and h["targeted_escalated_at"] and h["targeted_escalation_reason"] == INELIGIBLE
        assert h["admin_grace_deadline_at"] and h["targeted_escalation_recorded"] is True
        session = await db.counsel_matching_log.find_one({"hearing_id": hearing_id})
        assert session["status"] == "escalated" and session["final_decision"] == INELIGIBLE
        listed = await server.admin_list_hearing_requests(user=ADMIN, status=None, escalated=True)
        assert hearing_id in {x["hearing_id"] for x in listed}
        assert (await _escrow(db, hearing_id))["status"] == "held"  # D6: no automatic refund
    _run(body)


# --- D1: eligible target, 24h acceptance timeout -----------------------------
def test_eligible_target_accepting_within_24h_is_never_escalated():
    async def body(db, ctx):
        requester, target = ctx.track(_client(), _counsel("target"))
        hearing_id = await ctx.paid(requester, target, paid_ago=timedelta(hours=23))
        assert hearing_id not in await _watchdog_ids(db)
        await hearings.accept_hearing_request(db, hearing_id, target)
        later = datetime.now(timezone.utc) + timedelta(hours=48)
        assert hearing_id not in await _watchdog_ids(db, now=later)  # accepted: no longer a candidate
        assert not (await _hearing(db, hearing_id)).get("targeted_escalated_at")
    _run(body)


def test_eligible_target_not_accepting_within_24h_is_escalated():
    async def body(db, ctx):
        requester, target = ctx.track(_client(), _counsel("target"))
        hearing_id = await ctx.paid(requester, target, paid_ago=timedelta(hours=25))
        assert (await _watchdog_ids(db))[hearing_id] == TIMEOUT
        # The eligible counsel can still accept late; the request is then assigned normally.
        accepted = await hearings.accept_hearing_request(db, hearing_id, target)
        assert accepted["proxy_counsel_user_id"] == target["user_id"]
    _run(body)


# --- Idempotency and races ---------------------------------------------------
def test_duplicate_and_concurrent_watchdog_runs_escalate_once():
    async def body(db, ctx):
        requester, target = ctx.track(_client(), _counsel("target"))
        hearing_id = await ctx.paid(requester, target)
        await practice.revoke_verification(db, target["user_id"])

        runs = await asyncio.gather(*(counsel_matching.check_stalled_targeted_requests(db) for _ in range(3)))
        winners = [item for run in runs for item in run if item["hearing"]["hearing_id"] == hearing_id]
        assert len(winners) == 1
        assert hearing_id not in await _watchdog_ids(db)  # a later run finds nothing to do
        assert await db.counsel_matching_log.count_documents({"hearing_id": hearing_id}) == 1
        assert await db.audit_log.count_documents({"action": "matching.escalated", "details.hearing_id": hearing_id}) == 1
    _run(body)


def test_failed_escalation_recording_is_retried_without_a_second_escalation():
    async def body(db, ctx):
        requester, target = ctx.track(_client(), _counsel("target"))
        hearing_id = await ctx.paid(requester, target)
        await practice.revoke_verification(db, target["user_id"])

        with unittest.mock.patch.object(counsel_matching, "escalate_to_admin", side_effect=RuntimeError("db blip")):
            assert hearing_id not in await _watchdog_ids(db)  # claimed, but recording failed
        h = await _hearing(db, hearing_id)
        assert h["targeted_escalated_at"] and not h.get("targeted_escalation_recorded")
        assert hearing_id not in await _watchdog_ids(db)  # too fresh to retry; not re-escalated either

        later = datetime.now(timezone.utc) + counsel_matching.TARGETED_RETRY_AFTER + timedelta(minutes=1)
        assert hearing_id not in await _watchdog_ids(db, now=later)  # retried silently (no new escalation result)
        assert (await _hearing(db, hearing_id))["targeted_escalation_recorded"] is True
        session = await db.counsel_matching_log.find_one({"hearing_id": hearing_id})
        assert session["status"] == "escalated"
    _run(body)


def test_concurrent_acceptance_and_escalation_stay_consistent():
    async def body(db, ctx):
        requester, target = ctx.track(_client(), _counsel("target"))
        hearing_id = await ctx.paid(requester, target, paid_ago=timedelta(hours=25))
        accepted, escalated = await asyncio.gather(
            hearings.accept_hearing_request(db, hearing_id, target),
            counsel_matching.escalate_targeted_request(db, hearing_id, TIMEOUT),
            return_exceptions=True,
        )
        assert isinstance(accepted, dict) and accepted["proxy_counsel_user_id"] == target["user_id"]
        assert escalated is None or isinstance(escalated, dict)
        h = await _hearing(db, hearing_id)
        assert h["proxy_counsel_user_id"] == target["user_id"] and h["status"] != "broadcast"
        assert not hearings.is_escalated_unassigned(h)  # D4's after-window cancel no longer applies
        assert await counsel_matching.escalate_targeted_request(db, hearing_id, TIMEOUT) is None
    _run(body)


# --- D4: client cancel after escalation --------------------------------------
def test_client_can_cancel_escalated_request_after_window_and_is_refunded():
    async def body(db, ctx):
        requester, target, other_target = ctx.track(_client(), _counsel("target"), _counsel("other"))
        escalated_id = await ctx.paid(requester, target, paid_ago=timedelta(hours=2))
        normal_id = await ctx.paid(requester, other_target, paid_ago=timedelta(hours=2))
        await practice.revoke_verification(db, target["user_id"])
        assert escalated_id in await _watchdog_ids(db)

        # Not escalated: the 1-hour window still applies (unchanged behaviour).
        assert await _expect(400, hearings.cancel_hearing_request(db, normal_id, requester)) == hearings.CLIENT_CANCEL_WINDOW_EXPIRED_MESSAGE
        result = await hearings.cancel_hearing_request(db, escalated_id, requester)
        assert result["ok"] is True and result["refund_status"] == "refunded"
        assert (await _hearing(db, escalated_id))["status"] == "cancelled"
        assert (await _escrow(db, escalated_id))["status"] == "refunded"
    _run(body)


def test_concurrent_client_and_admin_cancel_refund_exactly_once():
    async def body(db, ctx):
        requester, target = ctx.track(_client(), _counsel("target"))
        hearing_id = await ctx.paid(requester, target, paid_ago=timedelta(hours=2))
        await practice.revoke_verification(db, target["user_id"])
        assert hearing_id in await _watchdog_ids(db)

        with unittest.mock.patch.object(escrow, "refund", wraps=escrow.refund) as spy:
            results = await asyncio.gather(
                hearings.cancel_hearing_request(db, hearing_id, requester),
                hearings.cancel_hearing_request(db, hearing_id, ADMIN),
                return_exceptions=True,
            )
        assert len([r for r in results if isinstance(r, dict)]) == 1
        assert all(isinstance(r, dict) or (isinstance(r, HTTPException) and r.status_code in (400, 409)) for r in results)
        assert spy.call_count == 1
        assert (await _escrow(db, hearing_id))["status"] == "refunded"
    _run(body)


# --- D3: admin reassignment with client consent ------------------------------
def test_admin_reassignment_requires_client_consent_and_assigns_new_counsel():
    async def body(db, ctx):
        requester, target, replacement = ctx.track(_client(), _counsel("target"), _counsel("replacement"))
        await verify_counsel(db, replacement["user_id"])
        hearing_id = await ctx.paid(requester, target)
        await practice.revoke_verification(db, target["user_id"])
        assert hearing_id in await _watchdog_ids(db)

        proposed = await counsel_matching.propose_reassignment(db, hearing_id, replacement["user_id"], ADMIN)
        assert proposed["reassignment_proposal"]["counsel_user_id"] == replacement["user_id"]
        assert proposed["target_advocate_id"] == target["user_id"]  # nothing changes before consent
        await _expect(403, counsel_matching.respond_to_reassignment(db, hearing_id, replacement, True))  # not the client

        # Declining clears the proposal; admin can propose again.
        assert (await counsel_matching.respond_to_reassignment(db, hearing_id, requester, False))["status"] == "declined"
        assert (await _hearing(db, hearing_id))["reassignment_proposal"] is None
        await counsel_matching.propose_reassignment(db, hearing_id, replacement["user_id"], ADMIN)

        assigned = await counsel_matching.respond_to_reassignment(db, hearing_id, requester, True)
        assert assigned["proxy_counsel_user_id"] == replacement["user_id"]
        h = await _hearing(db, hearing_id)
        assert h["target_advocate_id"] == replacement["user_id"] and h["previous_target_advocate_id"] == target["user_id"]
        assert (await _escrow(db, hearing_id))["payee_user_id"] == replacement["user_id"]
        for action in ("matching.reassignment_proposed", "matching.reassignment_declined", "matching.reassigned"):
            assert await db.audit_log.count_documents({"action": action, "details.hearing_id": hearing_id}) >= 1
    _run(body)


def test_reassignment_rejects_ineligible_counsel_and_invalid_states():
    async def body(db, ctx):
        requester, target, lapsed, replacement = ctx.track(
            _client(), _counsel("target"), _counsel("lapsed"), _counsel("replacement"))
        await verify_counsel(db, lapsed["user_id"])
        await practice.revoke_verification(db, lapsed["user_id"])
        await verify_counsel(db, replacement["user_id"])
        hearing_id = await ctx.paid(requester, target)

        # Not escalated yet: no reassignment.
        assert await _expect(400, counsel_matching.propose_reassignment(db, hearing_id, replacement["user_id"], ADMIN)) == counsel_matching.REASSIGN_NOT_OPEN
        await practice.revoke_verification(db, target["user_id"])
        assert hearing_id in await _watchdog_ids(db)

        assert await _expect(403, counsel_matching.propose_reassignment(db, hearing_id, lapsed["user_id"], ADMIN)) == counsel_matching.REASSIGN_COUNSEL_INELIGIBLE
        await _expect(400, counsel_matching.propose_reassignment(db, hearing_id, target["user_id"], ADMIN))  # the original counsel
        await counsel_matching.propose_reassignment(db, hearing_id, replacement["user_id"], ADMIN)
        await _expect(409, counsel_matching.propose_reassignment(db, hearing_id, replacement["user_id"], ADMIN))  # one pending

        # The replacement lapses before the client approves: refused, nothing assigned.
        await practice.revoke_verification(db, replacement["user_id"])
        await _expect(409, counsel_matching.respond_to_reassignment(db, hearing_id, requester, True))
        h = await _hearing(db, hearing_id)
        assert h["proxy_counsel_user_id"] is None and h["reassignment_proposal"] is None
        assert h["target_advocate_id"] == target["user_id"]
    _run(body)


# --- D5: notifications, exactly once -----------------------------------------
def test_escalation_and_proposal_notifications_are_sent_once():
    async def body(db, ctx):
        requester, target, replacement = ctx.track(_client(), _counsel("target"), _counsel("replacement"))
        admin_user = {"user_id": _uid("admin"), "role": "admin", "name": "Esc Admin"}
        ctx.track(admin_user)
        await db.users.insert_one(dict(admin_user))
        await verify_counsel(db, replacement["user_id"])
        hearing_id = await ctx.paid(requester, target)
        await practice.revoke_verification(db, target["user_id"])

        sent = []

        async def record(user_id, title, body_text, hid):
            if hid == hearing_id:
                sent.append((user_id, title))

        with unittest.mock.patch.object(server, "_notify_hearing_event", side_effect=record):
            for _ in range(3):  # what the scheduler job does on every 10s tick
                for item in await counsel_matching.check_stalled_targeted_requests(db):
                    await server._notify_targeted_escalation(item["hearing"], item["reason"])
            await server.admin_propose_reassignment(hearing_id, server.AdminAssignCounsel(counsel_user_id=replacement["user_id"]), ADMIN)
            await _expect(409, server.admin_propose_reassignment(
                hearing_id, server.AdminAssignCounsel(counsel_user_id=replacement["user_id"]), ADMIN))
            await server.respond_to_reassignment(hearing_id, server.ReassignmentResponse(approve=True), requester)

        assert sent.count((requester["user_id"], "We're arranging your counsel")) == 1
        assert sent.count((admin_user["user_id"], "Paid request needs action")) == 1
        assert sent.count((requester["user_id"], "Approve your replacement counsel")) == 1
        assert sent.count((requester["user_id"], "Counsel assigned")) == 1
        assert sent.count((replacement["user_id"], "New hearing assigned")) == 1
    _run(body)


# --- Broadcast matching untouched --------------------------------------------
def test_untargeted_broadcast_requests_are_ignored_by_the_targeted_watchdog():
    async def body(db, ctx):
        requester, = ctx.track(_client())
        hearing = await hearings.create_hearing_request(
            db, requester["user_id"], "court_tishazari", "2026-08-01", "Escalation test", 1500.0, None)
        hearing_id = hearing["hearing_id"]
        ctx.hearing_ids.append(hearing_id)
        await hearings.initiate_payment(db, hearing_id, requester)
        await escrow.create_and_hold(
            db, context_type="hearing", context_id=hearing_id, service_id=hearings.ESCROW_SERVICE_ID,
            matter_id=None, payer_user_id=requester["user_id"], payee_user_id=None, amount=1500.0,
            platform_commission_pct=0.1, razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}",
            razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
        )
        await hearings.mark_payment_confirmed(db, hearing_id, requester)
        before = await db.counsel_matching_log.find_one({"hearing_id": hearing_id}, {"_id": 0})
        far_future = datetime.now(timezone.utc) + timedelta(days=7)
        assert hearing_id not in await _watchdog_ids(db, now=far_future)
        after = await db.counsel_matching_log.find_one({"hearing_id": hearing_id}, {"_id": 0})
        assert after == before  # the broadcast session (if any) is untouched
        assert not (await _hearing(db, hearing_id)).get("targeted_escalated_at")
    _run(body)
