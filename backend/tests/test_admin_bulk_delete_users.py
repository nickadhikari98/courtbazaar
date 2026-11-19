"""Admin → Users "Delete selected" (audit_log.permanently_delete_users).

Founder decision (Oct 15 2026): this screen permanently removes the users
row, for active and already-deactivated users alike. Guards: never the
calling admin, never an admin account, never anyone with money in flight
(open escrow as payer/payee, or a wallet balance). Every delete is
audit-logged with the user's identity captured before the row is gone.

Re-registration (founder rule, Oct 15 2026): a permanently deleted person may
sign up again with the same email/phone/name and gets a brand-new account —
new user_id, nothing of the old account or profile restored, normal approval
before any counsel profile is public — while every old token stays invalid.

Same convention as test_cancel_after_payment.py: drives the module directly
via Motor with plain asyncio.run() wrappers, no HTTP layer. Runs against the
throwaway DB conftest.py sets up.
"""
import asyncio
import os
import sys
import uuid

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from audit_log import DELETED_ACCOUNT_MESSAGE, is_permanently_deleted, permanently_delete_users  # noqa: E402
import server  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _uid(prefix):
    return f"test_bulkdel_{prefix}_{uuid.uuid4().hex[:10]}"


async def _make_user(db, prefix, **extra):
    user = {"user_id": _uid(prefix), "email": f"{prefix}_{uuid.uuid4().hex[:6]}@cbqa.in",
            "name": prefix.title(), "role": "client", **extra}
    await db.users.insert_one(dict(user))
    await db.user_sessions.insert_one({"user_id": user["user_id"], "session_token": uuid.uuid4().hex})
    return user


def _run(coro_fn):
    async def wrapper():
        db = _db()
        try:
            return await coro_fn(db)
        finally:
            db.client.close()
    return asyncio.run(wrapper())


def test_deletes_active_and_deactivated_users_and_their_sessions():
    async def body(db):
        admin = await _make_user(db, "admin", role="admin")
        active = await _make_user(db, "active", role="proxy_counsel")
        gone = await _make_user(db, "gone", role="vendor", deleted=True, deleted_at="2026-10-01T00:00:00+00:00")

        result = await permanently_delete_users(db, [active["user_id"], gone["user_id"]], admin)

        assert result == {"deleted": [active["user_id"], gone["user_id"]], "skipped": []}
        for u in (active, gone):
            assert await db.users.find_one({"user_id": u["user_id"]}) is None
            assert await db.user_sessions.count_documents({"user_id": u["user_id"]}) == 0
        logs = await db.audit_log.find({"action": "admin.user_deleted", "user_id": admin["user_id"]}).to_list(10)
        by_target = {l["details"]["target_user_id"]: l["details"] for l in logs}
        assert by_target[active["user_id"]]["target_email"] == active["email"]
        assert by_target[active["user_id"]]["was_deactivated"] is False
        assert by_target[gone["user_id"]]["was_deactivated"] is True
        assert all(d["result"] == "success" for d in by_target.values())
    _run(body)


def test_never_deletes_self_admins_or_unknown_ids():
    async def body(db):
        admin = await _make_user(db, "admin", role="admin")
        other_admin = await _make_user(db, "admin2", role="admin")
        missing = _uid("missing")

        result = await permanently_delete_users(db, [admin["user_id"], other_admin["user_id"], missing], admin)

        assert result["deleted"] == []
        reasons = {s["user_id"]: s["reason"] for s in result["skipped"]}
        assert reasons == {
            admin["user_id"]: "You cannot delete your own account",
            other_admin["user_id"]: "Admin accounts cannot be deleted",
            missing: "User not found",
        }
        assert await db.users.find_one({"user_id": admin["user_id"]}) is not None
        assert await db.users.find_one({"user_id": other_admin["user_id"]}) is not None
    _run(body)


def test_skips_users_with_money_in_flight():
    async def body(db):
        admin = await _make_user(db, "admin", role="admin")
        payer = await _make_user(db, "payer")
        payee = await _make_user(db, "payee", role="proxy_counsel")
        wallet = await _make_user(db, "wallet", role="proxy_counsel", wallet_balance=500.0)
        settled = await _make_user(db, "settled")
        await db.escrow_transactions.insert_one({"escrow_id": _uid("esc"), "payer_user_id": payer["user_id"],
                                                 "payee_user_id": payee["user_id"], "status": "held"})
        await db.escrow_transactions.insert_one({"escrow_id": _uid("esc"), "payer_user_id": settled["user_id"],
                                                 "payee_user_id": None, "status": "released"})

        ids = [payer["user_id"], payee["user_id"], wallet["user_id"], settled["user_id"]]
        result = await permanently_delete_users(db, ids, admin)

        assert result["deleted"] == [settled["user_id"]]
        assert {s["user_id"] for s in result["skipped"]} == {payer["user_id"], payee["user_id"], wallet["user_id"]}
        for u in (payer, payee, wallet):
            assert await db.users.find_one({"user_id": u["user_id"]}) is not None
    _run(body)


def test_duplicate_ids_are_processed_once():
    async def body(db):
        admin = await _make_user(db, "admin", role="admin")
        u = await _make_user(db, "dup")
        result = await permanently_delete_users(db, [u["user_id"], u["user_id"]], admin)
        assert result == {"deleted": [u["user_id"]], "skipped": []}
    _run(body)


def test_removes_public_profile_rows_so_the_user_is_no_longer_listed():
    async def body(db):
        admin = await _make_user(db, "admin", role="admin")
        counsel = await _make_user(db, "counsel", role="advocate")
        vendor = await _make_user(db, "vendor", role="vendor")
        keep = await _make_user(db, "keep", role="advocate")
        for u in (counsel, keep):
            await db.proxy_counsel_profiles.insert_one({"user_id": u["user_id"], "kyc_status": "approved",
                                                        "bar_council_verified": True})
            await db.availability_slots.insert_one({"slot_id": _uid("slot"), "user_id": u["user_id"]})
        await db.vendors.insert_one({"vendor_id": _uid("ven"), "user_id": vendor["user_id"], "kyc_status": "approved"})

        await permanently_delete_users(db, [counsel["user_id"], vendor["user_id"]], admin)

        for coll in ("proxy_counsel_profiles", "availability_slots", "vendors"):
            assert await db[coll].count_documents({"user_id": {"$in": [counsel["user_id"], vendor["user_id"]]}}) == 0
        assert await db.proxy_counsel_profiles.count_documents({"user_id": keep["user_id"]}) == 1
        assert await db.availability_slots.count_documents({"user_id": keep["user_id"]}) == 1
        log = await db.audit_log.find_one({"action": "admin.user_deleted", "details.target_user_id": counsel["user_id"]})
        assert log["details"]["profiles_removed"] == {"proxy_counsel_profiles": 1, "availability_slots": 1, "vendors": 0, "calendar_events": 0}
    _run(body)


def test_deleted_email_and_phones_are_recorded():
    async def body(db):
        admin = await _make_user(db, "admin", role="admin")
        phone, alt = f"9{uuid.uuid4().int % 10**9:09d}", f"8{uuid.uuid4().int % 10**9:09d}"
        u = await _make_user(db, "recorded", phone=phone, alt_phones=[alt])
        assert not await is_permanently_deleted(db, email=u["email"])

        await permanently_delete_users(db, [u["user_id"]], admin)

        assert await is_permanently_deleted(db, email=u["email"].upper())  # case-insensitive
        assert await is_permanently_deleted(db, phone=phone)
        assert await is_permanently_deleted(db, phone=alt)
        assert not await is_permanently_deleted(db, email="someone.else@cbqa.in")
        assert not await is_permanently_deleted(db)
    _run(body)


def test_skipped_users_are_not_recorded_as_deleted():
    async def body(db):
        admin = await _make_user(db, "admin", role="admin")
        rich = await _make_user(db, "rich", wallet_balance=10.0)
        await permanently_delete_users(db, [rich["user_id"]], admin)
        assert not await is_permanently_deleted(db, email=rich["email"])
    _run(body)


# --- Auth entry points (server.py) --------------------------------------

@pytest.fixture
def server_db(monkeypatch):
    """Motor clients are bound to the loop they first ran on; each test uses
    its own asyncio.run, so give it its own client installed as server.db."""
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    monkeypatch.setattr(server, "db", client[os.environ["DB_NAME"]])
    yield server.db
    client.close()


async def _deleted_user(db, password="Secret#123"):
    admin = await _make_user(db, "admin", role="admin")
    phone = f"7{uuid.uuid4().int % 10**9:09d}"
    u = await _make_user(db, "gone", phone=phone, password_hash=server.hash_password(password))
    await permanently_delete_users(db, [u["user_id"]], admin)
    return u, password


async def _expect(coro, status):
    with pytest.raises(HTTPException) as exc:
        await coro
    assert exc.value.status_code == status
    return exc.value.detail


def test_deleted_user_old_token_no_longer_works(server_db):
    async def body():
        admin = await _make_user(server_db, "admin", role="admin")
        u = await _make_user(server_db, "tok")
        token = server.make_jwt(u["user_id"], u["role"])
        assert (await server.get_current_user(f"Bearer {token}"))["user_id"] == u["user_id"]
        await permanently_delete_users(server_db, [u["user_id"]], admin)
        await _expect(server.get_current_user(f"Bearer {token}"), 401)
    asyncio.run(body())


def test_deleted_user_old_password_no_longer_works(server_db):
    async def body():
        u, pw = await _deleted_user(server_db)
        detail = await _expect(server.login(server.LoginRequest(email=u["email"], password=pw), None), 401)
        assert detail == DELETED_ACCOUNT_MESSAGE
    asyncio.run(body())


def test_deleted_person_can_register_again_as_a_brand_new_account(server_db):
    """Same email, phone and name -> a new user_id; the old token stays dead;
    nothing of the old account or its profile comes back."""
    async def body():
        admin = await _make_user(server_db, "admin", role="admin")
        phone = f"7{uuid.uuid4().int % 10**9:09d}"
        old = await _make_user(server_db, "again", role="advocate", phone=phone, name="Asha Rao",
                               password_hash=server.hash_password("Old#pass1"), wallet_balance=0.0)
        await server_db.proxy_counsel_profiles.insert_one({"user_id": old["user_id"], "kyc_status": "approved",
                                                           "bar_council_verified": True, "courts": ["court_x"]})
        old_token = server.make_jwt(old["user_id"], old["role"])
        await permanently_delete_users(server_db, [old["user_id"]], admin)

        out = await server.register(server.RegisterRequest(email=old["email"], password="New#pass1",
                                                           name="Asha Rao", phone=phone, role="advocate"))
        new_id = out["user"]["user_id"]
        assert new_id != old["user_id"]
        assert await server_db.users.count_documents({"email": old["email"]}) == 1
        assert await server_db.users.count_documents({"user_id": old["user_id"]}) == 0
        assert await server_db.proxy_counsel_profiles.count_documents(
            {"user_id": {"$in": [old["user_id"], new_id]}}) == 0  # old profile gone, none restored

        assert (await server.get_current_user(f"Bearer {out['token']}"))["user_id"] == new_id
        await _expect(server.get_current_user(f"Bearer {old_token}"), 401)
        await _expect(server.login(server.LoginRequest(email=old["email"], password="Old#pass1"), None), 401)
        assert (await server.login(server.LoginRequest(email=old["email"], password="New#pass1"), None))["user"]["user_id"] == new_id
    asyncio.run(body())


def test_new_account_profile_is_hidden_until_normal_approval(server_db):
    """After re-registering, the new counsel profile only becomes public
    through the normal KYC + bar council approval, like any new counsel."""
    async def body():
        import counsel_matching
        import practice
        admin = await _make_user(server_db, "admin", role="admin")
        court = f"court_again_{uuid.uuid4().hex[:6]}"
        old = await _make_user(server_db, "listed", role="advocate")
        await server_db.proxy_counsel_profiles.insert_one({"user_id": old["user_id"], "kyc_status": "approved",
                                                           "bar_council_verified": True, "availability_mode": True,
                                                           "courts": [court]})
        ranked, _ = await counsel_matching.list_and_recommend(server_db, court_id=court)
        assert [c["user_id"] for c in ranked] == [old["user_id"]]
        await permanently_delete_users(server_db, [old["user_id"]], admin)

        out = await server.register(server.RegisterRequest(email=old["email"], password="New#pass1",
                                                           name=old["name"], role="advocate"))
        new_id = out["user"]["user_id"]
        try:
            profile = await practice.get_or_create_profile(server_db, new_id)
            assert profile["kyc_status"] != "approved"
            await server_db.proxy_counsel_profiles.update_one({"user_id": new_id},
                                                              {"$set": {"courts": [court], "availability_mode": True}})
            ranked, _ = await counsel_matching.list_and_recommend(server_db, court_id=court)
            assert ranked == []  # neither the old nor the unapproved new profile is visible

            await practice.approve_kyc(server_db, new_id)
            await practice.verify_bar_council(server_db, new_id)
            ranked, _ = await counsel_matching.list_and_recommend(server_db, court_id=court)
            assert [c["user_id"] for c in ranked] == [new_id]
        finally:
            # An approved, available counsel would join every other suite's
            # hearing-time candidate pool (the test DB is shared per session).
            await server_db.proxy_counsel_profiles.delete_many({"user_id": new_id})
            await server_db.users.delete_many({"user_id": new_id})
    asyncio.run(body())


def test_deleted_person_can_sign_up_again_with_phone_otp(server_db):
    async def body():
        u, _ = await _deleted_user(server_db)
        assert (await server.otp_request(server.OtpRequest(phone=u["phone"])))["ok"] is True
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        await server_db.otp_codes.delete_many({"phone": u["phone"]})
        await server_db.otp_codes.insert_one({
            "phone": u["phone"], "otp_hash": server.hash_password("123456"), "attempts": 0, "used": False,
            "expires_at": (now + timedelta(minutes=5)).isoformat(), "created_at": now.isoformat(),
        })
        out = await server.otp_verify(server.OtpVerify(phone=u["phone"], otp="123456"))
        assert out["user"]["user_id"] != u["user_id"]
        assert await server_db.users.count_documents({"phone": u["phone"]}) == 1
    asyncio.run(body())


def test_unrelated_new_user_can_still_register(server_db):
    async def body():
        await _deleted_user(server_db)
        email = f"fresh_{uuid.uuid4().hex[:6]}@cbqa.in"
        out = await server.register(server.RegisterRequest(email=email, password="New#pass1", name="Fresh"))
        assert out["user"]["email"] == email
    asyncio.run(body())


def test_removes_calendar_events_and_lead_applications():
    async def body(db):
        admin = await _make_user(db, "admin", role="admin")
        u = await _make_user(db, "leaduser", role="advocate")
        await db.calendar_events.insert_one({"event_id": _uid("ev"), "user_id": u["user_id"]})
        converted = _uid("lead")
        by_email = _uid("lead")
        await db.leads.insert_one({"lead_id": converted, "converted_user_id": u["user_id"], "status": "approved"})
        await db.leads.insert_one({"lead_id": by_email, "email_normalized": u["email"].lower(), "status": "submitted"})
        await db.lead_documents.insert_one({"lead_id": converted, "doc_id": _uid("doc"), "storage_path": "kyc/x.pdf"})
        purged = []

        await permanently_delete_users(db, [u["user_id"]], admin, delete_object_fn=purged.append)

        assert await db.calendar_events.count_documents({"user_id": u["user_id"]}) == 0
        assert await db.leads.count_documents({"lead_id": {"$in": [converted, by_email]}}) == 0
        assert await db.lead_documents.count_documents({"lead_id": converted}) == 0
        assert purged == ["kyc/x.pdf"]
        log = await db.audit_log.find_one({"action": "admin.user_deleted", "details.target_user_id": u["user_id"]})
        assert sorted(log["details"]["leads_removed"]) == sorted([converted, by_email])
    _run(body)


def _google_request():
    from types import SimpleNamespace
    return SimpleNamespace(cookies={}, client=SimpleNamespace(host="127.0.0.1"))


def _fake_google(monkeypatch, email):
    """Real Google sign-in needs a Google-signed ID token, which no local or
    CI setup has — so the token check itself is faked and everything after
    it (the deleted-account guard, account lookup/creation) runs for real."""
    import google.oauth2.id_token as google_id_token
    monkeypatch.setattr(server, "GOOGLE_OAUTH_ENABLED", True)
    monkeypatch.setattr(server, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(google_id_token, "verify_oauth2_token",
                        lambda credential, request, client_id: {"email": email, "name": "Google User"})


def test_deleted_person_signing_in_with_google_gets_a_brand_new_account(server_db, monkeypatch):
    async def body():
        u, _ = await _deleted_user(server_db)
        _fake_google(monkeypatch, u["email"])
        resp = await server.google_callback(_google_request(), credential="fake", g_csrf_token=None, role="client")
        location = resp.headers["location"]
        assert "/auth/google/complete#token=" in location
        new_id = server.decode_jwt(location.split("#token=", 1)[1])["user_id"]
        assert new_id != u["user_id"]
        assert await server_db.users.count_documents({"email": u["email"]}) == 1
    asyncio.run(body())


def test_unrelated_google_user_still_gets_an_account(server_db, monkeypatch):
    async def body():
        await _deleted_user(server_db)
        email = f"google_{uuid.uuid4().hex[:6]}@cbqa.in"
        _fake_google(monkeypatch, email)
        resp = await server.google_callback(_google_request(), credential="fake", g_csrf_token=None, role="client")
        assert "/auth/google/complete#token=" in resp.headers["location"]
        assert await server_db.users.count_documents({"email": email}) == 1
    asyncio.run(body())


# --- Wider financial / in-flight guard (financial_blockers) ---------------

MONEY = "Has money held in escrow or a wallet balance"

IN_FLIGHT_CASES = {
    "escrow_captured": ("escrow_transactions", "payer_user_id", {"status": "captured"}, MONEY),
    "escrow_refund_failed": ("escrow_transactions", "payee_user_id", {"status": "refund_failed"}, MONEY),
    "escrow_refund_processing": ("escrow_transactions", "payer_user_id", {"status": "refund_processing"}, MONEY),
    "hearing_as_client": ("hearing_requests", "requesting_user_id", {"status": "broadcast"}, "Has an active hearing"),
    "hearing_as_counsel": ("hearing_requests", "proxy_counsel_user_id", {"status": "hearing_scheduled"}, "Has an active hearing"),
    "hearing_disputed": ("hearing_requests", "target_advocate_id", {"status": "disputed"}, "Has an active hearing"),
    "order_as_client": ("orders", "user_id", {"status": "processing"}, "Has an open order"),
    "order_as_vendor": ("orders", "vendor_id", {"status": "delivered"}, "Has an open order"),
    "settlement_queued": ("settlements", "payee_id", {"status": "queued"}, "Has an unpaid settlement payout"),
    "settlement_failed": ("settlements", "payee_id", {"status": "failed"}, "Has an unpaid settlement payout"),
}


@pytest.mark.parametrize("case", sorted(IN_FLIGHT_CASES))
def test_in_flight_money_or_work_blocks_delete(case):
    coll, field, extra, reason = IN_FLIGHT_CASES[case]

    async def body(db):
        admin = await _make_user(db, "admin", role="admin")
        u = await _make_user(db, "busy", role="vendor")
        row_id = _uid(case)
        await db[coll].insert_one({"row_id": row_id, field: u["user_id"], **extra})
        try:
            result = await permanently_delete_users(db, [u["user_id"]], admin)
            assert result["deleted"] == []
            assert result["skipped"] == [{"user_id": u["user_id"], "reason": reason}]
            assert await db.users.find_one({"user_id": u["user_id"]}) is not None
            assert not await is_permanently_deleted(db, email=u["email"])
        finally:
            await db[coll].delete_many({"row_id": row_id})
    _run(body)


def test_finished_history_does_not_block_delete_and_is_kept():
    """Closed hearings/orders, paid settlements and settled escrow stay as
    records but never stop a delete."""
    async def body(db):
        admin = await _make_user(db, "admin", role="admin")
        u = await _make_user(db, "done", role="vendor")
        uid = u["user_id"]
        seeded = [
            ("escrow_transactions", {"payer_user_id": uid, "status": "released"}),
            ("escrow_transactions", {"payer_user_id": uid, "status": "refunded"}),
            ("hearing_requests", {"requesting_user_id": uid, "status": "completed"}),
            ("hearing_requests", {"proxy_counsel_user_id": uid, "status": "cancelled"}),
            ("orders", {"user_id": uid, "status": "completed"}),
            ("orders", {"vendor_id": uid, "status": "cancelled"}),
            ("settlements", {"payee_id": uid, "status": "paid"}),
        ]
        row_ids = []
        for coll, doc in seeded:
            row_ids.append(_uid("hist"))
            await db[coll].insert_one({"row_id": row_ids[-1], **doc})
        try:
            result = await permanently_delete_users(db, [uid], admin)
            assert result == {"deleted": [uid], "skipped": []}
            for coll, doc in seeded:  # retained records are untouched
                assert await db[coll].count_documents(doc) == 1
        finally:
            for coll, _ in seeded:
                await db[coll].delete_many({"row_id": {"$in": row_ids}})
    _run(body)


def test_multiple_blockers_are_all_reported():
    async def body(db):
        admin = await _make_user(db, "admin", role="admin")
        u = await _make_user(db, "multi", wallet_balance=5.0)
        await db.orders.insert_one({"row_id": _uid("ord"), "user_id": u["user_id"], "status": "placed"})
        try:
            result = await permanently_delete_users(db, [u["user_id"]], admin)
            assert result["skipped"][0]["reason"] == MONEY + "; Has an open order"
        finally:
            await db.orders.delete_many({"user_id": u["user_id"]})
    _run(body)


# --- Remaining auth entry points -----------------------------------------

def test_otp_is_never_sent_to_a_deactivated_phone(server_db):
    async def body():
        phone = f"6{uuid.uuid4().int % 10**9:09d}"
        await _make_user(server_db, "deact", phone=phone, deleted=True)
        await _expect(server.otp_request(server.OtpRequest(phone=phone)), 401)
        assert await server_db.otp_codes.count_documents({"phone": phone}) == 0
    asyncio.run(body())


def test_deactivated_user_google_sign_in_is_refused_without_touching_the_row(server_db, monkeypatch):
    async def body():
        u = await _make_user(server_db, "gdeact", deleted=True, name="Original Name")
        _fake_google(monkeypatch, u["email"])
        resp = await server.google_callback(_google_request(), credential="fake", g_csrf_token=None, role="client")
        assert resp.headers["location"].endswith("/login?error=account_deactivated")
        row = await server_db.users.find_one({"user_id": u["user_id"]})
        assert row["name"] == "Original Name" and "avatar_url" not in row
    asyncio.run(body())


def test_set_password_link_does_not_work_for_deactivated_account(server_db):
    async def body():
        import hashlib
        token = uuid.uuid4().hex
        u = await _make_user(server_db, "setpw", deleted=True,
                             set_password_token_hash=hashlib.sha256(token.encode()).hexdigest())
        await _expect(server.set_password(server.SetPasswordRequest(token=token, password="New#pass1")), 401)
        assert "password_hash" not in await server_db.users.find_one({"user_id": u["user_id"]})
    asyncio.run(body())


def test_existing_active_user_still_signs_in_with_google(server_db, monkeypatch):
    """Regression guard for the deleted/deactivated checks: a normal account
    signing in with Google gets a token for its own user_id, and no second
    account is created."""
    async def body():
        await _deleted_user(server_db)  # a permanently deleted account exists alongside
        u = await _make_user(server_db, "gactive", role="client")
        _fake_google(monkeypatch, u["email"])
        resp = await server.google_callback(_google_request(), credential="fake", g_csrf_token=None, role="client")
        location = resp.headers["location"]
        assert "/auth/google/complete#token=" in location
        payload = server.decode_jwt(location.split("#token=", 1)[1])
        assert payload["user_id"] == u["user_id"]
        assert await server_db.users.count_documents({"email": u["email"]}) == 1
    asyncio.run(body())


# --- Required protections (explicit matrix, Oct 15 2026 final audit) -------

PROTECTED_CASES = {
    "current_admin": ({"role": "admin"}, None, "You cannot delete your own account"),
    "other_admin": ({"role": "admin"}, None, "Admin accounts cannot be deleted"),
    "escrow_created_payer": ({}, ("payer_user_id", "created"), MONEY),
    "escrow_created_payee": ({}, ("payee_user_id", "created"), MONEY),
    "escrow_held_payer": ({}, ("payer_user_id", "held"), MONEY),
    "escrow_held_payee": ({}, ("payee_user_id", "held"), MONEY),
    "escrow_refund_pending_payer": ({}, ("payer_user_id", "refund_pending"), MONEY),
    "escrow_refund_pending_payee": ({}, ("payee_user_id", "refund_pending"), MONEY),
    "wallet_balance": ({"wallet_balance": 0.01}, None, MONEY),
    "wallet_held_balance": ({"wallet_held_balance": 250.0}, None, MONEY),
}


@pytest.mark.parametrize("case", sorted(PROTECTED_CASES))
def test_required_protections_block_permanent_delete(case):
    extra, escrow, reason = PROTECTED_CASES[case]

    async def body(db):
        admin = await _make_user(db, "actor", role="admin")
        target = admin if case == "current_admin" else await _make_user(db, "protected", **extra)
        escrow_id = None
        if escrow:
            field, status = escrow
            escrow_id = _uid("esc")
            await db.escrow_transactions.insert_one({"escrow_id": escrow_id, field: target["user_id"], "status": status})
        try:
            result = await permanently_delete_users(db, [target["user_id"]], admin)
            assert result == {"deleted": [], "skipped": [{"user_id": target["user_id"], "reason": reason}]}
            assert await db.users.find_one({"user_id": target["user_id"]}) is not None
            assert await db.user_sessions.count_documents({"user_id": target["user_id"]}) == 1
            assert not await is_permanently_deleted(db, email=target["email"])
            assert await db.audit_log.count_documents({"action": "admin.user_deleted",
                                                       "details.target_user_id": target["user_id"]}) == 0
        finally:
            if escrow_id:
                await db.escrow_transactions.delete_many({"escrow_id": escrow_id})
    _run(body)


def test_zero_wallet_and_settled_escrow_do_not_block():
    async def body(db):
        admin = await _make_user(db, "actor", role="admin")
        u = await _make_user(db, "settled", wallet_balance=0.0, wallet_held_balance=0)
        await db.escrow_transactions.insert_one({"escrow_id": _uid("esc"), "payee_user_id": u["user_id"], "status": "released"})
        result = await permanently_delete_users(db, [u["user_id"]], admin)
        assert result == {"deleted": [u["user_id"]], "skipped": []}
    _run(body)
