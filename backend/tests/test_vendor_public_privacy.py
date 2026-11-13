"""P1 — the two vendor lists that need no login (GET /api/vendors,
GET /api/stenographers) return listing fields only, never the KYC, contact and
payout details a vendor record also holds. Real routes over raw ASGI on the
throwaway test database (see conftest); every row here is made up.
"""
import asyncio
import json
import os
import sys
import unittest.mock
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server  # noqa: E402

PRIVATE = {"phone": "9000000001", "address": "1 Private Lane", "pan": "ABCDE1234F", "gst": "07ABCDE1234F1Z5",
           "aadhaar": "123412341234", "bank_account": "000111222333", "bank_ifsc": "TEST0000001", "has_gst": True,
           "kyc_status": "approved", "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"}
# Fields no model declares: a later feature, an import, a manual DB edit.
UNEXPECTED = {"upi_id": "owner@upi", "kyc_document_url": "https://files.invalid/kyc.pdf", "internal_notes": "call after 6",
              "date_of_birth": "1980-01-01", "email": "owner@example.com"}
COURT_A, COURT_B, SERVICE = f"court_p1_{uuid.uuid4().hex[:6]}", f"court_p1_{uuid.uuid4().hex[:6]}", f"svc_p1_{uuid.uuid4().hex[:6]}"


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def call(method, path, token=None):
    headers = [(b"host", b"testserver"), (b"content-type", b"application/json")]
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    path, _, query = path.partition("?")
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http",
             "path": path, "raw_path": path.encode(), "root_path": "", "query_string": query.encode(), "headers": headers,
             "server": ("testserver", 80), "client": ("127.0.0.1", 50000)}
    sent, done = [], False

    async def receive():
        nonlocal done
        if done:
            return {"type": "http.disconnect"}
        done = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)
    await server.app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    text = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body").decode()
    return status, json.loads(text)


def vendor(name, category, rating, courts, kyc_status="approved", **extra):
    vid = f"vendor_p1_{uuid.uuid4().hex[:8]}"
    return {**PRIVATE, "vendor_id": vid, "user_id": vid, "shop_name": name, "owner_name": f"{name} Owner",
            "vendor_category": category, "court_ids": courts, "service_ids": [SERVICE], "bio": f"{name} bio",
            "hourly_rate": 500.0, "rating": rating, "total_orders": 3, "kyc_status": kyc_status, **extra}


def run(body):
    async def wrapper():
        db = _db()
        rows = [vendor("Steno High", "stenographer", 4.9, [COURT_A], **UNEXPECTED),
                vendor("Steno Low", "stenographer", 3.1, [COURT_A, COURT_B]),
                vendor("Copy Shop", "photocopy", 4.0, [COURT_B], **UNEXPECTED),
                vendor("Pending Steno", "stenographer", 5.0, [COURT_A], kyc_status="pending")]
        users = {role: f"user_p1_{role}_{uuid.uuid4().hex[:8]}" for role in ("client", "vendor", "admin")}
        await db.vendors.insert_many([dict(r) for r in rows])
        await db.users.insert_many([{"user_id": uid, "email": f"{uid}@example.com", "name": f"P1 {role}", "role": role}
                                    for role, uid in users.items()])
        tokens = {role: server.make_jwt(uid, role) for role, uid in users.items()}
        with unittest.mock.patch.object(server, "db", db):
            try:
                await body(db, rows, tokens)
            finally:
                await db.vendors.delete_many({"vendor_id": {"$in": [r["vendor_id"] for r in rows]}})
                await db.users.delete_many({"user_id": {"$in": list(users.values())}})
    asyncio.run(wrapper())


def ours(listing, rows):
    ids = {r["vendor_id"] for r in rows}
    return [v for v in listing if v["vendor_id"] in ids]


def assert_public_only(listing):
    private_values = {str(v) for v in {**PRIVATE, **UNEXPECTED}.values() if not isinstance(v, bool)} - {"approved"}
    for row in listing:
        assert set(row) <= set(server.PUBLIC_VENDOR_FIELDS), sorted(set(row) - set(server.PUBLIC_VENDOR_FIELDS))
        assert not private_values & {str(v) for v in row.values()}, row.get("vendor_id")


PUBLIC_PATHS = ["/api/vendors", f"/api/vendors?court_id={COURT_A}", f"/api/vendors?service_id={SERVICE}",
                f"/api/vendors?court_id={COURT_B}&service_id={SERVICE}", "/api/stenographers",
                f"/api/stenographers?court_id={COURT_A}"]


def test_the_public_field_list_is_an_explicit_allowlist():
    private = {"phone", "address", "pan", "gst", "aadhaar", "bank_account", "bank_ifsc", "has_gst", "user_id", "kyc_status",
               "email", "_id", "owner_name", "total_orders", "created_at", "updated_at"}
    assert not private & set(server.PUBLIC_VENDOR_FIELDS)
    # An inclusion projection: Mongo returns these fields and nothing else.
    assert server.PUBLIC_VENDOR_PROJECTION == {"_id": 0, **{f: 1 for f in server.PUBLIC_VENDOR_FIELDS}}


@pytest.mark.parametrize("path", PUBLIC_PATHS)
def test_no_login_gets_listing_fields_only(path):
    async def body(db, rows, tokens):
        status, listing = await call("GET", path)
        assert status == 200 and ours(listing, rows), path
        assert_public_only(listing)  # every row in the response, not just this test's
    run(body)


@pytest.mark.parametrize("role", ["client", "vendor", "admin"])
@pytest.mark.parametrize("path", ["/api/vendors", "/api/stenographers"])
def test_a_logged_in_user_gets_no_more_than_the_public_fields(path, role):
    async def body(db, rows, tokens):
        status, listing = await call("GET", path, tokens[role])
        assert status == 200 and ours(listing, rows)
        assert_public_only(listing)
    run(body)


def test_fields_added_to_a_vendor_record_are_not_exposed():
    async def body(db, rows, tokens):
        await db.vendors.update_many({"vendor_id": {"$in": [r["vendor_id"] for r in rows]}},
                                     {"$set": {"future_private_field": "secret-value", "nested": {"bank": {"account": "999"}}}})
        for path in ("/api/vendors", "/api/stenographers"):
            listing = (await call("GET", path))[1]
            assert ours(listing, rows)
            assert_public_only(listing)
            assert "secret-value" not in json.dumps(listing) and "future_private_field" not in json.dumps(listing)
    run(body)


def test_an_object_stored_under_a_public_field_is_not_passed_through():
    async def body(db, rows, tokens):
        high, low = rows[0], rows[1]
        await db.vendors.update_one({"vendor_id": high["vendor_id"]}, {"$set": {
            "bio": {"text": "hello", "bank_account": "555000555", "owner": {"aadhaar": "999988887777"}},
            "service_ids": [{"id": SERVICE, "pan": "ZZZZZ9999Z"}]}})
        await db.vendors.update_one({"vendor_id": low["vendor_id"]}, {"$set": {"shop_name": ["a", {"phone": "9111111111"}]}})
        for path in ("/api/vendors", "/api/stenographers"):
            listing = (await call("GET", path))[1]
            text = json.dumps(listing)
            for leaked in ("555000555", "999988887777", "ZZZZZ9999Z", "9111111111"):
                assert leaked not in text, (path, leaked)
            shown = next(v for v in listing if v["vendor_id"] == high["vendor_id"])
            assert "bio" not in shown and "service_ids" not in shown and shown["rating"] == 4.9  # plain fields still listed
            assert "shop_name" not in next(v for v in listing if v["vendor_id"] == low["vendor_id"])
            assert_public_only(listing)
    run(body)


def test_listing_fields_filters_and_order_still_work():
    async def body(db, rows, tokens):
        high, low, copy, pending = rows
        everyone = ours((await call("GET", "/api/vendors"))[1], rows)
        assert [v["shop_name"] for v in everyone] == ["Steno High", "Copy Shop", "Steno Low"]  # best rated first
        assert pending["vendor_id"] not in {v["vendor_id"] for v in everyone}  # approved vendors only
        shown = next(v for v in everyone if v["vendor_id"] == high["vendor_id"])
        assert shown == {"vendor_id": high["vendor_id"], "shop_name": "Steno High",
                         "vendor_category": "stenographer", "court_ids": [COURT_A], "service_ids": [SERVICE],
                         "bio": "Steno High bio", "hourly_rate": 500.0, "rating": 4.9}
        assert "Steno High Owner" not in json.dumps(everyone)  # the owner's own name is not a listing field
        court_a = ours((await call("GET", f"/api/vendors?court_id={COURT_A}"))[1], rows)
        assert [v["shop_name"] for v in court_a] == ["Steno High", "Steno Low"]
        court_b = ours((await call("GET", f"/api/vendors?court_id={COURT_B}&service_id={SERVICE}"))[1], rows)
        assert [v["shop_name"] for v in court_b] == ["Copy Shop", "Steno Low"]
        assert ours((await call("GET", "/api/vendors?service_id=svc_does_not_exist"))[1], rows) == []
        stenos = ours((await call("GET", "/api/stenographers"))[1], rows)
        assert [v["shop_name"] for v in stenos] == ["Steno High", "Steno Low"]  # stenographers only, best rated first
        stenos_b = ours((await call("GET", f"/api/stenographers?court_id={COURT_B}"))[1], rows)
        assert [v["shop_name"] for v in stenos_b] == ["Steno Low"]
    run(body)


def test_admin_keeps_the_full_record_and_others_are_refused():
    async def body(db, rows, tokens):
        status, listing = await call("GET", "/api/admin/vendors", tokens["admin"])
        assert status == 200
        full = next(v for v in listing if v["vendor_id"] == rows[0]["vendor_id"])
        for field in ("phone", "address", "pan", "gst", "aadhaar", "bank_account", "bank_ifsc", "kyc_status"):
            assert full[field] == rows[0][field], field
        pending = (await call("GET", "/api/admin/vendors?status=pending", tokens["admin"]))[1]
        assert rows[3]["vendor_id"] in {v["vendor_id"] for v in pending}
        for role in ("client", "vendor"):
            assert (await call("GET", "/api/admin/vendors", tokens[role]))[0] == 403
        assert (await call("GET", "/api/admin/vendors"))[0] == 401
    run(body)
