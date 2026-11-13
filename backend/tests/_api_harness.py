"""Test helper: call the real routes with real JWTs over raw ASGI, on the
throwaway test database (see conftest). Seeds throwaway people and removes
everything they created when the test ends. Payments run in Razorpay's
simulated mode (conftest blanks the keys), so no gateway is ever called."""
import asyncio
import json
import os
import sys
import unittest.mock
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server  # noqa: E402
from tests._verified_counsel import verify_counsel  # noqa: E402

COURT, DATE = "court_tishazari", "2026-08-20"  # conftest pins India's today to 2026-01-01
PRICING = {"district": {"morning": 1200.0, "afternoon": 1500.0}}
_CREATED = []  # user ids made by the running test


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def call(method, path, body=None, token=None):
    headers = [(b"host", b"testserver"), (b"content-type", b"application/json")]
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    data = json.dumps(body).encode() if body is not None else b""
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
        return {"type": "http.request", "body": data, "more_body": False}

    async def send(message):
        sent.append(message)
    await server.app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    text = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body").decode()
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


class P:
    def __init__(self, user_id, role, token):
        self.id, self.role, self.token = user_id, role, token


async def person(db, role, prefix, verified=False, negotiation=True):
    uid = f"user_t12_{prefix}_{uuid.uuid4().hex[:8]}"
    _CREATED.append(uid)
    await db.users.insert_one({"user_id": uid, "email": f"{uid}@example.com", "name": f"T12 {prefix}", "role": role,
                               "professional_profile_types": [role]})
    if role == "proxy_counsel":
        await db.proxy_counsel_profiles.insert_one({"user_id": uid, "negotiation_enabled": negotiation,
                                                    "pricing": PRICING, "courts": [COURT]})
        if verified:
            await verify_counsel(db, uid)
    return P(uid, role, server.make_jwt(uid, role))


async def api(method, path, who=None, body=None):
    return await call(method, path, body, token=who.token if who else None)


async def create(client, counsel=None, fee=None, date=DATE, court=COURT):
    body = {"court_id": court, "hearing_date": date, "case_details": "", "service_type": "proxy_counsel",
            "target_advocate_id": counsel.id if counsel else None}
    if fee is not None:
        body["fee"] = fee
    return await api("POST", "/api/hearing-requests", client, body)


async def pay(client, hearing_id):
    st, order = await api("POST", f"/api/hearing-requests/{hearing_id}/payment/create-order", client)
    assert st == 200, order
    return await api("POST", f"/api/hearing-requests/{hearing_id}/payment/verify", client,
                     {"razorpay_order_id": order["razorpay_order_id"]})


async def agreed_and_paid(db, client, counsel, fee=1500.0):
    """Targeted request -> client's opening offer (auto) -> counsel accepts it -> client pays."""
    st, h = await create(client, counsel, fee=fee)
    assert st == 200, h
    hid = h["hearing_id"]
    neg = (await api("GET", f"/api/hearing-requests/{hid}/negotiation", counsel))[1]
    assert (await api("POST", f"/api/hearing-requests/{hid}/negotiation/offers/{neg['current_offer_id']}/accept", counsel))[0] == 200
    st, res = await pay(client, hid)
    assert st == 200 and res["status"] == "broadcast", res
    return hid


async def _cleanup(db):
    ids, _CREATED[:] = list(_CREATED), []
    hids = [h["hearing_id"] for h in await db.hearing_requests.find(
        {"requesting_user_id": {"$in": ids}}, {"hearing_id": 1}).to_list(1000)]
    for coll, key in (("hearing_requests", "hearing_id"), ("negotiations", "hearing_id"), ("hearing_messages", "hearing_id"),
                      ("hearing_documents", "hearing_id"), ("counsel_matching_log", "hearing_id"),
                      ("escrow_transactions", "context_id"), ("payment_transactions", "context_id")):
        await db[coll].delete_many({key: {"$in": hids}})
    await db.audit_log.delete_many({"details.hearing_id": {"$in": hids}})
    for coll in ("notification_events", "proxy_counsel_profiles", "users"):
        await db[coll].delete_many({"user_id": {"$in": ids}})


def run(body):
    async def wrapper():
        db = _db()
        with unittest.mock.patch.object(server, "db", db):
            try:
                await body(db)
            finally:
                await _cleanup(db)
    asyncio.run(wrapper())
