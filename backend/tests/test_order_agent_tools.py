"""Order Management Agent — tool layer (order_agent_tools.py). Exercises the
5 read wrappers + the one write tool (flag_for_admin_review) directly against
a real local MongoDB, same conventions as test_hearings_auto_release.py.
Confirms every tool is a thin passthrough that reads existing collections
correctly and that the new agent_review_flags collection is the ONLY thing
this module ever writes to.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hearings  # noqa: E402
import escrow  # noqa: E402
import counsel_matching  # noqa: E402
import order_agent_tools  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _user(prefix):
    return {"user_id": f"test_oat_{prefix}_{uuid.uuid4().hex[:10]}"}


def _noop_put_object(path, data, content_type):
    return {"path": path, "size": len(data)}


def _noop_validate_upload(filename, content_type, size):
    return None


async def _hold_escrow(db, hearing_id, requester, fee):
    return await escrow.create_and_hold(
        db, context_type="hearing", context_id=hearing_id, service_id=hearings.ESCROW_SERVICE_ID,
        matter_id=None, payer_user_id=requester["user_id"], payee_user_id=None,
        amount=fee, platform_commission_pct=0.1,
        razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}", razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
    )


async def _cleanup(db, hearing_ids=(), user_ids=(), flag_ids=()):
    if hearing_ids:
        await db.hearing_requests.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
        await db.escrow_transactions.delete_many({"context_id": {"$in": list(hearing_ids)}})
        await db.hearing_documents.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
        await db.wallet_transactions.delete_many({"related_entity_id": {"$in": list(hearing_ids)}})
        await db.counsel_matching_log.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
        await db.agent_review_flags.delete_many({"hearing_id": {"$in": list(hearing_ids)}})
    if user_ids:
        await db.proxy_counsel_profiles.delete_many({"user_id": {"$in": list(user_ids)}})
    if flag_ids:
        await db.agent_review_flags.delete_many({"flag_id": {"$in": list(flag_ids)}})


async def _drive_to_verification_pending(db, requester, counsel, fee=1500.0):
    hearing = await hearings.create_hearing_request(
        db, requester["user_id"], "court_tishazari", "2026-08-01", "Test case", fee, None,
    )
    hearing_id = hearing["hearing_id"]
    await hearings.initiate_payment(db, hearing_id, requester)
    await _hold_escrow(db, hearing_id, requester, fee)
    await hearings.mark_payment_confirmed(db, hearing_id, requester)
    await hearings.accept_hearing_request(db, hearing_id, counsel)
    await hearings.add_document(db, _noop_put_object, _noop_validate_upload, hearing_id, counsel,
                                 "case_document", "brief.pdf", "application/pdf", b"x")
    await hearings.mark_hearing_conducted(db, hearing_id, counsel)
    await hearings.add_document(db, _noop_put_object, _noop_validate_upload, hearing_id, counsel,
                                 "order_sheet", "order.pdf", "application/pdf", b"x")
    return hearing_id


def test_list_hearings_returns_created_hearing():
    async def body():
        db = _db()
        requester = _user("requester")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-09-01", "Test case", 1000.0, None,
            )
            hearing_id = hearing["hearing_id"]
            all_hearings = await order_agent_tools.list_hearings(db)
            assert any(h["hearing_id"] == hearing_id for h in all_hearings)
            requested_only = await order_agent_tools.list_hearings(db, status="requested")
            assert any(h["hearing_id"] == hearing_id for h in requested_only)
            broadcast_only = await order_agent_tools.list_hearings(db, status="broadcast")
            assert not any(h["hearing_id"] == hearing_id for h in broadcast_only)
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_list_hearings_status_none_matches_no_filter():
    """Regression: explicit status=None (the shape _execute_tool passes
    through from a Groq {"status": null} tool-call arg) must behave exactly
    like omitting the status kwarg, not raise or silently filter everything
    out."""
    async def body():
        db = _db()
        requester = _user("requester")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-09-01", "Test case", 1000.0, None,
            )
            hearing_id = hearing["hearing_id"]
            no_kwarg = await order_agent_tools.list_hearings(db)
            explicit_none = await order_agent_tools.list_hearings(db, status=None)
            assert any(h["hearing_id"] == hearing_id for h in no_kwarg)
            assert any(h["hearing_id"] == hearing_id for h in explicit_none)
            assert {h["hearing_id"] for h in no_kwarg} == {h["hearing_id"] for h in explicit_none}
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_list_hearings_returns_compact_triage_projection_only():
    """The LLM-facing list_hearings result must be a compact triage
    projection, not the full hearing_requests document — this is the fix for
    the Groq 413 (list_hearings' full-document result blew past the 8,000
    TPM cap). Drives a hearing through enough of its lifecycle to populate
    every field that must NOT be in the compact result (case_details,
    request_details, timeline, hearing_notes, document_ids, declined_by,
    rated_by) alongside the fields that must be."""
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = None
        try:
            hearing_id = await _drive_to_verification_pending(db, requester, counsel, fee=1234.0)
            # Sanity: the full document genuinely does carry the large fields
            # this test asserts are excluded from the compact projection —
            # otherwise this test would pass trivially.
            full = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert len(full["timeline"]) > 0
            assert "case_details" in full and "request_details" in full

            results = await order_agent_tools.list_hearings(db, status="verification_pending")
            match = next(h for h in results if h["hearing_id"] == hearing_id)

            expected_fields = {
                "hearing_id", "status", "hearing_date", "court_id", "fee",
                "verification_pending_at", "order_sheet_reminder_sent_at",
                "proxy_counsel_user_id", "created_at", "updated_at",
            }
            assert set(match.keys()) == expected_fields
            assert match["status"] == "verification_pending"
            assert match["fee"] == 1234.0

            large_fields = {
                "timeline", "case_details", "request_details", "hearing_notes",
                "document_ids", "declined_by", "rated_by", "requesting_user_id",
                "target_advocate_id", "matter_id", "service_type",
                "commercially_locked", "order_sheet_doc_id",
            }
            assert not (large_fields & set(match.keys()))
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [], [counsel["user_id"]])
    asyncio.run(body())


def test_list_escalated_hearings_cross_references_matching_log():
    async def body():
        db = _db()
        requester = _user("requester")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-09-01", "Test case", 1000.0, None,
            )
            hearing_id = hearing["hearing_id"]
            # Force status to "broadcast" directly (bypassing payment) so
            # escalate_to_admin's own status=="broadcast" guard doesn't reject it.
            await db.hearing_requests.update_one({"hearing_id": hearing_id}, {"$set": {"status": "broadcast"}})
            await counsel_matching.get_or_create_matching_session(db, hearing_id)
            hearing["status"] = "broadcast"
            await counsel_matching.escalate_to_admin(db, hearing, reason="no_eligible_candidates")

            escalated = await order_agent_tools.list_escalated_hearings(db)
            match = next((h for h in escalated if h["hearing_id"] == hearing_id), None)
            assert match is not None
            assert match["escalation_reason"] == "no_eligible_candidates"

            not_escalated = await order_agent_tools.list_hearings(db, status="requested")
            assert not any(h["hearing_id"] == hearing_id for h in not_escalated
                            if "escalation_reason" in h)
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_get_attention_summary_covers_every_hearing():
    """Second-stage context-size fix regression: by_status/total_hearings
    must come from count_documents/aggregate (uncapped), not from a capped
    row-return list — otherwise hearings created after the 200-row list_hearings
    cap (or the 1000-row candidate scan cap) would silently vanish from
    platform-wide coverage. Asserts total_hearings matches a fresh
    count_documents call made independently, and that a freshly created
    hearing is counted in by_status."""
    async def body():
        db = _db()
        requester = _user("requester")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-09-01", "Test case", 1000.0, None,
            )
            hearing_id = hearing["hearing_id"]
            true_total = await db.hearing_requests.count_documents({})

            summary = await order_agent_tools.get_attention_summary(db)
            assert summary["total_hearings"] == true_total
            assert summary["by_status"].get("requested", 0) >= 1
            assert sum(summary["by_status"].values()) == true_total
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())


def test_get_attention_summary_does_not_drop_disputed_candidate():
    """A genuinely at-risk hearing (disputed) must always appear in
    attention_candidates — the one case the requirements explicitly say must
    never be silently hidden."""
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = None
        try:
            hearing_id = await _drive_to_verification_pending(db, requester, counsel)
            await hearings.reject_order_sheet(db, hearing_id, requester, remark="wrong order")
            summary = await order_agent_tools.get_attention_summary(db)
            match = next((c for c in summary["attention_candidates"] if c["hearing_id"] == hearing_id), None)
            assert match is not None
            assert "disputed" in match["risk_reasons"]
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [], [counsel["user_id"]])
    asyncio.run(body())


def test_get_attention_summary_detects_verification_overdue():
    """A verification_pending hearing whose clock has run past
    hearings.AUTO_RELEASE_DELAY_DAYS must be flagged verification_overdue —
    exactly the auto-release-deadline risk case the requirements call out by
    name."""
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = None
        try:
            hearing_id = await _drive_to_verification_pending(db, requester, counsel)
            stale_at = (datetime.now(timezone.utc) - timedelta(days=hearings.AUTO_RELEASE_DELAY_DAYS, hours=1)).isoformat()
            await db.hearing_requests.update_one({"hearing_id": hearing_id}, {"$set": {"verification_pending_at": stale_at}})

            summary = await order_agent_tools.get_attention_summary(db)
            match = next((c for c in summary["attention_candidates"] if c["hearing_id"] == hearing_id), None)
            assert match is not None
            assert "verification_overdue" in match["risk_reasons"]
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [], [counsel["user_id"]])
    asyncio.run(body())


def test_get_attention_summary_candidates_carry_no_large_fields():
    """The whole point of get_attention_summary is a small LLM payload — a
    candidate must never carry timeline/case_details/request_details/
    hearing_notes/document_ids, same guarantee as list_hearings' compact
    projection, plus the one extra field (risk_reasons) this tool adds."""
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = None
        try:
            hearing_id = await _drive_to_verification_pending(db, requester, counsel)
            await hearings.reject_order_sheet(db, hearing_id, requester, remark="wrong order")

            summary = await order_agent_tools.get_attention_summary(db)
            match = next(c for c in summary["attention_candidates"] if c["hearing_id"] == hearing_id)

            expected_fields = {
                "hearing_id", "status", "hearing_date", "court_id", "fee",
                "verification_pending_at", "order_sheet_reminder_sent_at",
                "proxy_counsel_user_id", "created_at", "updated_at", "risk_reasons",
            }
            assert set(match.keys()) == expected_fields
            large_fields = {"timeline", "case_details", "request_details", "hearing_notes", "document_ids"}
            assert not (large_fields & set(match.keys()))
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [], [counsel["user_id"]])
    asyncio.run(body())


def test_get_hearing_detail_includes_documents():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = None
        try:
            hearing_id = await _drive_to_verification_pending(db, requester, counsel)
            detail = await order_agent_tools.get_hearing_detail(db, hearing_id)
            assert detail is not None
            assert detail["hearing"]["hearing_id"] == hearing_id
            assert detail["hearing"]["status"] == "verification_pending"
            kinds = {d["kind"] for d in detail["documents"]}
            assert kinds == {"case_document", "order_sheet"}
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [], [counsel["user_id"]])
    asyncio.run(body())


def test_get_hearing_detail_returns_none_for_missing_hearing():
    async def body():
        db = _db()
        detail = await order_agent_tools.get_hearing_detail(db, "hearing_does_not_exist")
        assert detail is None
    asyncio.run(body())


def test_get_escrow_status_reflects_held_amount():
    async def body():
        db = _db()
        requester, counsel = _user("requester"), _user("counsel")
        hearing_id = None
        try:
            hearing_id = await _drive_to_verification_pending(db, requester, counsel, fee=2000.0)
            status = await order_agent_tools.get_escrow_status(db, hearing_id)
            assert status is not None
            assert status["status"] == "held"
            assert status["amount"] == 2000.0
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [], [counsel["user_id"]])
    asyncio.run(body())


def test_get_matching_session_returns_none_when_no_session():
    async def body():
        db = _db()
        session = await order_agent_tools.get_matching_session(db, "hearing_no_session_exists")
        assert session is None
    asyncio.run(body())


def test_flag_for_admin_review_creates_and_is_idempotent():
    async def body():
        db = _db()
        hearing_id = f"hearing_flagtest_{uuid.uuid4().hex[:10]}"
        try:
            first = await order_agent_tools.flag_for_admin_review(
                db, hearing_id, "stalled", "No activity for 5 days",
            )
            assert first["ok"] is True
            assert first["created"] is True

            second = await order_agent_tools.flag_for_admin_review(
                db, hearing_id, "stalled again", "Different summary",
            )
            assert second["ok"] is True
            assert second["created"] is False
            assert second["flag_id"] == first["flag_id"]

            count = await db.agent_review_flags.count_documents({"hearing_id": hearing_id})
            assert count == 1

            open_flags = await order_agent_tools.list_open_flags(db)
            assert any(f["flag_id"] == first["flag_id"] for f in open_flags)
        finally:
            await db.agent_review_flags.delete_many({"hearing_id": hearing_id})
    asyncio.run(body())


def test_flag_for_admin_review_never_touches_hearing_requests():
    """The one write tool must be additive-only — confirms no side effect
    lands on hearing_requests even when a real hearing_id is used."""
    async def body():
        db = _db()
        requester = _user("requester")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-09-01", "Test case", 1000.0, None,
            )
            hearing_id = hearing["hearing_id"]
            before = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})

            await order_agent_tools.flag_for_admin_review(db, hearing_id, "stalled", "summary")

            after = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert before == after
        finally:
            await _cleanup(db, [hearing_id] if hearing_id else [])
    asyncio.run(body())
