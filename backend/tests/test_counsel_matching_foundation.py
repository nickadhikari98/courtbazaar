"""Counsel Matching Agent — session ledger foundation (roadmap M4).

Same rationale as test_escrow_deferred_payee.py: counsel_matching.py has no
HTTP endpoint yet (nothing calls it until a later milestone wires it into
hearings.py), so this exercises the module directly via Motor with plain
asyncio.run() wrappers rather than pytest-asyncio, which isn't a dependency
of this project. Each test creates its own throwaway hearing_id and cleans
up its counsel_matching_log row in a finally block.
"""
import asyncio
import os
import sys
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import counsel_matching  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


async def _db_with_indexes():
    """get_or_create_matching_session's idempotency relies entirely on the
    unique hearing_id index (see counsel_matching.ensure_indexes) — in the
    real app that's always created at server startup before any request
    runs. Tests must set up the same precondition explicitly since nothing
    calls ensure_indexes automatically here."""
    db = _db()
    await counsel_matching.ensure_indexes(db)
    return db


async def _cleanup(db, hearing_ids=()):
    if hearing_ids:
        await db.counsel_matching_log.delete_many({"hearing_id": {"$in": list(hearing_ids)}})


def test_create_matching_session_default_shape():
    async def body():
        db = await _db_with_indexes()
        hearing_id = f"test_hearing_{uuid.uuid4().hex[:10]}"
        try:
            session = await counsel_matching.get_or_create_matching_session(db, hearing_id, urgent=False)
            assert session["hearing_id"] == hearing_id
            assert session["urgent"] is False
            assert session["status"] == "in_progress"
            assert session["tiers"] == []
            assert session["timeline"] == []
            assert session["accepted_by"] is None
            assert session["final_decision"] is None
            assert session["match_id"].startswith("match_")
            assert "created_at" in session and "updated_at" in session
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_create_matching_session_is_idempotent():
    async def body():
        db = await _db_with_indexes()
        hearing_id = f"test_hearing_{uuid.uuid4().hex[:10]}"
        try:
            first = await counsel_matching.get_or_create_matching_session(db, hearing_id, urgent=True)
            second = await counsel_matching.get_or_create_matching_session(db, hearing_id, urgent=True)
            assert first["match_id"] == second["match_id"]
            count = await db.counsel_matching_log.count_documents({"hearing_id": hearing_id})
            assert count == 1
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_different_hearings_get_different_sessions():
    async def body():
        db = await _db_with_indexes()
        h1 = f"test_hearing_{uuid.uuid4().hex[:10]}"
        h2 = f"test_hearing_{uuid.uuid4().hex[:10]}"
        try:
            s1 = await counsel_matching.get_or_create_matching_session(db, h1)
            s2 = await counsel_matching.get_or_create_matching_session(db, h2)
            assert s1["match_id"] != s2["match_id"]
        finally:
            await _cleanup(db, [h1, h2])
    asyncio.run(body())


def test_get_matching_session_returns_none_when_absent():
    async def body():
        db = await _db_with_indexes()
        result = await counsel_matching.get_matching_session(db, "nonexistent_hearing_xyz")
        assert result is None
    asyncio.run(body())


def test_get_matching_session_returns_created_session():
    async def body():
        db = await _db_with_indexes()
        hearing_id = f"test_hearing_{uuid.uuid4().hex[:10]}"
        try:
            created = await counsel_matching.get_or_create_matching_session(db, hearing_id)
            fetched = await counsel_matching.get_matching_session(db, hearing_id)
            assert fetched["match_id"] == created["match_id"]
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_append_session_event_accumulates_in_order():
    async def body():
        db = await _db_with_indexes()
        hearing_id = f"test_hearing_{uuid.uuid4().hex[:10]}"
        try:
            session = await counsel_matching.get_or_create_matching_session(db, hearing_id)
            match_id = session["match_id"]
            await counsel_matching.append_session_event(db, match_id, "session_opened")
            await counsel_matching.append_session_event(db, match_id, "candidate_pool_checked", {"count": 3})

            updated = await counsel_matching.get_matching_session(db, hearing_id)
            assert len(updated["timeline"]) == 2
            assert updated["timeline"][0]["event"] == "session_opened"
            assert updated["timeline"][1]["event"] == "candidate_pool_checked"
            assert updated["timeline"][1]["detail"] == {"count": 3}
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())


def test_finalize_matching_session_sets_status_and_decision():
    async def body():
        db = await _db_with_indexes()
        hearing_id = f"test_hearing_{uuid.uuid4().hex[:10]}"
        try:
            session = await counsel_matching.get_or_create_matching_session(db, hearing_id)
            match_id = session["match_id"]
            finalized = await counsel_matching.finalize_matching_session(
                db, match_id, status="unmatched", final_decision="no_eligible_counsel",
            )
            assert finalized["status"] == "unmatched"
            assert finalized["final_decision"] == "no_eligible_counsel"

            refetched = await counsel_matching.get_matching_session(db, hearing_id)
            assert refetched["status"] == "unmatched"
            assert refetched["final_decision"] == "no_eligible_counsel"
        finally:
            await _cleanup(db, [hearing_id])
    asyncio.run(body())
