"""Candidate Discovery Engine (roadmap M5).

Same rationale as test_counsel_matching_foundation.py: no HTTP endpoint
exists for this yet, so counsel_matching.discover_candidates is exercised
directly via Motor with plain asyncio.run() wrappers. Each test creates its
own throwaway hearing_requests row and proxy_counsel_profiles row(s) and
cleans them up in a finally block.
"""
import asyncio
import os
import sys
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import counsel_matching  # noqa: E402

from fastapi import HTTPException  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


async def _make_hearing(db):
    hearing_id = f"test_hearing_{uuid.uuid4().hex[:10]}"
    await db.hearing_requests.insert_one({
        "hearing_id": hearing_id, "court_id": "court_tishazari", "status": "requested",
    })
    return hearing_id


def _profile(user_id, kyc_status="approved", bar_council_verified=True, availability_mode=True):
    return {
        "user_id": user_id,
        "kyc_status": kyc_status,
        "bar_council_verified": bar_council_verified,
        "availability_mode": availability_mode,
        "practice_areas": [], "courts": [],
    }


async def _cleanup(db, hearing_ids=(), user_ids=()):
    if hearing_ids:
        await db.hearing_requests.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
    if user_ids:
        await db.proxy_counsel_profiles.delete_many({"user_id": {"$in": list(user_ids)}})


def test_discover_candidates_returns_fully_eligible_counsel():
    async def body():
        db = _db()
        hearing_id = await _make_hearing(db)
        counsel_id = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            await db.proxy_counsel_profiles.insert_one(_profile(counsel_id))
            results = await counsel_matching.discover_candidates(db, hearing_id)
            assert any(c["user_id"] == counsel_id for c in results)
        finally:
            await _cleanup(db, [hearing_id], [counsel_id])
    asyncio.run(body())


def test_discover_candidates_excludes_kyc_pending():
    async def body():
        db = _db()
        hearing_id = await _make_hearing(db)
        counsel_id = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            await db.proxy_counsel_profiles.insert_one(_profile(counsel_id, kyc_status="pending"))
            results = await counsel_matching.discover_candidates(db, hearing_id)
            assert not any(c["user_id"] == counsel_id for c in results)
        finally:
            await _cleanup(db, [hearing_id], [counsel_id])
    asyncio.run(body())


def test_discover_candidates_excludes_bar_council_unverified():
    async def body():
        db = _db()
        hearing_id = await _make_hearing(db)
        counsel_id = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            await db.proxy_counsel_profiles.insert_one(_profile(counsel_id, bar_council_verified=False))
            results = await counsel_matching.discover_candidates(db, hearing_id)
            assert not any(c["user_id"] == counsel_id for c in results)
        finally:
            await _cleanup(db, [hearing_id], [counsel_id])
    asyncio.run(body())


def test_discover_candidates_excludes_unavailable():
    async def body():
        db = _db()
        hearing_id = await _make_hearing(db)
        counsel_id = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            await db.proxy_counsel_profiles.insert_one(_profile(counsel_id, availability_mode=False))
            results = await counsel_matching.discover_candidates(db, hearing_id)
            assert not any(c["user_id"] == counsel_id for c in results)
        finally:
            await _cleanup(db, [hearing_id], [counsel_id])
    asyncio.run(body())


def test_discover_candidates_returns_multiple_eligible():
    async def body():
        db = _db()
        hearing_id = await _make_hearing(db)
        c1 = f"test_counsel_{uuid.uuid4().hex[:8]}"
        c2 = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            await db.proxy_counsel_profiles.insert_one(_profile(c1))
            await db.proxy_counsel_profiles.insert_one(_profile(c2))
            results = await counsel_matching.discover_candidates(db, hearing_id)
            found = {c["user_id"] for c in results}
            assert c1 in found and c2 in found
        finally:
            await _cleanup(db, [hearing_id], [c1, c2])
    asyncio.run(body())


def test_discover_candidates_empty_when_none_eligible():
    async def body():
        db = _db()
        hearing_id = await _make_hearing(db)
        counsel_id = f"test_counsel_{uuid.uuid4().hex[:8]}"
        try:
            # Ineligible on all three counts
            await db.proxy_counsel_profiles.insert_one(
                _profile(counsel_id, kyc_status="pending", bar_council_verified=False, availability_mode=False)
            )
            results = await counsel_matching.discover_candidates(db, hearing_id)
            assert not any(c["user_id"] == counsel_id for c in results)
        finally:
            await _cleanup(db, [hearing_id], [counsel_id])
    asyncio.run(body())


def test_discover_candidates_raises_404_for_missing_hearing():
    async def body():
        db = _db()
        with pytest.raises(HTTPException) as exc_info:
            await counsel_matching.discover_candidates(db, "nonexistent_hearing_xyz")
        assert exc_info.value.status_code == 404
    asyncio.run(body())
