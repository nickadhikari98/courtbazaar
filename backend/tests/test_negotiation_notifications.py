"""Notification Improvements — targeted counsel notified at hearing-creation
time (not just at payment), and both negotiation parties notified on
offer/counter-offer/accept.

Same rationale/pattern as test_negotiation.py: plain asyncio.run() wrappers
against a real Mongo instance, no HTTP layer. server.create_hearing_request
is called directly as a plain function (FastAPI's router decorator returns
it unchanged) rather than through the app, same as other endpoint-adjacent
tests in this suite. Each test creates its own throwaway users/hearing rows
and cleans them up in a finally block.
"""
import asyncio
import os
import sys
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import negotiation  # noqa: E402
import server  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _user(prefix):
    return {"user_id": f"test_negnotif_{prefix}_{uuid.uuid4().hex[:10]}", "capabilities": ["can_practice_proxy_counsel", "can_hire_proxy_counsel"]}


async def _insert_user(db, user):
    await db.users.insert_one({"user_id": user["user_id"], "name": f"Test {user['user_id']}"})


async def _cleanup(db, user_ids=(), hearing_ids=()):
    if user_ids:
        await db.users.delete_many({"user_id": {"$in": list(user_ids)}})
        await db.notification_events.delete_many({"user_id": {"$in": list(user_ids)}})
    if hearing_ids:
        await db.hearing_requests.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
        await db.negotiations.delete_many({"hearing_id": {"$in": list(hearing_ids)}})


def test_target_advocate_notified_immediately_on_hearing_creation(monkeypatch):
    async def body():
        db = _db()
        # server.create_hearing_request reads the module-global `db` — point
        # it at this test's own fresh client instead of the shared one server
        # normally holds, since that shared client gets bound to whichever
        # event loop first uses it and asyncio.run() tears its loop down
        # after every test (same reason every other test file here builds
        # its own client instead of importing a shared one).
        monkeypatch.setattr(server, "db", db)
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = None
        try:
            await _insert_user(db, requester)
            await _insert_user(db, counsel)
            payload = server.HearingRequestCreate(
                court_id="court_tishazari", hearing_date="2026-08-01", case_details="Test case",
                fee=1500.0, target_advocate_id=counsel["user_id"],
            )
            hearing = await server.create_hearing_request(payload, requester)
            hearing_id = hearing["hearing_id"]
            # Still "requested" — payment hasn't happened yet — but the
            # notification must already exist, unlike the old M6 behavior.
            assert hearing["status"] == "requested"

            event = await db.notification_events.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
            assert event is not None
            assert event["related_entity_type"] == "hearing"
            assert event["related_entity_id"] == hearing_id
            assert "request" in event["title"].lower()
        finally:
            await _cleanup(db, [requester["user_id"], counsel["user_id"]], [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_broadcast_hearing_creation_notifies_no_one(monkeypatch):
    async def body():
        db = _db()
        monkeypatch.setattr(server, "db", db)
        requester = _user("requester")
        hearing_id = None
        try:
            await _insert_user(db, requester)
            payload = server.HearingRequestCreate(
                court_id="court_tishazari", hearing_date="2026-08-01", case_details="Test case",
                fee=1500.0, target_advocate_id=None,
            )
            hearing = await server.create_hearing_request(payload, requester)
            hearing_id = hearing["hearing_id"]
            count = await db.notification_events.count_documents({"related_entity_id": hearing_id})
            assert count == 0
        finally:
            await _cleanup(db, [requester["user_id"]], [hearing_id] if hearing_id else [])
    asyncio.run(body())


async def _make_hearing(db, requester, counsel):
    import hearings
    hearing = await hearings.create_hearing_request(
        db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", 1500.0, None,
        target_advocate_id=counsel["user_id"],
    )
    return hearing["hearing_id"]


def test_propose_offer_notifies_the_other_party():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = await _make_hearing(db, requester, counsel)
        try:
            await _insert_user(db, requester)
            await _insert_user(db, counsel)

            await negotiation.propose_offer(db, hearing_id, requester, 3000.0, "Opening offer")
            event = await db.notification_events.find_one({"user_id": counsel["user_id"]}, {"_id": 0})
            assert event is not None
            assert "3000" in event["body"] or "3,000" in event["body"]
            assert event["title"] == "New offer"

            neg = await negotiation.get_negotiation(db, hearing_id)
            offer_id = neg["current_offer_id"]
            # Counsel counters — the requester (other party from counsel's
            # perspective) should now be the one notified, with "Counter offer".
            await negotiation.propose_offer(db, hearing_id, counsel, 3500.0, "Counter")
            counter_event = await db.notification_events.find_one(
                {"user_id": requester["user_id"], "title": "Counter offer"}, {"_id": 0},
            )
            assert counter_event is not None
        finally:
            await _cleanup(db, [requester["user_id"], counsel["user_id"]], [hearing_id])
    asyncio.run(body())


def test_accept_offer_notifies_the_party_who_did_not_accept():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = await _make_hearing(db, requester, counsel)
        try:
            await _insert_user(db, requester)
            await _insert_user(db, counsel)

            await negotiation.propose_offer(db, hearing_id, requester, 3000.0, None)
            offer_id = (await negotiation.get_negotiation(db, hearing_id))["current_offer_id"]
            await negotiation.accept_offer(db, hearing_id, offer_id, counsel)

            # Counsel accepted the requester's offer, so the requester
            # (not the acceptor) is the one who gets the "Offer accepted" ping.
            event = await db.notification_events.find_one(
                {"user_id": requester["user_id"], "title": "Offer accepted"}, {"_id": 0},
            )
            assert event is not None
            assert "3000" in event["body"] or "3,000" in event["body"]

            no_self_notify = await db.notification_events.find_one(
                {"user_id": counsel["user_id"], "title": "Offer accepted"}, {"_id": 0},
            )
            assert no_self_notify is None
        finally:
            await _cleanup(db, [requester["user_id"], counsel["user_id"]], [hearing_id])
    asyncio.run(body())
