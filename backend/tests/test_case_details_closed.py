"""B6 — hearings.submit_case_details refused on a closed hearing.

The frontend hides the Share Case Details form once a hearing is cancelled/
rejected/expired; this pins the same rule server-side, so a direct API call
can't attach a case brief to a closed request. Active paid hearings (and the
still-open "disputed" state) keep the existing behaviour.

Same conventions/fixtures as test_cancel_after_payment.py: Motor directly,
asyncio.run() wrappers, payment through the real capture path, Razorpay
refund stubbed. "rejected"/"expired" are set directly on the test record:
"expired" has no job that drives it yet, and a counsel can't reject a paid,
fee-locked hearing — what's under test is the status guard, not how the
hearing got there.
"""
import asyncio

import pytest
from fastapi import HTTPException

import hearings
from tests.test_cancel_after_payment import _Fixture, _db, _hearing, _refund_stub, _user

DETAILS = {
    "case_details": "Seek adjournment; client is travelling.",
    "case_title": "State v. Example",
    "case_number": "CRL-42/2026",
    "work_required": ["appearance"],
}
CLOSED_MESSAGE = "This request is no longer active and case details cannot be shared."


def _snapshot(hearing):
    """Every field submit_case_details writes, plus the activity timeline."""
    return {k: hearing.get(k) for k in ("case_details", "request_details", "details_submitted", "updated_at", "timeline", "status")}


async def _doc_count(db, hearing_id):
    return await db.hearing_documents.count_documents({"hearing_id": hearing_id})


def test_active_paid_hearing_accepts_case_details_as_before():
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing_id = await fx.paid_locked_hearing(db)
            before = await _hearing(db, hearing_id)
            updated = await hearings.submit_case_details(db, hearing_id, fx.requester, DETAILS)
            assert updated["details_submitted"] is True
            assert updated["case_details"] == DETAILS["case_details"]
            assert updated["request_details"]["common"]["case_title"] == "State v. Example"
            assert updated["request_details"]["service_specific"]["work_required"] == ["appearance"]
            assert len(updated["timeline"]) == len(before["timeline"]) + 1
            assert updated["timeline"][-1]["note"] == "Case details shared with the counsel"
            # Still not write-once: a correction on an active hearing is accepted.
            again = await hearings.submit_case_details(db, hearing_id, fx.requester, {"case_details": "Corrected."})
            assert again["case_details"] == "Corrected."
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


def test_cancelled_hearing_rejects_case_details_and_changes_nothing():
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing_id = await fx.paid_locked_hearing(db)
            with _refund_stub(status="pending"):
                await hearings.cancel_hearing_request(db, hearing_id, fx.requester)
            before = await _hearing(db, hearing_id)
            docs_before = await _doc_count(db, hearing_id)
            assert before["status"] == "cancelled" and not before.get("details_submitted")

            with pytest.raises(HTTPException) as exc_info:
                await hearings.submit_case_details(db, hearing_id, fx.requester, DETAILS)
            assert exc_info.value.status_code == 400
            assert exc_info.value.detail == CLOSED_MESSAGE

            after = await _hearing(db, hearing_id)
            assert _snapshot(after) == _snapshot(before)  # details, flag, updated_at, timeline untouched
            assert await _doc_count(db, hearing_id) == docs_before
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


def test_cancelled_hearing_keeps_previously_shared_details_unchanged():
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing_id = await fx.paid_locked_hearing(db)
            await hearings.submit_case_details(db, hearing_id, fx.requester, DETAILS)
            with _refund_stub(status="pending"):
                await hearings.cancel_hearing_request(db, hearing_id, fx.requester)
            before = await _hearing(db, hearing_id)
            with pytest.raises(HTTPException) as exc_info:
                await hearings.submit_case_details(db, hearing_id, fx.requester, {"case_details": "Overwrite attempt"})
            assert exc_info.value.status_code == 400
            after = await _hearing(db, hearing_id)
            assert _snapshot(after) == _snapshot(before)
            assert after["case_details"] == DETAILS["case_details"]
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


@pytest.mark.parametrize("closed_status", ["rejected", "expired"])
def test_other_closed_states_reject_case_details(closed_status):
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing_id = await fx.paid_locked_hearing(db)
            await db.hearing_requests.update_one({"hearing_id": hearing_id}, {"$set": {"status": closed_status}})
            before = await _hearing(db, hearing_id)
            with pytest.raises(HTTPException) as exc_info:
                await hearings.submit_case_details(db, hearing_id, fx.requester, DETAILS)
            assert exc_info.value.status_code == 400
            assert exc_info.value.detail == CLOSED_MESSAGE
            assert _snapshot(await _hearing(db, hearing_id)) == _snapshot(before)
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


def test_disputed_is_not_closed_and_still_accepts_case_details():
    """Guard isn't broadened past the closed set — "disputed" is under
    admin review, still open."""
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing_id = await fx.paid_locked_hearing(db)
            await db.hearing_requests.update_one({"hearing_id": hearing_id}, {"$set": {"status": "disputed"}})
            updated = await hearings.submit_case_details(db, hearing_id, fx.requester, DETAILS)
            assert updated["details_submitted"] is True
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


def test_authorization_and_payment_checks_unchanged():
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing_id = await fx.paid_locked_hearing(db)
            # Neither the counsel, an unrelated user, nor an admin can share on the requester's behalf.
            for other in (fx.counsel, _user("stranger"), {**_user("admin"), "role": "admin"}):
                with pytest.raises(HTTPException) as exc_info:
                    await hearings.submit_case_details(db, hearing_id, other, DETAILS)
                assert exc_info.value.status_code == 403
            # Ownership is still checked first on a closed hearing too.
            with _refund_stub(status="pending"):
                await hearings.cancel_hearing_request(db, hearing_id, fx.requester)
            with pytest.raises(HTTPException) as exc_info:
                await hearings.submit_case_details(db, hearing_id, _user("stranger"), DETAILS)
            assert exc_info.value.status_code == 403
            # Unpaid hearing: still the existing payment-gate message.
            unpaid_id = await fx.locked_hearing(db)
            with pytest.raises(HTTPException) as exc_info:
                await hearings.submit_case_details(db, unpaid_id, fx.requester, DETAILS)
            assert exc_info.value.status_code == 400
            assert exc_info.value.detail == "Case details can be shared once payment is confirmed"
            with pytest.raises(HTTPException) as exc_info:
                await hearings.submit_case_details(db, "hearing_does_not_exist", fx.requester, DETAILS)
            assert exc_info.value.status_code == 404
        finally:
            await fx.cleanup(db)
    asyncio.run(body())


def test_cancel_racing_the_submit_is_caught_by_the_atomic_write():
    """The read sees an active hearing, but it's cancelled before the write —
    the status guard inside update_one refuses it and no activity is added."""
    async def body():
        db, fx = _db(), _Fixture()
        await fx.setup_users(db)
        try:
            hearing_id = await fx.paid_locked_hearing(db)
            stale = await db.hearing_requests.find_one({"hearing_id": hearing_id})
            with _refund_stub(status="pending"):
                await hearings.cancel_hearing_request(db, hearing_id, fx.requester)
            before = await _hearing(db, hearing_id)

            class _StaleRead:
                """db proxy whose hearing_requests.find_one returns the
                pre-cancel snapshot once; everything else is the real db."""
                def __init__(self, real):
                    self._real = real
                    self._served = False

                def __getattr__(self, name):
                    coll = getattr(self._real, name)
                    if name != "hearing_requests":
                        return coll
                    outer = self

                    class _Coll:
                        def __getattr__(self, attr):
                            return getattr(coll, attr)

                        async def find_one(self, *args, **kwargs):
                            if not outer._served:
                                outer._served = True
                                return dict(stale)
                            return await coll.find_one(*args, **kwargs)
                    return _Coll()

            with pytest.raises(HTTPException) as exc_info:
                await hearings.submit_case_details(_StaleRead(db), hearing_id, fx.requester, DETAILS)
            assert exc_info.value.status_code == 400
            assert exc_info.value.detail == CLOSED_MESSAGE
            assert _snapshot(await _hearing(db, hearing_id)) == _snapshot(before)
        finally:
            await fx.cleanup(db)
    asyncio.run(body())
