"""Task 12 — negotiation authorization and consistency, profile/vendor field
exposure, refund permissions. Real routes with real JWTs on the throwaway test
database (harness from test_p7_hiring_workflow); payments are simulated and no
gateway refund is ever requested.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import escrow  # noqa: E402
import hearings  # noqa: E402
import negotiation  # noqa: E402
import server  # noqa: E402
from tests._api_harness import agreed_and_paid, api, create, person, run  # noqa: E402

OFFERS = "/api/hearing-requests/{}/negotiation/offers"
ADMIN_ONLY_ESCROW_FIELDS = ("razorpay_payment_id", "razorpay_order_id", "refund_last_error", "refund_error_history",
                            "refund_last_retry_by", "gateway_refund_id", "payer_user_id", "timeline")


async def negotiation_of(who, hid):
    return (await api("GET", f"/api/hearing-requests/{hid}/negotiation", who))[1]


async def open_request(db, fee=2000.0):
    client = await person(db, "client", "t12client")
    counsel = await person(db, "proxy_counsel", "t12counsel", verified=True)
    st, h = await create(client, counsel, fee=fee)
    assert st == 200, h
    return client, counsel, h["hearing_id"]


# ------------------------------------------------------------------ Negotiation: who may act
def test_only_the_two_parties_can_make_or_accept_offers():
    async def body(db):
        client, counsel, hid = await open_request(db)
        outsider = await person(db, "client", "t12outsider")
        other_counsel = await person(db, "proxy_counsel", "t12other", verified=True)
        admin = await person(db, "admin", "t12admin")
        offer_id = (await negotiation_of(client, hid))["current_offer_id"]
        for who in (outsider, other_counsel):
            assert (await api("GET", f"/api/hearing-requests/{hid}/negotiation", who))[0] == 403
            assert (await api("POST", OFFERS.format(hid), who, {"amount": 2500}))[0] == 403
            assert (await api("POST", f"{OFFERS.format(hid)}/{offer_id}/accept", who))[0] == 403
            assert (await api("PUT", f"/api/hearing-requests/{hid}/end-negotiation", who))[0] in (403, 404)
        assert (await api("POST", OFFERS.format(hid), None, {"amount": 2500}))[0] == 401
        # Admin can read the negotiation but is not a party to it.
        assert (await api("GET", f"/api/hearing-requests/{hid}/negotiation", admin))[0] == 200
        st, res = await api("POST", OFFERS.format(hid), admin, {"amount": 2500})
        assert st == 403 and res["detail"] == negotiation.PARTIES_ONLY_MESSAGE
        assert (await api("POST", f"{OFFERS.format(hid)}/{offer_id}/accept", admin))[0] == 403
        neg = await negotiation_of(client, hid)
        assert neg["status"] == "open" and len(neg["offers"]) == 1 and neg["current_offer_id"] == offer_id
        assert (await db.hearing_requests.find_one({"hearing_id": hid}))["commercially_locked"] is not True
    run(body)


def test_proposer_cannot_accept_own_offer_and_counsel_cannot_end_negotiation():
    async def body(db):
        client, counsel, hid = await open_request(db)
        offer_id = (await negotiation_of(client, hid))["current_offer_id"]
        assert (await api("POST", f"{OFFERS.format(hid)}/{offer_id}/accept", client))[0] == 403
        assert (await api("PUT", f"/api/hearing-requests/{hid}/end-negotiation", counsel))[0] == 403
        assert (await api("PUT", f"/api/hearing-requests/{hid}/end-negotiation", client))[0] == 200
        # Closed: neither side can offer or accept any more.
        assert (await api("POST", OFFERS.format(hid), counsel, {"amount": 2500}))[0] == 400
        assert (await api("POST", f"{OFFERS.format(hid)}/{offer_id}/accept", counsel))[0] == 400
        assert (await api("PUT", f"/api/hearing-requests/{hid}/end-negotiation", client))[0] == 400  # repeat
    run(body)


def test_no_offers_on_a_request_sent_to_no_specific_counsel():
    async def body(db):
        client = await person(db, "client", "t12client")
        admin = await person(db, "admin", "t12admin")
        st, h = await create(client, None, fee=2000.0)
        assert st == 200, h
        st, res = await api("POST", OFFERS.format(h["hearing_id"]), client, {"amount": 1500})
        assert st == 403 and res["detail"] == negotiation.PARTIES_ONLY_MESSAGE
        assert (await api("POST", OFFERS.format(h["hearing_id"]), admin, {"amount": 1500}))[0] == 403
        assert (await db.hearing_requests.find_one({"hearing_id": h["hearing_id"]}))["fee"] == 2000.0
    run(body)


# ------------------------------------------------------------------ Negotiation: transitions
def test_no_offers_once_the_fee_is_agreed_or_paid():
    async def body(db):
        client = await person(db, "client", "t12client")
        counsel = await person(db, "proxy_counsel", "t12counsel", verified=True)
        hid = await agreed_and_paid(db, client, counsel, fee=1500.0)
        for who in (client, counsel):
            st, res = await api("POST", OFFERS.format(hid), who, {"amount": 1300})
            assert st == 400 and res["detail"] == negotiation.NOT_NEGOTIABLE_MESSAGE
        neg = await negotiation_of(client, hid)
        assert neg["status"] == "agreed" and len(neg["offers"]) == 1
        st, _ = await api("POST", f"{OFFERS.format(hid)}/{neg['current_offer_id']}/accept", counsel)
        assert st == 400  # accepting again changes nothing
        assert (await db.hearing_requests.find_one({"hearing_id": hid}))["fee"] == 1500.0
        assert (await db.escrow_transactions.find_one({"context_id": hid}))["amount"] == 1500.0
    run(body)


def test_no_offers_after_the_counsel_accepted_the_listed_rate():
    async def body(db):
        client, counsel, hid = await open_request(db)
        st, res = await api("PUT", f"/api/hearing-requests/{hid}/accept-listed-rate", counsel)
        assert st == 200, res
        for who in (client, counsel):
            st, res = await api("POST", OFFERS.format(hid), who, {"amount": 2600})
            assert st == 400 and res["detail"] == negotiation.FEE_ALREADY_AGREED_MESSAGE
        neg = await negotiation_of(client, hid)
        assert len(neg["offers"]) == 1
        st, _ = await api("POST", f"{OFFERS.format(hid)}/{neg['current_offer_id']}/accept", counsel)
        assert st == 409  # the opening offer can't replace the agreed fee
        assert (await db.hearing_requests.find_one({"hearing_id": hid}))["fee"] == 1200.0  # the listed rate
    run(body)


def test_stale_offer_cannot_be_accepted():
    async def body(db):
        client, counsel, hid = await open_request(db)
        first = (await negotiation_of(client, hid))["current_offer_id"]
        assert (await api("POST", OFFERS.format(hid), counsel, {"amount": 2600}))[0] == 200
        st, _ = await api("POST", f"{OFFERS.format(hid)}/{first}/accept", counsel)
        assert st == 409
        assert (await api("POST", f"{OFFERS.format(hid)}/offer_does_not_exist/accept", client))[0] == 409
        neg = await negotiation_of(client, hid)
        assert neg["status"] == "open" and [o["status"] for o in neg["offers"]] == ["superseded", "active"]
    run(body)


# ------------------------------------------------------------------ Negotiation: duplicates and concurrency
def test_same_offer_sent_twice_is_recorded_once():
    async def body(db):
        client, counsel, hid = await open_request(db)
        for _ in range(2):
            assert (await api("POST", OFFERS.format(hid), counsel, {"amount": 2600, "note": "My rate"}))[0] == 200
        neg = await negotiation_of(client, hid)
        assert [o["amount"] for o in neg["offers"]] == [2000.0, 2600.0]
        assert len([e for e in neg["timeline"] if e["event"] == "offer_proposed"]) == 2
        # A different amount is a new offer.
        assert (await api("POST", OFFERS.format(hid), counsel, {"amount": 2700, "note": "My rate"}))[0] == 200
        assert len((await negotiation_of(client, hid))["offers"]) == 3
    run(body)


def test_concurrent_offers_leave_exactly_one_active():
    async def body(db):
        client, counsel, hid = await open_request(db)
        results = await asyncio.gather(*[
            api("POST", OFFERS.format(hid), who, {"amount": amount})
            for who, amount in ((client, 2100), (counsel, 2900), (client, 2200), (counsel, 2800))])
        codes = sorted(st for st, _ in results)
        assert set(codes) <= {200, 409} and codes.count(200) >= 1, codes
        neg = await negotiation_of(client, hid)
        active = [o for o in neg["offers"] if o["status"] == "active"]
        assert len(active) == 1 and active[0]["offer_id"] == neg["current_offer_id"]
        assert len(neg["offers"]) == 1 + codes.count(200)
    run(body)


def test_offer_racing_an_agreement_is_refused(monkeypatch):
    """The offer read the negotiation as open, then the agreement landed: the
    write must lose, not append an offer to an agreed negotiation."""
    async def body(db):
        client, counsel, hid = await open_request(db)
        offer_id = (await negotiation_of(client, hid))["current_offer_id"]
        real = negotiation.get_or_create_negotiation

        async def agreed_meanwhile(db_, hearing_id):
            neg = await real(db_, hearing_id)
            await db_.negotiations.update_one({"hearing_id": hearing_id}, {"$set": {"status": "agreed", "offers.0.status": "accepted"}})
            return neg
        monkeypatch.setattr(negotiation, "get_or_create_negotiation", agreed_meanwhile)
        st, res = await api("POST", OFFERS.format(hid), client, {"amount": 2100})
        assert st == 409 and res["detail"] == negotiation.STALE_NEGOTIATION_MESSAGE
        stored = await db.negotiations.find_one({"hearing_id": hid})
        assert len(stored["offers"]) == 1 and stored["current_offer_id"] == offer_id
    run(body)


def test_concurrent_accepts_agree_once():
    async def body(db):
        client, counsel, hid = await open_request(db)
        offer_id = (await negotiation_of(client, hid))["current_offer_id"]
        results = await asyncio.gather(*[api("POST", f"{OFFERS.format(hid)}/{offer_id}/accept", counsel) for _ in range(4)])
        assert sorted(st for st, _ in results).count(200) == 1
        neg = await negotiation_of(client, hid)
        assert neg["status"] == "agreed" and neg["locked_amount"] == 2000.0
        assert len([e for e in neg["timeline"] if e["event"] == "negotiation_agreed"]) == 1
        hearing = await db.hearing_requests.find_one({"hearing_id": hid})
        assert hearing["commercially_locked"] is True and hearing["fee"] == 2000.0
    run(body)


# ------------------------------------------------------------------ Negotiation: input
@pytest.mark.parametrize("payload", [
    {"amount": 0}, {"amount": -500}, {"amount": "abc"}, {}, {"amount": server.NEGOTIATION_OFFER_MAX_INR + 1},
    {"amount": 2500, "note": "x" * (server.NEGOTIATION_NOTE_MAX_CHARS + 1)},
])
def test_invalid_offer_is_rejected(payload):
    async def body(db):
        client, counsel, hid = await open_request(db)
        assert (await api("POST", OFFERS.format(hid), counsel, payload))[0] == 422
        assert len((await negotiation_of(client, hid))["offers"]) == 1
    run(body)


@pytest.mark.parametrize("amount", [float("inf"), float("nan")])
def test_offer_amount_must_be_a_real_number(amount):
    with pytest.raises(ValueError):
        server.NegotiationOfferCreate(amount=amount)


def test_note_text_is_stored_as_text():
    async def body(db):
        client, counsel, hid = await open_request(db)
        note = "$offers and $$ROOT {\"$set\": 1} <script>"
        assert (await api("POST", OFFERS.format(hid), counsel, {"amount": 2600, "note": note}))[0] == 200
        neg = await negotiation_of(client, hid)
        assert neg["offers"][-1]["note"] == note and neg["offers"][0]["status"] == "superseded"
    run(body)


def test_offer_below_the_platform_minimum_is_rejected():
    async def body(db):
        client, counsel, hid = await open_request(db)
        st, res = await api("POST", OFFERS.format(hid), counsel, {"amount": 100})
        assert st == 400 and "minimum" in res["detail"]
    run(body)


# ------------------------------------------------------------------ Profile visibility
def test_counsel_profile_cards_carry_no_contact_or_kyc_fields():
    async def body(db):
        client, counsel, hid = await open_request(db)
        await db.users.update_one({"user_id": counsel.id}, {"$set": {"phone": "9999911111"}})
        await db.proxy_counsel_profiles.update_one({"user_id": counsel.id}, {"$set": {
            "bar_council_number": "D/1234/2010", "office_address": "2 Test Lane", "state_bar_council": "Delhi"}})
        cards = [
            (await api("GET", f"/api/public/proxy-counsels/{counsel.id}/profile"))[1],
            (await api("GET", f"/api/advocates/{counsel.id}/profile", client))[1],
            (await api("GET", f"/api/hearing-requests/{hid}/counsel-profile", client))[1],
            next(a for a in (await api("GET", "/api/public/proxy-counsels"))[1]["advocates"] if a["advocate_id"] == counsel.id),
        ]
        for card in cards:
            text = str(card)
            for private in ("9999911111", "D/1234/2010", "2 Test Lane", "@example.com", "kyc_status", "bar_council"):
                assert private not in text, private
    run(body)


def test_profile_of_a_counsel_who_lost_verification():
    async def body(db):
        client, counsel, hid = await open_request(db)
        outsider = await person(db, "client", "t12outsider")
        assert (await api("GET", f"/api/hearing-requests/{hid}/counsel-profile", client))[1]["verified"] is True
        assert (await api("GET", f"/api/hearing-requests/{hid}/counsel-profile", outsider))[0] == 403
        await db.proxy_counsel_profiles.update_one({"user_id": counsel.id}, {"$set": {"bar_council_verified": False}})
        # Gone from every listing and direct profile lookup...
        assert (await api("GET", f"/api/public/proxy-counsels/{counsel.id}/profile"))[0] == 404
        assert (await api("GET", f"/api/advocates/{counsel.id}/profile", client))[0] == 404
        assert counsel.id not in {a["advocate_id"] for a in (await api("GET", "/api/public/proxy-counsels"))[1]["advocates"]}
        # ...and the client's own request no longer shows them as verified.
        st, card = await api("GET", f"/api/hearing-requests/{hid}/counsel-profile", client)
        assert st == 200 and card["verified"] is False
    run(body)


def test_client_identity_stays_hidden_from_open_pool_counsel():
    async def body(db):
        client = await person(db, "client", "t12client")
        await db.users.update_one({"user_id": client.id}, {"$set": {"phone": "9999922222"}})
        counsel = await person(db, "proxy_counsel", "t12counsel", verified=True)
        pool = await person(db, "proxy_counsel", "t12pool", verified=True)
        hid = await agreed_and_paid(db, client, counsel)
        await db.hearing_requests.update_one({"hearing_id": hid}, {"$set": {"target_advocate_id": None}})  # open to the pool
        st, seen = await api("GET", f"/api/hearing-requests/{hid}", pool)
        assert st == 200
        for private in ("9999922222", "@example.com", "T12 t12client"):
            assert private not in str(seen)
    run(body)


# ------------------------------------------------------------------ Refunds
def test_escrow_details_by_role():
    async def body(db):
        client = await person(db, "client", "t12client")
        counsel = await person(db, "proxy_counsel", "t12counsel", verified=True)
        pool = await person(db, "proxy_counsel", "t12pool", verified=True)
        outsider = await person(db, "client", "t12outsider")
        admin = await person(db, "admin", "t12admin")
        hid = await agreed_and_paid(db, client, counsel)
        assert (await api("PUT", f"/api/hearing-requests/{hid}/accept", counsel))[0] == 200
        await db.escrow_transactions.update_one({"context_id": hid}, {"$set": {
            "refund_last_error": "gateway said no: key rzp_test_x", "refund_error_history": [{"error": "boom"}],
            "refund_last_retry_by": admin.id, "gateway_refund_id": "rfnd_t12"}})
        for who in (client, counsel):
            st, esc = await api("GET", f"/api/hearing-requests/{hid}/escrow", who)
            assert st == 200 and esc["status"] == "held" and esc["amount"] == 1500.0
            assert not set(esc) & set(ADMIN_ONLY_ESCROW_FIELDS), sorted(esc)
        st, esc = await api("GET", f"/api/hearing-requests/{hid}/escrow", admin)
        assert st == 200 and esc["refund_last_error"] and esc["gateway_refund_id"] == "rfnd_t12"
        # An open-pool counsel can still open a broadcast request on main, so it
        # reaches this endpoint too — but only ever gets the party view.
        st, esc = await api("GET", f"/api/hearing-requests/{hid}/escrow", pool)
        assert st in (200, 403, 404)
        if st == 200:
            assert not set(esc) & set(ADMIN_ONLY_ESCROW_FIELDS), sorted(esc)
        assert (await api("GET", f"/api/hearing-requests/{hid}/escrow", outsider))[0] in (403, 404)
        assert (await api("GET", f"/api/hearing-requests/{hid}/escrow"))[0] == 401
    run(body)


def test_only_admin_can_retry_sync_or_resolve_a_refund():
    async def body(db):
        client = await person(db, "client", "t12client")
        counsel = await person(db, "proxy_counsel", "t12counsel", verified=True)
        hid = await agreed_and_paid(db, client, counsel)
        escrow_id = (await db.escrow_transactions.find_one({"context_id": hid}))["escrow_id"]
        calls = (("POST", f"/api/admin/escrow-transactions/{escrow_id}/retry-refund", None),
                 ("POST", f"/api/admin/escrow-transactions/{escrow_id}/sync-refund", None),
                 ("POST", "/api/admin/payments/order_t12/retry-orphan-refund", None),
                 ("PUT", f"/api/hearing-requests/{hid}/resolve-dispute", {"action": "refund"}),
                 ("GET", "/api/admin/escrow-transactions", None), ("GET", "/api/admin/reconciliation", None))
        for method, path, payload in calls:
            for who in (client, counsel):
                assert (await api(method, path, who, payload))[0] == 403, path
            assert (await api(method, path, None, payload))[0] == 401, path
        stored = await db.escrow_transactions.find_one({"context_id": hid})
        assert stored["status"] == "held" and not stored.get("refund_attempts")
        assert (await db.hearing_requests.find_one({"hearing_id": hid}))["status"] == "broadcast"
    run(body)


def test_admin_retry_and_sync_change_nothing_when_no_refund_is_owed():
    async def body(db):
        client = await person(db, "client", "t12client")
        counsel = await person(db, "proxy_counsel", "t12counsel", verified=True)
        admin = await person(db, "admin", "t12admin")
        hid = await agreed_and_paid(db, client, counsel)
        escrow_id = (await db.escrow_transactions.find_one({"context_id": hid}))["escrow_id"]
        assert (await api("POST", f"/api/admin/escrow-transactions/{escrow_id}/retry-refund", admin))[0] == 400
        assert (await api("POST", "/api/admin/escrow-transactions/escrow_missing/retry-refund", admin))[0] == 404
        st, _ = await api("POST", f"/api/admin/escrow-transactions/{escrow_id}/sync-refund", admin)
        assert st in (200, 400)
        stored = await db.escrow_transactions.find_one({"context_id": hid})
        assert stored["status"] == "held" and not stored.get("refund_attempts")
    run(body)


async def _disputed(db):
    client = await person(db, "client", "t12client")
    counsel = await person(db, "proxy_counsel", "t12counsel", verified=True)
    admin = await person(db, "admin", "t12admin")
    hid = await agreed_and_paid(db, client, counsel)
    await db.hearing_requests.update_one({"hearing_id": hid}, {"$set": {"status": "disputed", "proxy_counsel_user_id": counsel.id}})
    return client, counsel, admin, hid


@pytest.mark.parametrize("action", ["release", "resubmitt", "", "REFUND", None])
def test_unknown_dispute_resolution_never_refunds(action):
    async def body(db):
        client, counsel, admin, hid = await _disputed(db)
        st, _ = await api("PUT", f"/api/hearing-requests/{hid}/resolve-dispute", admin, {"action": action})
        assert st == 422
        with pytest.raises(hearings.HTTPException) as exc:  # the module refuses it too, not only the request model
            await hearings.resolve_dispute(db, hid, {"user_id": admin.id, "role": "admin"}, action)
        assert exc.value.status_code == 400
        assert (await db.hearing_requests.find_one({"hearing_id": hid}))["status"] == "disputed"
        assert (await db.escrow_transactions.find_one({"context_id": hid}))["status"] == "held"
    run(body)


def test_dispute_refund_happens_once(monkeypatch):
    async def body(db):
        client, counsel, admin, hid = await _disputed(db)
        gateway_calls = []
        monkeypatch.setattr(escrow.razorpay_svc, "refund_payment", lambda *a, **k: gateway_calls.append(a) or {"status": "processed"})
        results = await asyncio.gather(*[
            api("PUT", f"/api/hearing-requests/{hid}/resolve-dispute", admin, {"action": "refund", "remark": "Order sheet was wrong"})
            for _ in range(3)])
        codes = sorted(st for st, _ in results)
        assert codes.count(200) == 1 and set(codes) <= {200, 400, 409}, codes  # the repeats are refused
        stored = await db.escrow_transactions.find_one({"context_id": hid})
        assert stored["status"] == "refunded" and stored["refund_attempts"] == 1
        assert gateway_calls == []  # simulated payment: the gateway is never called
        assert (await db.hearing_requests.find_one({"hearing_id": hid}))["status"] == "cancelled"
        # The client sees the refund, without the admin-only details.
        esc = (await api("GET", f"/api/hearing-requests/{hid}/escrow", client))[1]
        assert esc["status"] == "refunded" and esc["refund_completed_at"] and "refund_reason" not in esc
    run(body)


def test_paid_cancel_refunds_once_and_parties_cannot_set_refund_status():
    async def body(db):
        client = await person(db, "client", "t12client")
        counsel = await person(db, "proxy_counsel", "t12counsel", verified=True)
        hid = await agreed_and_paid(db, client, counsel)
        assert (await api("PUT", f"/api/hearing-requests/{hid}/cancel", counsel))[0] == 403
        results = await asyncio.gather(*[api("PUT", f"/api/hearing-requests/{hid}/cancel", client) for _ in range(3)])
        assert sorted(st for st, _ in results).count(200) == 1
        stored = await db.escrow_transactions.find_one({"context_id": hid})
        assert stored["status"] == "refunded" and stored["refund_attempts"] == 1
        # No route lets a party write a refund status: unsigned gateway events are refused.
        st, _ = await api("POST", "/api/payments/razorpay/webhook", client,
                          {"event": "refund.failed", "payload": {"refund": {"entity": {"id": "rfnd_x", "payment_id": "pay_x"}}}})
        assert st == 400
        assert (await db.escrow_transactions.find_one({"context_id": hid}))["status"] == "refunded"
    run(body)
