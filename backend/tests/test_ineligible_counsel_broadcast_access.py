"""H2: only a currently eligible Proxy Counsel (verified + not deactivated, the
same counsel_matching.eligible_counsel_query gate as the public listing) may
see the open broadcast pool or a request targeted at them, or take on new work
(accept, accept-at-listed-rate, admin assignment).

The can_practice_proxy_counsel capability alone isn't enough: it comes from
professional_profile_types and survives a verification revocation. Work
already assigned to a counsel stays visible to them (they must be able to
finish or hand it over); requester, plain advocate and admin access are
unchanged.

Same pattern as test_decline_authorization.py: hearings.py / server.py
functions called directly, server.db patched to the per-session test DB.
"""
import asyncio
import os
import sys
import unittest.mock
import uuid

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import counsel_matching  # noqa: E402
import escrow  # noqa: E402
import hearings  # noqa: E402
import negotiation  # noqa: E402
import practice  # noqa: E402
import server  # noqa: E402
from tests._verified_counsel import verify_counsel  # noqa: E402

MSG = "Your Proxy Counsel verification isn't active, so you can't accept requests."


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _uid(prefix):
    return f"test_h2_{prefix}_{uuid.uuid4().hex[:10]}"


def _counsel(prefix="counsel"):
    return {"user_id": _uid(prefix), "role": "advocate", "capabilities": ["can_practice_proxy_counsel", "can_hire_proxy_counsel"]}


def _client(prefix="client"):
    return {"user_id": _uid(prefix), "role": "client", "capabilities": ["can_hire_proxy_counsel"]}


ADMIN = {"user_id": "test_h2_admin", "role": "admin", "capabilities": ["is_admin"]}


async def _make_ineligible(db, user_id, how):
    if how == "pending_kyc":
        await db.proxy_counsel_profiles.update_one({"user_id": user_id}, {"$set": {"kyc_status": "pending"}})
    elif how == "rejected_kyc":
        await practice.revoke_verification(db, user_id)  # what a lead rejection does (PR #71)
    elif how == "bar_revoked":
        await db.proxy_counsel_profiles.update_one({"user_id": user_id}, {"$set": {"bar_council_verified": False}})
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

    def next_date(self):
        """A new date per request: one requester can't hold two active
        requests to the same counsel/court/date (hearings.dedupe_key)."""
        return f"2026-08-{len(self.hearing_ids) + 1:02d}"

    async def paid(self, requester, target=None):
        """A paid request: status "broadcast" (targeted or not)."""
        db = self.db
        hearing = await hearings.create_hearing_request(
            db, requester["user_id"], "court_tishazari", self.next_date(), "H2 test case", 1500.0, None,
            target_advocate_id=target["user_id"] if target else None,
        )
        hearing_id = hearing["hearing_id"]
        self.hearing_ids.append(hearing_id)
        if target:  # a targeted fee must be agreed first; same call negotiation/accept-at-listed-rate make
            assert await hearings.set_negotiated_fee(db, hearing_id, 1500.0)
        await hearings.initiate_payment(db, hearing_id, requester)
        await escrow.create_and_hold(
            db, context_type="hearing", context_id=hearing_id, service_id=hearings.ESCROW_SERVICE_ID,
            matter_id=None, payer_user_id=requester["user_id"], payee_user_id=None, amount=1500.0,
            platform_commission_pct=0.1, razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}",
            razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
        )
        await hearings.mark_payment_confirmed(db, hearing_id, requester)
        return hearing_id

    async def requested(self, requester, target):
        hearing = await hearings.create_hearing_request(
            self.db, requester["user_id"], "court_tishazari", self.next_date(), "H2 test case", 1500.0, None,
            target_advocate_id=target["user_id"],
        )
        self.hearing_ids.append(hearing["hearing_id"])
        return hearing["hearing_id"]

    async def cleanup(self):
        db, ids = self.db, self.hearing_ids
        if ids:
            for coll in ("hearing_requests", "escrow_transactions", "counsel_matching_log", "negotiations",
                         "hearing_documents", "hearing_messages"):
                key = "context_id" if coll == "escrow_transactions" else "hearing_id"
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


async def _http_get(path, token):
    """A real GET through server.app (routing, middleware, get_current_user)
    as a raw ASGI call — FastAPI's TestClient needs httpx, which isn't a
    project dependency. No lifespan event is sent, so no scheduler starts."""
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
        "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
        "headers": [(b"host", b"testserver"), (b"authorization", f"Bearer {token}".encode())],
        "server": ("testserver", 80), "client": ("127.0.0.1", 50000),
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await server.app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    return status, b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body").decode()


async def _listed(db, user, hearing_id):
    return hearing_id in {h["hearing_id"] for h in await hearings.list_hearing_requests(db, user)}


# 1 -------------------------------------------------------------------------
def test_eligible_counsel_sees_and_accepts_broadcast():
    async def body(db, ctx):
        requester, counsel = ctx.track(_client(), _counsel())
        await verify_counsel(db, counsel["user_id"])
        hearing_id = await ctx.paid(requester)

        assert await _listed(db, counsel, hearing_id)
        assert (await hearings.get_hearing_request(db, hearing_id, counsel))["status"] == "broadcast"
        assert await server.get_hearing_documents(hearing_id, counsel) == []
        accepted = await server.accept_hearing_request(hearing_id, counsel)
        assert accepted["proxy_counsel_user_id"] == counsel["user_id"]
    _run(body)


# 2-5 -----------------------------------------------------------------------
@pytest.mark.parametrize("how", ["pending_kyc", "rejected_kyc", "bar_revoked", "deactivated"])
def test_ineligible_counsel_cannot_see_or_accept_broadcast(how):
    async def body(db, ctx):
        requester, counsel = ctx.track(_client(), _counsel())
        await verify_counsel(db, counsel["user_id"])
        await _make_ineligible(db, counsel["user_id"], how)
        hearing_id = await ctx.paid(requester)

        assert not await _listed(db, counsel, hearing_id)
        await _expect(403, hearings.get_hearing_request(db, hearing_id, counsel))
        await _expect(403, server.get_hearing_documents(hearing_id, counsel))
        assert await _expect(403, hearings.accept_hearing_request(db, hearing_id, counsel)) == MSG
        hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
        assert hearing["status"] == "broadcast" and hearing["proxy_counsel_user_id"] is None
        assert (await practice.performance(db, counsel["user_id"]))["pending_requests"] == 0  # A4
    _run(body)


# 5b ------------------------------------------------------------------------
def test_deactivated_counsel_api_request_gets_401_without_hearing_data():
    async def body(db, ctx):
        requester, counsel = ctx.track(_client(), _counsel())
        await db.users.insert_one({
            "user_id": counsel["user_id"], "name": "H2 Counsel", "role": "advocate",
            "professional_profile_types": ["advocate", "proxy_counsel"],
        })
        await verify_counsel(db, counsel["user_id"])
        hearing_id = await ctx.paid(requester)
        token = server.make_jwt(counsel["user_id"], "advocate")
        paths = ["/api/hearing-requests", f"/api/hearing-requests/{hearing_id}",
                 f"/api/hearing-requests/{hearing_id}/documents"]

        # Control: the same request path does return the hearing while the account is active.
        status, text = await _http_get(paths[0], token)
        assert status == 200 and hearing_id in text

        await db.users.update_one({"user_id": counsel["user_id"]}, {"$set": {"deleted": True}})
        for path in paths:
            status, text = await _http_get(path, token)
            assert status == 401, (path, status)
            assert "deactivated" in text
            assert hearing_id not in text and "H2 test case" not in text and "court_tishazari" not in text
    _run(body)


# 6 -------------------------------------------------------------------------
def test_direct_api_accept_by_ineligible_counsel_is_rejected():
    async def body(db, ctx):
        requester, counsel = ctx.track(_client(), _counsel())
        await verify_counsel(db, counsel["user_id"])
        await practice.revoke_verification(db, counsel["user_id"])
        hearing_id = await ctx.paid(requester)

        # The route only checks the capability, which the revoked counsel still has.
        assert await _expect(403, server.accept_hearing_request(hearing_id, counsel)) == MSG
        hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
        assert hearing["status"] == "broadcast" and hearing["proxy_counsel_user_id"] is None
    _run(body)


# 7 -------------------------------------------------------------------------
def test_assigned_counsel_keeps_access_after_revocation():
    async def body(db, ctx):
        requester, counsel = ctx.track(_client(), _counsel())
        await verify_counsel(db, counsel["user_id"])
        hearing_id = await ctx.paid(requester)
        await hearings.accept_hearing_request(db, hearing_id, counsel)
        await practice.revoke_verification(db, counsel["user_id"])

        assert await _listed(db, counsel, hearing_id)
        assert (await hearings.get_hearing_request(db, hearing_id, counsel))["proxy_counsel_user_id"] == counsel["user_id"]
        assert await server.get_hearing_documents(hearing_id, counsel) == []
    _run(body)


# 7b ------------------------------------------------------------------------
# Every status an assigned hearing can move through after accept (accept itself
# lands on documents_shared). Deactivated is left out: a deactivated account
# can't authenticate at all (5b), which is intended.
ASSIGNED_LATER_STATUSES = ("documents_shared", "preparation", "hearing_scheduled", "hearing_completed",
                           "verification_pending", "disputed", "verified", "completed", "rated")


@pytest.mark.parametrize("how", ["pending_kyc", "rejected_kyc", "bar_revoked"])
def test_ineligible_counsel_keeps_assigned_hearing_documents_and_thread_through_later_statuses(how):
    async def body(db, ctx):
        requester, counsel = ctx.track(_client(), _counsel())
        await verify_counsel(db, counsel["user_id"])
        hearing_id = await ctx.paid(requester)
        assert (await hearings.accept_hearing_request(db, hearing_id, counsel))["status"] == "documents_shared"
        doc_id = f"doc_{uuid.uuid4().hex[:10]}"
        await db.hearing_documents.insert_one({
            "doc_id": doc_id, "hearing_id": hearing_id, "is_deleted": False, "kind": "case_document",
            "storage_path": f"hearings/{hearing_id}/brief.pdf", "original_filename": "brief.pdf",
        })
        await hearings.add_message(db, hearing_id, requester, "Brief attached")
        await _make_ineligible(db, counsel["user_id"], how)

        with unittest.mock.patch.object(server, "presigned_download_url", lambda path, **kw: f"https://storage.test/{path}"):
            for status in ASSIGNED_LATER_STATUSES:
                # Status set directly: this checks read access per status; the
                # transitions themselves are covered by the lifecycle tests.
                await db.hearing_requests.update_one({"hearing_id": hearing_id}, {"$set": {"status": status}})
                assert await _listed(db, counsel, hearing_id), status
                assert (await hearings.get_hearing_request(db, hearing_id, counsel))["status"] == status
                assert [d["doc_id"] for d in await server.get_hearing_documents(hearing_id, counsel)] == [doc_id]
                assert (await server.get_hearing_document_url(hearing_id, doc_id, False, counsel))["filename"] == "brief.pdf"
                assert [m["text"] for m in await server.list_hearing_messages(hearing_id, counsel)] == ["Brief attached"]
        # Still no new work for them.
        other_id = await ctx.paid(requester)
        assert not await _listed(db, counsel, other_id)
        assert await _expect(403, hearings.accept_hearing_request(db, other_id, counsel)) == MSG
        assert (await practice.performance(db, counsel["user_id"]))["pending_requests"] == 0
    _run(body)


# 8 -------------------------------------------------------------------------
def test_requester_and_plain_advocate_unchanged():
    async def body(db, ctx):
        requester, = ctx.track(_client())
        plain_advocate = {"user_id": _uid("advocate"), "role": "advocate", "capabilities": ["can_hire_proxy_counsel"]}
        hearing_id = await ctx.paid(requester)

        assert await _listed(db, requester, hearing_id)
        assert (await hearings.get_hearing_request(db, hearing_id, requester))["status"] == "broadcast"
        assert await server.get_hearing_documents(hearing_id, requester) == []
        assert not await _listed(db, plain_advocate, hearing_id)
        await _expect(403, hearings.get_hearing_request(db, hearing_id, plain_advocate))
    _run(body)


# 9 -------------------------------------------------------------------------
def test_admin_view_unchanged_and_assign_requires_eligible_counsel():
    async def body(db, ctx):
        requester, eligible, ineligible = ctx.track(_client(), _counsel("eligible"), _counsel("ineligible"))
        await verify_counsel(db, eligible["user_id"])
        await verify_counsel(db, ineligible["user_id"])
        await practice.revoke_verification(db, ineligible["user_id"])
        hearing_id = await ctx.paid(requester)

        assert (await hearings.get_hearing_request(db, hearing_id, ADMIN))["status"] == "broadcast"
        assert await _expect(403, counsel_matching.admin_assign_counsel(db, hearing_id, ineligible["user_id"], ADMIN)) == MSG
        assigned = await counsel_matching.admin_assign_counsel(db, hearing_id, eligible["user_id"], ADMIN)
        assert assigned["proxy_counsel_user_id"] == eligible["user_id"]
    _run(body)


# 10 ------------------------------------------------------------------------
def test_targeted_request_eligible_target_only():
    async def body(db, ctx):
        requester, target, other = ctx.track(_client(), _counsel("target"), _counsel("other"))
        await verify_counsel(db, target["user_id"])
        await verify_counsel(db, other["user_id"])

        pending_id = await ctx.requested(requester, target)  # pre-payment negotiation window
        assert await _listed(db, target, pending_id)
        assert (await hearings.get_hearing_request(db, pending_id, target))["status"] == "requested"
        assert not await _listed(db, other, pending_id)
        await _expect(403, hearings.get_hearing_request(db, pending_id, other))

        paid_id = await ctx.paid(requester, target=target)
        assert await _listed(db, target, paid_id) and not await _listed(db, other, paid_id)
        await _expect(403, hearings.accept_hearing_request(db, paid_id, other))  # not sent to them
        assert (await hearings.accept_hearing_request(db, paid_id, target))["proxy_counsel_user_id"] == target["user_id"]

        # Target's verification lapses after the request was created (A2).
        await practice.revoke_verification(db, target["user_id"])
        assert not await _listed(db, target, pending_id)
        await _expect(403, hearings.get_hearing_request(db, pending_id, target))
        assert await _expect(403, hearings.accept_at_listed_rate(db, pending_id, target)) == MSG
        paid_again = await ctx.paid(requester, target=other)
        await practice.revoke_verification(db, other["user_id"])
        assert not await _listed(db, other, paid_again)
        assert await _expect(403, hearings.accept_hearing_request(db, paid_again, other)) == MSG
    _run(body)


# 11 ------------------------------------------------------------------------
def test_concurrent_accept_exactly_one_wins():
    async def body(db, ctx):
        requester, a, b = ctx.track(_client(), _counsel("a"), _counsel("b"))
        await verify_counsel(db, a["user_id"])
        await verify_counsel(db, b["user_id"])
        hearing_id = await ctx.paid(requester)

        results = await asyncio.gather(
            hearings.accept_hearing_request(db, hearing_id, a),
            hearings.accept_hearing_request(db, hearing_id, b),
            return_exceptions=True,
        )
        wins = [r for r in results if isinstance(r, dict)]
        losses = [r for r in results if isinstance(r, HTTPException)]
        assert len(wins) == 1 and len(losses) == 1 and losses[0].status_code == 409
        hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
        assert hearing["proxy_counsel_user_id"] == wins[0]["proxy_counsel_user_id"]
    _run(body)


# A4 ------------------------------------------------------------------------
def test_performance_counts_only_this_counsels_open_pool():
    async def body(db, ctx):
        requester, counsel, other = ctx.track(_client(), _counsel(), _counsel("other"))
        await verify_counsel(db, counsel["user_id"])
        await verify_counsel(db, other["user_id"])
        before = (await practice.performance(db, counsel["user_id"]))["pending_requests"]
        await ctx.paid(requester, target=other)  # targeted at someone else: not counted
        assert (await practice.performance(db, counsel["user_id"]))["pending_requests"] == before
        await ctx.paid(requester)  # untargeted: counted
        assert (await practice.performance(db, counsel["user_id"]))["pending_requests"] == before + 1
    _run(body)


# Negotiation (targeted, pre-payment) ----------------------------------------
async def _negotiable(db, ctx, requester, target):
    """A targeted request whose counsel negotiates fees (snapshotted at creation)."""
    await db.proxy_counsel_profiles.update_one(
        {"user_id": target["user_id"]}, {"$set": {"negotiation_enabled": True}}, upsert=True)
    await verify_counsel(db, target["user_id"])
    hearing_id = await ctx.requested(requester, target)
    assert (await db.hearing_requests.find_one({"hearing_id": hearing_id}))["negotiation_enabled"] is True
    return hearing_id


def test_eligible_target_and_requester_negotiate_normally():
    async def body(db, ctx):
        requester, target = ctx.track(_client(), _counsel("target"))
        hearing_id = await _negotiable(db, ctx, requester, target)

        await negotiation.propose_offer(db, hearing_id, requester, 3000.0, None)
        assert (await negotiation.get_negotiation_for_user(db, hearing_id, target))["status"] == "open"
        await negotiation.propose_offer(db, hearing_id, target, 3500.0, "Counter")
        await negotiation.propose_offer(db, hearing_id, requester, 3200.0, None)
        offer_id = (await negotiation.get_negotiation_for_user(db, hearing_id, requester))["current_offer_id"]
        agreed = await negotiation.accept_offer(db, hearing_id, offer_id, target)
        assert agreed["status"] == "agreed" and agreed["locked_amount"] == 3200.0
        assert (await db.hearing_requests.find_one({"hearing_id": hearing_id}))["commercially_locked"] is True
    _run(body)


def test_ineligible_target_cannot_view_or_negotiate_but_requester_can():
    async def body(db, ctx):
        requester, target = ctx.track(_client(), _counsel("target"))
        hearing_id = await _negotiable(db, ctx, requester, target)
        await negotiation.propose_offer(db, hearing_id, requester, 3000.0, None)
        offer_id = (await negotiation.get_negotiation(db, hearing_id))["current_offer_id"]
        await practice.revoke_verification(db, target["user_id"])  # lapses after the request was sent

        assert await _expect(403, negotiation.get_negotiation_for_user(db, hearing_id, target)) == MSG
        assert await _expect(403, negotiation.propose_offer(db, hearing_id, target, 3500.0, None)) == MSG
        assert await _expect(403, negotiation.accept_offer(db, hearing_id, offer_id, target)) == MSG
        assert await _expect(403, server.get_negotiation(hearing_id, target)) == MSG  # route level

        # Requester unaffected; nothing was agreed or locked.
        neg = await negotiation.get_negotiation_for_user(db, hearing_id, requester)
        assert neg["status"] == "open" and neg["current_offer_id"] == offer_id
        await negotiation.propose_offer(db, hearing_id, requester, 3100.0, None)
        assert not (await db.hearing_requests.find_one({"hearing_id": hearing_id})).get("commercially_locked")
    _run(body)


def test_ineligible_target_can_still_reject_and_others_cannot():
    async def body(db, ctx):
        requester, target, other = ctx.track(_client(), _counsel("target"), _counsel("other"))
        await verify_counsel(db, other["user_id"])
        hearing_id = await _negotiable(db, ctx, requester, target)
        await practice.revoke_verification(db, target["user_id"])

        await _expect(403, server.reject_hearing_request(hearing_id, other))  # not sent to them
        await _expect(403, server.reject_hearing_request(hearing_id, requester))  # no counsel capability
        result = await server.reject_hearing_request(hearing_id, target)
        assert result["status"] == "rejected"
        assert (await db.hearing_requests.find_one({"hearing_id": hearing_id}))["status"] == "rejected"
    _run(body)
