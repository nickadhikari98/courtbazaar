"""Deactivated / deleted accounts never reach clients (Admin → Users,
Oct 15 2026).

Admin → Users' row trash icon only deactivates (audit_log.deactivate_user:
users.deleted = True); "Delete selected" removes the users row and the
profile rows with it (audit_log.permanently_delete_users). Every listing,
profile page, recommendation, matching and auto-assignment path reads the
profile collections directly, so each one is pinned here:

- counsels: counsel_matching.drop_deactivated / deactivated_user_ids
  (same helper as PR #62) — search/browse, recommendations, the chatbot's
  counsel search (it calls list_and_recommend), auto top-5 fallback,
  hearing-time discovery, public + authenticated profile pages, and direct
  booking by target_advocate_id;
- vendors: server._drop_deactivated_vendors — /vendors, /stenographers and
  order/stenographer auto-assignment.

Both also hide a profile whose users row is gone (orphaned).

Same convention as test_chat_authorization.py: route functions are called
directly with server.db swapped for a per-test Motor client.
"""
import asyncio
import os
import sys
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import counsel_matching  # noqa: E402
import server  # noqa: E402
from audit_log import deactivate_user, permanently_delete_users  # noqa: E402


@pytest.fixture(autouse=True)
def db(monkeypatch):
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    monkeypatch.setattr(server, "db", client[os.environ["DB_NAME"]])
    yield server.db
    client.close()


def _tag():
    return uuid.uuid4().hex[:10]


def _request():
    return SimpleNamespace(client=SimpleNamespace(host=f"198.51.100.{uuid.uuid4().int % 250 + 1}"))


CLIENT = {"user_id": "test_vis_client", "role": "client", "capabilities": ["can_hire_proxy_counsel"]}


async def _counsel(db, court, name):
    """A real, fully verified, available counsel listed for `court`."""
    user_id = f"test_vis_{name}_{_tag()}"
    await db.users.insert_one({"user_id": user_id, "name": name, "email": f"{user_id}@cbqa.in", "role": "advocate"})
    await db.proxy_counsel_profiles.insert_one({
        "user_id": user_id, "kyc_status": "approved", "bar_council_verified": True, "availability_mode": True,
        "practice_areas": [], "courts": [court], "experience_years": 5, "rating": 4, "cases_completed": 3,
        "fee_structure": None, "instant_booking": False,
    })
    return user_id


async def _court_with_active_and_deactivated(db):
    court = f"court_vis_{_tag()}"
    active = await _counsel(db, court, "Active")
    gone = await _counsel(db, court, "Gone")
    await deactivate_user(db, gone, "test_vis_admin")
    return court, active, gone


def _ids(cards, key="advocate_id"):
    return {c[key] for c in cards}


# --- counsel listings / recommendations / matching --------------------------

def test_list_and_recommend_excludes_deactivated_counsel(db):
    async def body():
        court, active, gone = await _court_with_active_and_deactivated(db)
        ranked, total = await counsel_matching.list_and_recommend(db, court_id=court)
        assert {c["user_id"] for c in ranked} == {active}
        assert total == 1
    asyncio.run(body())


def test_public_browse_list_excludes_deactivated_counsel(db):
    async def body():
        court, active, gone = await _court_with_active_and_deactivated(db)
        out = await server.public_proxy_counsels(_request(), court_id=court)
        assert _ids(out["advocates"]) == {active}
        assert out["metadata"]["total_candidates"] == 1
    asyncio.run(body())


def test_authenticated_recommendations_exclude_deactivated_counsel(db):
    async def body():
        court, active, gone = await _court_with_active_and_deactivated(db)
        out = await server.recommendations_advocates(court_id=court, user=CLIENT)
        assert _ids(out["advocates"]) == {active}
    asyncio.run(body())


def test_auto_fallback_candidates_exclude_deactivated_counsel(db):
    async def body():
        court, active, gone = await _court_with_active_and_deactivated(db)
        hearing = {"court_id": court, "hearing_date": None, "request_details": {}}
        picked = await counsel_matching.top_fallback_candidates(db, hearing, set())
        assert {c["user_id"] for c in picked} == {active}
    asyncio.run(body())


def test_hearing_time_discovery_excludes_deactivated_counsel(db):
    async def body():
        court, active, gone = await _court_with_active_and_deactivated(db)
        broadcast = f"hearing_vis_{_tag()}"
        targeted = f"hearing_vis_{_tag()}"
        # Full-shape rows (status etc.): the test DB is shared for the whole
        # session and other suites (order_agent_tools) scan every hearing.
        for hearing_id, target in ((broadcast, None), (targeted, gone)):
            await db.hearing_requests.insert_one({
                "hearing_id": hearing_id, "requesting_user_id": CLIENT["user_id"], "proxy_counsel_user_id": None,
                "target_advocate_id": target, "court_id": court, "hearing_date": "2026-12-01",
                "case_details": "Bail hearing", "status": "requested", "created_at": "2026-10-15T00:00:00+00:00",
            })
        try:
            pool = {c["user_id"] for c in await counsel_matching.discover_candidates(db, broadcast)}
            assert active in pool and gone not in pool
            assert await counsel_matching.discover_candidates(db, targeted) == []
        finally:
            await db.hearing_requests.delete_many({"hearing_id": {"$in": [broadcast, targeted]}})
    asyncio.run(body())


# --- profile pages + direct booking --------------------------------------

@pytest.mark.parametrize("route", ["public", "authenticated"])
def test_profile_page_404s_for_deactivated_counsel(db, route):
    async def body():
        court, active, gone = await _court_with_active_and_deactivated(db)
        fetch = ((lambda aid: server.get_public_advocate_profile(aid, _request())) if route == "public"
                 else (lambda aid: server.get_advocate_profile(aid, user=CLIENT)))
        assert (await fetch(active))["advocate_id"] == active
        with pytest.raises(HTTPException) as exc:
            await fetch(gone)
        assert exc.value.status_code == 404
    asyncio.run(body())


def test_direct_booking_of_deactivated_counsel_is_404(db):
    async def body():
        court, active, gone = await _court_with_active_and_deactivated(db)
        payload = server.HearingRequestCreate(court_id=court, hearing_date="2026-12-01",
                                              case_details="Bail hearing", target_advocate_id=gone)
        with pytest.raises(HTTPException) as exc:
            await server.create_hearing_request(payload, user=CLIENT)
        assert exc.value.status_code == 404
        assert await db.hearing_requests.count_documents({"target_advocate_id": gone}) == 0
    asyncio.run(body())


def test_direct_booking_of_active_counsel_still_works(db):
    """Found in browser E2E (Oct 15 2026): the first cut of the booking
    guard 404'd every live counsel whose users row has no `deleted` field."""
    async def body():
        court = f"court_vis_{_tag()}"
        active = await _counsel(db, court, "Bookable")
        payload = server.HearingRequestCreate(court_id=court, hearing_date="2026-12-01",
                                              case_details="Bail hearing", target_advocate_id=active)
        try:
            hearing = await server.create_hearing_request(payload, user=CLIENT)
            assert hearing["target_advocate_id"] == active
        finally:
            await db.hearing_requests.delete_many({"target_advocate_id": active})
    asyncio.run(body())


def test_permanently_deleted_counsel_disappears_everywhere(db):
    async def body():
        court = f"court_vis_{_tag()}"
        keep = await _counsel(db, court, "Keep")
        doomed = await _counsel(db, court, "Doomed")
        await db.users.insert_one({"user_id": "test_vis_admin2", "role": "admin"})
        result = await permanently_delete_users(db, [doomed], {"user_id": "test_vis_admin2", "role": "admin"})
        assert result["deleted"] == [doomed]

        assert _ids((await server.public_proxy_counsels(_request(), court_id=court))["advocates"]) == {keep}
        for fetch in (server.get_public_advocate_profile(doomed, _request()), server.get_advocate_profile(doomed, user=CLIENT)):
            with pytest.raises(HTTPException) as exc:
                await fetch
            assert exc.value.status_code == 404

        # Found in browser E2E (Oct 15 2026): direct booking by id used to
        # succeed for a deleted counsel, since no users row means "not
        # deactivated" to deactivated_user_ids.
        payload = server.HearingRequestCreate(court_id=court, hearing_date="2026-12-01",
                                              case_details="Bail hearing", target_advocate_id=doomed)
        with pytest.raises(HTTPException) as exc:
            await server.create_hearing_request(payload, user=CLIENT)
        assert exc.value.status_code == 404
        assert await db.hearing_requests.count_documents({"target_advocate_id": doomed}) == 0
    asyncio.run(body())


# --- vendors -------------------------------------------------------------

async def _vendors(db, court, category=None):
    """An active vendor, a deactivated one, and an orphaned one whose users
    row is gone (what the first version of "Delete selected" left behind)."""
    rows = {}
    for kind in ("active", "gone", "orphan"):
        uid = f"test_vis_v{kind}_{_tag()}"
        if kind != "orphan":
            await db.users.insert_one({"user_id": uid, "name": kind, "email": f"{uid}@cbqa.in", "role": "vendor"})
        doc = {"vendor_id": uid, "user_id": uid, "shop_name": kind, "kyc_status": "approved", "court_ids": [court],
               "rating": 4}
        if category:
            doc["vendor_category"] = category
        await db.vendors.insert_one(doc)
        rows[kind] = uid
    await deactivate_user(db, rows["gone"], "test_vis_admin")
    return rows


def test_vendor_list_excludes_deactivated_and_orphaned_vendors(db):
    async def body():
        court = f"court_vis_{_tag()}"
        v = await _vendors(db, court)
        assert {x["vendor_id"] for x in await server.list_vendors(court_id=court)} == {v["active"]}
    asyncio.run(body())


def test_stenographer_list_excludes_deactivated_and_orphaned_vendors(db):
    async def body():
        court = f"court_vis_{_tag()}"
        v = await _vendors(db, court, category="stenographer")
        assert {x["vendor_id"] for x in await server.list_stenographers(court_id=court)} == {v["active"]}
    asyncio.run(body())


def test_vendor_auto_assignment_pool_skips_deactivated_and_orphaned_vendors(db):
    """create_order, bulk orders and stenographer booking all build their
    auto-match pool through _drop_deactivated_vendors."""
    async def body():
        court = f"court_vis_{_tag()}"
        v = await _vendors(db, court)
        pool = await db.vendors.find({"court_ids": court, "kyc_status": "approved"}, {"_id": 0}).to_list(20)
        assert {x["vendor_id"] for x in await server._drop_deactivated_vendors(pool)} == {v["active"]}
    asyncio.run(body())


def test_hearing_counsel_card_404s_for_deactivated_counsel(db):
    """/hearing-requests/{id}/counsel-profile — the Negotiation page's
    counsel card on a client's own targeted hearing."""
    async def body():
        court, active, gone = await _court_with_active_and_deactivated(db)
        ids = []
        for target in (active, gone):
            hid = f"hearing_vis_{_tag()}"
            ids.append(hid)
            await db.hearing_requests.insert_one({
                "hearing_id": hid, "requesting_user_id": CLIENT["user_id"], "proxy_counsel_user_id": None,
                "target_advocate_id": target, "court_id": court, "hearing_date": "2026-12-01",
                "case_details": "Bail hearing", "status": "requested", "created_at": "2026-10-15T00:00:00+00:00",
            })
        try:
            assert (await server.get_hearing_counsel_profile(ids[0], user=CLIENT))["advocate_id"] == active
            with pytest.raises(HTTPException) as exc:
                await server.get_hearing_counsel_profile(ids[1], user=CLIENT)
            assert exc.value.status_code == 404
        finally:
            await db.hearing_requests.delete_many({"hearing_id": {"$in": ids}})
    asyncio.run(body())


# --- Orphaned counsel profiles (users row gone) ----------------------------

async def _orphan_counsel(db, court):
    """A verified, available profile whose account no longer exists — what
    the first version of "Delete selected" left behind on Oct 15 2026."""
    user_id = f"test_vis_orphan_{_tag()}"
    await db.proxy_counsel_profiles.insert_one({
        "user_id": user_id, "kyc_status": "approved", "bar_council_verified": True, "availability_mode": True,
        "practice_areas": [], "courts": [court], "experience_years": 5, "rating": 4, "cases_completed": 3,
        "fee_structure": None, "instant_booking": False,
    })
    return user_id


def test_orphaned_counsel_never_reaches_clients(db):
    async def body():
        court = f"court_vis_{_tag()}"
        active = await _counsel(db, court, "Active")
        orphan = await _orphan_counsel(db, court)

        ranked, total = await counsel_matching.list_and_recommend(db, court_id=court)
        assert {c["user_id"] for c in ranked} == {active} and total == 1
        assert _ids((await server.public_proxy_counsels(_request(), court_id=court))["advocates"]) == {active}
        assert _ids((await server.recommendations_advocates(court_id=court, user=CLIENT))["advocates"]) == {active}
        fallback = await counsel_matching.top_fallback_candidates(db, {"court_id": court, "request_details": {}}, set())
        assert {c["user_id"] for c in fallback} == {active}

        for fetch in (server.get_public_advocate_profile(orphan, _request()), server.get_advocate_profile(orphan, user=CLIENT)):
            with pytest.raises(HTTPException) as exc:
                await fetch
            assert exc.value.status_code == 404

        payload = server.HearingRequestCreate(court_id=court, hearing_date="2026-12-01",
                                              case_details="Bail hearing", target_advocate_id=orphan)
        with pytest.raises(HTTPException) as exc:
            await server.create_hearing_request(payload, user=CLIENT)
        assert exc.value.status_code == 404
    asyncio.run(body())


def test_orphaned_counsel_is_not_matched_at_hearing_time(db):
    async def body():
        court = f"court_vis_{_tag()}"
        active = await _counsel(db, court, "Active")
        orphan = await _orphan_counsel(db, court)
        broadcast, targeted = f"hearing_vis_{_tag()}", f"hearing_vis_{_tag()}"
        for hearing_id, target in ((broadcast, None), (targeted, orphan)):
            await db.hearing_requests.insert_one({
                "hearing_id": hearing_id, "requesting_user_id": CLIENT["user_id"], "proxy_counsel_user_id": None,
                "target_advocate_id": target, "court_id": court, "hearing_date": "2026-12-01",
                "case_details": "Bail hearing", "status": "requested", "created_at": "2026-10-15T00:00:00+00:00",
            })
        try:
            pool = {c["user_id"] for c in await counsel_matching.discover_candidates(db, broadcast)}
            assert active in pool and orphan not in pool
            assert await counsel_matching.discover_candidates(db, targeted) == []
        finally:
            await db.hearing_requests.delete_many({"hearing_id": {"$in": [broadcast, targeted]}})
    asyncio.run(body())
