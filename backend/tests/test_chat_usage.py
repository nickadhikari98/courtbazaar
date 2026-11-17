"""Daily Instant Legal Help limits (chat_usage): guest 5 messages, free 30,
paid unlimited messages under a daily token cap; 429 with the reason when hit."""
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ai_chat  # noqa: E402
import chat_usage  # noqa: E402
import llm_service  # noqa: E402
import server  # noqa: E402

pytestmark = pytest.mark.real_usage


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    monkeypatch.setattr(server, "db", client[os.environ["DB_NAME"]])
    yield
    client.close()


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    """Each answer reports 120 tokens in and 30 out, as the real client's usage would."""
    async def fake(messages, **kwargs):
        llm_service._count_tokens(SimpleNamespace(usage=SimpleNamespace(input_tokens=120, output_tokens=30)))
        return {"ok": True, "text": "General answer.", "sources": []}
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "generate_response", fake)


def _ip():
    return f"198.51.100.{uuid.uuid4().int % 250 + 1}-{uuid.uuid4().hex[:6]}"  # unique per test


def _user(plan=None):
    return {"user_id": f"user_usage_{uuid.uuid4().hex[:8]}", "role": "client", "capabilities": [], "name": "U",
            **({"subscription": plan} if plan else {})}


async def _send(user, ip):
    return await ai_chat.handle_chat_message(server.db, None, "What is arbitration?", user, client_ip=ip)


async def _seed(user, ip, **counts):
    who = chat_usage.identity(user, ip)
    await server.db.ai_usage_daily.update_one(
        {"key": who["key"], "day": datetime.now(timezone.utc).date().isoformat()},
        {"$set": {"plan": who["plan"], **counts}}, upsert=True)


async def _expect_limit(coro, reason):
    with pytest.raises(HTTPException) as exc:
        await coro
    assert exc.value.status_code == 429
    assert exc.value.headers == {"X-Usage-Limit": reason}
    return exc.value.detail


async def _cleanup(user, ip):
    await server.db.ai_usage_daily.delete_many({"key": chat_usage.identity(user, ip)["key"]})
    convo_filter = {"user_id": user["user_id"]} if user else {"user_id": None}
    ids = [c["conversation_id"] for c in await server.db.ai_conversations.find(convo_filter).to_list(500)] if user else []
    await server.db.ai_conversations.delete_many({"conversation_id": {"$in": ids}})


def test_guest_gets_five_messages_a_day_then_a_429_asking_to_sign_up():
    ip = _ip()

    async def body():
        try:
            for _ in range(5):
                await _send(None, ip)
            usage = await server.ai_usage(user=None, request=SimpleNamespace(client=SimpleNamespace(host=ip)))
            assert {k: usage[k] for k in ("plan", "messages_used", "messages_limit", "tokens_limit")} == \
                {"plan": "guest", "messages_used": 5, "messages_limit": 5, "tokens_limit": None}
            assert usage["tokens_used"] == 750
            assert usage["resets_at"].endswith("T00:00:00+05:30")  # next midnight IST
            detail = await _expect_limit(_send(None, ip), "guest")
            assert "Sign up" in detail
            # Another guest (another IP) is unaffected; the raw IP is never stored.
            await _send(None, _ip())
            assert await server.db.ai_usage_daily.count_documents({"key": {"$regex": ip}}) == 0
        finally:
            await _cleanup(None, ip)
    asyncio.run(body())


def test_registered_free_user_gets_thirty_messages():
    user, ip = _user(), _ip()

    async def body():
        try:
            await _seed(user, ip, messages=29)
            await _send(user, ip)  # the 30th
            assert (await chat_usage.summary(server.db, user, ip))["messages_used"] == 30
            detail = await _expect_limit(_send(user, ip), "free")
            assert "Upgrade" in detail
            # Keyed by the account, not the IP: a new IP doesn't reset it.
            await _expect_limit(_send(user, _ip()), "free")
        finally:
            await _cleanup(user, ip)
    asyncio.run(body())


def test_paid_user_has_no_message_cap_but_a_daily_token_cap_from_the_env(monkeypatch):
    monkeypatch.setenv("AI_PAID_DAILY_TOKEN_CAP", "1000")
    user, ip = _user("advocate_pro"), _ip()

    async def body():
        try:
            await _seed(user, ip, messages=500, tokens=900)
            await _send(user, ip)  # messages are unlimited; 900 < 1000 tokens
            usage = await chat_usage.summary(server.db, user, ip)
            assert (usage["plan"], usage["messages_limit"], usage["tokens_limit"], usage["tokens_used"]) == \
                ("paid", None, 1000, 1050)
            await _expect_limit(_send(user, ip), "paid")
        finally:
            await _cleanup(user, ip)
    asyncio.run(body())
    monkeypatch.delenv("AI_PAID_DAILY_TOKEN_CAP")
    assert chat_usage.paid_daily_tokens() == 200000


def test_a_refused_message_writes_nothing_and_the_stream_reports_the_reason():
    ip = _ip()

    async def body():
        try:
            await _seed(None, ip, messages=5)
            before = await server.db.ai_conversations.count_documents({})
            events = [json.loads(chunk.split("data: ", 1)[1]) async for chunk in
                      ai_chat.stream_chat_events(server.db, None, "Hi", None, client_ip=ip) if "data: " in chunk]
            error = events[-1]
            assert (error["type"], error["status"], error["reason"]) == ("error", 429, "guest")
            assert await server.db.ai_conversations.count_documents({}) == before
            assert (await chat_usage.summary(server.db, None, ip))["messages_used"] == 5
        finally:
            await _cleanup(None, ip)
    asyncio.run(body())


def test_the_usage_day_is_the_date_in_india_and_resets_at_midnight_ist(monkeypatch):
    from datetime import datetime, timedelta, timezone
    user, ip = _user(), _ip()
    utc = timezone.utc
    clock = {}
    monkeypatch.setattr(chat_usage, "_today", lambda: clock["now"].astimezone(chat_usage.IST))

    async def at(when):
        clock["now"] = when
        await chat_usage.record(server.db, chat_usage.identity(user, ip), 0)
        return await chat_usage.summary(server.db, user, ip)

    async def body():
        try:
            # 23:00 IST on the 17th (17:30 UTC) and 01:00 IST on the 18th (19:30 UTC, same UTC day): two IST days.
            late = await at(datetime(2026, 11, 17, 17, 30, tzinfo=utc))
            assert (late["messages_used"], late["resets_at"]) == (1, "2026-11-18T00:00:00+05:30")
            early = await at(datetime(2026, 11, 17, 19, 30, tzinfo=utc))
            assert (early["messages_used"], early["resets_at"]) == (1, "2026-11-19T00:00:00+05:30")
            # 00:00 UTC (05:30 IST on the 18th) does not roll the counter.
            before = await at(datetime(2026, 11, 17, 23, 50, tzinfo=utc))   # 05:20 IST, 18th
            after = await at(datetime(2026, 11, 18, 0, 10, tzinfo=utc))     # 05:40 IST, 18th
            assert (before["messages_used"], after["messages_used"]) == (2, 3)
            days = await server.db.ai_usage_daily.distinct("day", {"key": chat_usage.identity(user, ip)["key"]})
            assert sorted(days) == ["2026-11-17", "2026-11-18"]
        finally:
            await _cleanup(user, ip)
    asyncio.run(body())
