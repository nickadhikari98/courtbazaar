"""Task 12 — the client is told where a refund stands, once per stage, and only
what the gateway actually reported: initiated (accepted, not yet processed),
completed (processed) or delayed (failed). Real routes on the throwaway test
database; the Razorpay calls are stubbed, so no refund is ever requested.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import escrow  # noqa: E402
import notifications  # noqa: E402
import server  # noqa: E402
from tests._api_harness import agreed_and_paid, api, person, run  # noqa: E402

REFUND_TITLES = ("Refund initiated", "Refund completed", "Refund delayed")
PAYMENT_ID, REFUND_ID = "pay_T12notify", "rfnd_T12notify"


async def notices(db, user_id, hearing_id):
    return [(n["title"], n["body"]) for n in await db.notification_events.find(
        {"user_id": user_id, "related_entity_id": hearing_id}, {"_id": 0}).sort("created_at", 1).to_list(100)]


async def refund_titles(db, user_id, hearing_id):
    return [t for t, _ in await notices(db, user_id, hearing_id) if t in REFUND_TITLES]


class Gateway:
    """Stands in for Razorpay: `answer` is what a refund request returns (or
    raises); `state` is what a later status check of that refund reports."""

    def __init__(self, monkeypatch, answer, state="pending"):
        self.answer, self.state, self.created = answer, state, 0  # created: refunds the gateway accepted
        monkeypatch.setattr(escrow.razorpay_svc, "refund_payment", self._refund)
        monkeypatch.setattr(escrow.razorpay_svc, "fetch_refund", lambda payment_id, refund_id: {
            "razorpay_refund_id": refund_id, "status": self.state, "amount_inr": 1500.0, "notes": {}})
        monkeypatch.setattr(escrow.razorpay_svc, "fetch_refunds", lambda payment_id: (
            [] if not self.created else [{"razorpay_refund_id": REFUND_ID, "status": self.state, "amount_inr": 1500.0}]))

    def _refund(self, *args, **kwargs):
        if isinstance(self.answer, Exception):
            raise self.answer
        self.created += 1
        return self.answer


async def paid(db, real_payment=True, client_fields=None):
    client = await person(db, "client", "t12nclient")
    if client_fields is not None:
        await db.users.update_one({"user_id": client.id}, {"$set": client_fields.get("set", {}), "$unset": client_fields.get("unset", {})})
    counsel = await person(db, "proxy_counsel", "t12ncounsel", verified=True)
    admin = await person(db, "admin", "t12nadmin")
    hid = await agreed_and_paid(db, client, counsel)
    if real_payment:  # not simulated: the refund goes through the (stubbed) gateway
        await db.escrow_transactions.update_one({"context_id": hid}, {"$set": {"razorpay_payment_id": PAYMENT_ID}})
    escrow_id = (await db.escrow_transactions.find_one({"context_id": hid}))["escrow_id"]
    return client, counsel, admin, hid, escrow_id


PENDING = {"razorpay_refund_id": REFUND_ID, "status": "pending", "simulated": False}
PROCESSED = {"razorpay_refund_id": REFUND_ID, "status": "processed", "simulated": False}


# ------------------------------------------------------------------ client cancellation
def test_client_cancel_tells_the_client_the_refund_was_initiated_not_completed(monkeypatch):
    async def body(db):
        client, counsel, admin, hid, _ = await paid(db)
        Gateway(monkeypatch, PENDING)
        st, res = await api("PUT", f"/api/hearing-requests/{hid}/cancel", client)
        assert st == 200 and res["refund_status"] == "refund_processing"
        assert await refund_titles(db, client.id, hid) == ["Refund initiated"]
        body_text = dict(await notices(db, client.id, hid))["Refund initiated"]
        assert "Rs.1500" in body_text and "initiated" in body_text and "completed and sent" not in body_text
        for private in (PAYMENT_ID, REFUND_ID, "rzp_", "order_"):
            assert private not in body_text
        # The counsel hears about the cancellation, without a claim that the refund is done.
        to_counsel = dict(await notices(db, counsel.id, hid))["Hearing cancelled"]
        assert "cancelled by the requester" in to_counsel and "being refunded" in to_counsel
        assert "has been refunded" not in to_counsel
        assert await refund_titles(db, counsel.id, hid) == []  # refund notices are the payer's
    run(body)


def test_client_cancel_of_a_simulated_payment_says_completed_once():
    async def body(db):
        client, counsel, admin, hid, _ = await paid(db, real_payment=False)
        results = await asyncio.gather(*[api("PUT", f"/api/hearing-requests/{hid}/cancel", client) for _ in range(3)])
        assert sorted(st for st, _ in results).count(200) == 1
        assert await refund_titles(db, client.id, hid) == ["Refund completed"]
        assert "has been refunded" in dict(await notices(db, counsel.id, hid))["Hearing cancelled"]
    run(body)


def test_failed_refund_is_reported_as_delayed_never_as_refunded(monkeypatch):
    async def body(db):
        client, counsel, admin, hid, escrow_id = await paid(db)
        Gateway(monkeypatch, RuntimeError("gateway down: key rzp_test_secretvalue"))
        st, res = await api("PUT", f"/api/hearing-requests/{hid}/cancel", client)
        assert st == 200 and res["refund_status"] == "refund_failed"
        assert await refund_titles(db, client.id, hid) == ["Refund delayed"]
        text = str(await notices(db, client.id, hid))
        assert "gateway down" not in text and "rzp_test" not in text  # the error itself stays with admin
        # Admin retries twice and it fails again: the client is not told again.
        for _ in range(2):
            st, res = await api("POST", f"/api/admin/escrow-transactions/{escrow_id}/retry-refund", admin)
            assert st == 200 and res["status"] == "refund_failed"
        assert await refund_titles(db, client.id, hid) == ["Refund delayed"]
    run(body)


# ------------------------------------------------------------------ admin retry / sync
def test_admin_retry_notifies_by_the_gateway_answer_not_by_the_click(monkeypatch):
    async def body(db):
        client, counsel, admin, hid, escrow_id = await paid(db)
        gateway = Gateway(monkeypatch, RuntimeError("timeout"))
        assert (await api("PUT", f"/api/hearing-requests/{hid}/cancel", client))[1]["refund_status"] == "refund_failed"
        # Retry: Razorpay accepts the refund but has not processed it.
        gateway.answer = PENDING
        st, res = await api("POST", f"/api/admin/escrow-transactions/{escrow_id}/retry-refund", admin)
        assert st == 200 and res["status"] == "refund_processing"
        assert await refund_titles(db, client.id, hid) == ["Refund delayed", "Refund initiated"]
        # Retry again while it is still pending at the gateway: nothing new to say.
        st, res = await api("POST", f"/api/admin/escrow-transactions/{escrow_id}/retry-refund", admin)
        assert st == 200 and res["status"] == "refund_processing"
        assert await refund_titles(db, client.id, hid) == ["Refund delayed", "Refund initiated"]
        assert "Refund completed" not in await refund_titles(db, client.id, hid)
    run(body)


def test_repeated_sync_notifies_completion_exactly_once(monkeypatch):
    async def body(db):
        client, counsel, admin, hid, escrow_id = await paid(db)
        gateway = Gateway(monkeypatch, PENDING)
        assert (await api("PUT", f"/api/hearing-requests/{hid}/cancel", client))[1]["refund_status"] == "refund_processing"
        for _ in range(3):  # still pending at Razorpay
            st, res = await api("POST", f"/api/admin/escrow-transactions/{escrow_id}/sync-refund", admin)
            assert st == 200 and res["refund_sync"] == "still_pending"
        assert await refund_titles(db, client.id, hid) == ["Refund initiated"]
        gateway.state = "processed"
        st, res = await api("POST", f"/api/admin/escrow-transactions/{escrow_id}/sync-refund", admin)
        assert st == 200 and res["refund_sync"] == "settled" and res["status"] == "refunded"
        for _ in range(3):  # already settled
            assert (await api("POST", f"/api/admin/escrow-transactions/{escrow_id}/sync-refund", admin))[0] == 200
        assert await refund_titles(db, client.id, hid) == ["Refund initiated", "Refund completed"]
    run(body)


def test_scheduler_sync_also_notifies_completion_once(monkeypatch):
    async def body(db):
        client, counsel, admin, hid, escrow_id = await paid(db)
        gateway = Gateway(monkeypatch, PENDING)
        await api("PUT", f"/api/hearing-requests/{hid}/cancel", client)
        monkeypatch.setattr(escrow, "REFUND_SYNC_MIN_AGE_MINUTES", 0)
        gateway.state = "processed"
        await escrow.sync_processing_refunds(db)
        await escrow.sync_processing_refunds(db)
        assert (await db.escrow_transactions.find_one({"escrow_id": escrow_id}))["status"] == "refunded"
        assert await refund_titles(db, client.id, hid) == ["Refund initiated", "Refund completed"]
    run(body)


# ------------------------------------------------------------------ gateway confirmation (webhook)
@pytest.mark.parametrize("event,final_status,expected", [
    ("refund.processed", "refunded", ["Refund initiated", "Refund completed"]),
    ("refund.failed", "refund_failed", ["Refund initiated", "Refund delayed"]),
])
def test_gateway_event_notifies_once_even_when_delivered_repeatedly(monkeypatch, event, final_status, expected):
    async def body(db):
        client, counsel, admin, hid, escrow_id = await paid(db)
        Gateway(monkeypatch, PENDING)
        await api("PUT", f"/api/hearing-requests/{hid}/cancel", client)
        entity = {"id": REFUND_ID, "payment_id": PAYMENT_ID, "notes": {"escrow_id": escrow_id, "refund_attempt": 1}}
        results = await asyncio.gather(*[server.payment_svc.apply_refund_event(db, entity, event) for _ in range(4)])
        assert sum(1 for r in results if r.get("changed")) == 1
        assert (await db.escrow_transactions.find_one({"escrow_id": escrow_id}))["status"] == final_status
        assert await refund_titles(db, client.id, hid) == expected
        stored = await db.escrow_transactions.find_one({"escrow_id": escrow_id})
        assert sorted(stored["refund_notified"]) == sorted({"refund_processing", final_status})
    run(body)


def test_a_failed_refund_that_later_succeeds_is_then_reported_completed(monkeypatch):
    async def body(db):
        client, counsel, admin, hid, escrow_id = await paid(db)
        gateway = Gateway(monkeypatch, RuntimeError("timeout"))
        await api("PUT", f"/api/hearing-requests/{hid}/cancel", client)
        gateway.answer = PROCESSED
        st, res = await api("POST", f"/api/admin/escrow-transactions/{escrow_id}/retry-refund", admin)
        assert st == 200 and res["status"] == "refunded"
        assert await refund_titles(db, client.id, hid) == ["Refund delayed", "Refund completed"]
    run(body)


# ------------------------------------------------------------------ admin cancel and dispute refund
def test_admin_cancel_and_refund_sends_one_cancellation_and_one_refund_notice(monkeypatch):
    async def body(db):
        client, counsel, admin, hid, _ = await paid(db)
        Gateway(monkeypatch, PROCESSED)
        st, res = await api("PUT", f"/api/hearing-requests/{hid}/cancel", admin)
        assert st == 200 and res["refund_status"] == "refunded"
        got = await notices(db, client.id, hid)
        cancelled = [b for t, b in got if t == "Hearing cancelled"]
        assert len(cancelled) == 1 and "cancelled by CourtBazaar support" in cancelled[0] and "refund" not in cancelled[0].lower()
        assert await refund_titles(db, client.id, hid) == ["Refund completed"]
    run(body)


def test_dispute_refund_reports_the_decision_and_the_refund_status_separately(monkeypatch):
    async def body(db):
        client, counsel, admin, hid, _ = await paid(db)
        await db.hearing_requests.update_one({"hearing_id": hid}, {"$set": {"status": "disputed", "proxy_counsel_user_id": counsel.id}})
        Gateway(monkeypatch, PENDING)
        st, res = await api("PUT", f"/api/hearing-requests/{hid}/resolve-dispute", admin, {"action": "refund"})
        assert st == 200 and res["refund_status"] == "refund_processing"
        titles = [t for t, _ in await notices(db, client.id, hid)]
        assert titles.count("Dispute resolved — refund approved") == 1
        assert await refund_titles(db, client.id, hid) == ["Refund initiated"]
        to_counsel = dict(await notices(db, counsel.id, hid))["Dispute resolved — no payout"]
        assert "is being returned" in to_counsel and "was refunded" not in to_counsel
    run(body)


def test_resubmit_sends_no_refund_notice():
    async def body(db):
        client, counsel, admin, hid, _ = await paid(db, real_payment=False)
        await db.hearing_requests.update_one({"hearing_id": hid}, {"$set": {"status": "disputed", "proxy_counsel_user_id": counsel.id}})
        st, _ = await api("PUT", f"/api/hearing-requests/{hid}/resolve-dispute", admin, {"action": "resubmit"})
        assert st == 200
        assert await refund_titles(db, client.id, hid) == []
        assert (await db.escrow_transactions.find_one({"context_id": hid}))["status"] == "held"
        assert "Resubmission requested" in [t for t, _ in await notices(db, counsel.id, hid)]
    run(body)


# ------------------------------------------------------------------ channels
@pytest.mark.parametrize("fields,emails_expected", [
    ({"unset": {"email": ""}}, 0),                                    # no email on the account
    ({"set": {"email": ""}}, 0),                                      # blank email
    ({"set": {"notif_prefs": {"sms": True, "whatsapp": True, "email": False}}}, 0),  # email turned off
    ({}, 1),                                                          # has an email and allows it
])
def test_email_goes_only_to_a_client_who_has_one_and_allows_it(monkeypatch, fields, emails_expected):
    async def body(db):
        sent = []
        monkeypatch.setattr(notifications, "send_email", lambda to, subject, *a, **k: sent.append((to, subject)) or {"status": "mocked"})
        client, counsel, admin, hid, _ = await paid(db, real_payment=False, client_fields=fields)
        sent.clear()
        assert (await api("PUT", f"/api/hearing-requests/{hid}/cancel", client))[0] == 200
        to_client = [s for s in sent if s[0] and s[0].startswith(client.id)]
        assert len(to_client) == emails_expected, sent
        assert await refund_titles(db, client.id, hid) == ["Refund completed"]  # always saved in the app
    run(body)


def test_a_notification_failure_never_blocks_the_refund(monkeypatch):
    async def body(db):
        client, counsel, admin, hid, escrow_id = await paid(db, real_payment=False)

        async def broken(db_, escrow_row):
            raise RuntimeError("notification service down")
        monkeypatch.setattr(escrow, "refund_status_listener", broken)
        st, res = await api("PUT", f"/api/hearing-requests/{hid}/cancel", client)
        assert st == 200 and res["refund_status"] == "refunded"
        assert (await db.escrow_transactions.find_one({"escrow_id": escrow_id}))["status"] == "refunded"
    run(body)
