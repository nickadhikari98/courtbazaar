"""Order Management Agent — tool layer.

Thin, read-mostly wrappers around the EXISTING hearing/escrow/matching
services (hearings.py, escrow.py, counsel_matching.py) — this module owns no
business logic of its own and never touches HEARING_TRANSITIONS/
ESCROW_TRANSITIONS or any money/state-changing function. It exists only so
order_management_agent.py has a small, named set of functions to hand to the
LLM as tool calls, mirroring the exact reasoning already used by the admin
routes in server.py (e.g. the escalated-hearings cross-reference at
admin_list_hearing_requests) rather than re-deriving it.

The one write primitive here, flag_for_admin_review, writes ONLY to the new
agent_review_flags collection — it never writes to hearing_requests,
escrow_transactions, or counsel_matching_log. See the module docstring
convention already established by hearings.py/escrow.py: each module owns
exactly one collection's writes.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import escrow as escrow_svc
import hearings as hearings_svc
import counsel_matching as counsel_matching_svc


def new_flag_id() -> str:
    return f"flag_{uuid.uuid4().hex[:12]}"


async def ensure_indexes(db) -> None:
    await db.agent_review_flags.create_index([("hearing_id", 1), ("status", 1)], name="hearing_status")
    await db.agent_review_flags.create_index([("status", 1), ("created_at", -1)], name="status_created")


# ---------------------------------------------------------------------------
# Read-only tools
# ---------------------------------------------------------------------------
# Compact, LLM-oriented projection for list_hearings — NOT the same shape as
# hearings.list_hearings_for_admin's full documents (that function/route is
# untouched; the admin hearing-list UI still gets the full record). This
# tool feeds a chat-completions request, where every extra field is tokens
# spent on every call: full documents (case_details, request_details,
# hearing_notes, document_ids, and above all the unbounded `timeline` array)
# blew a single platform-wide summarize_all call past Groq's 8,000 TPM cap
# (observed: ~60,850 requested tokens for ~70 hearings). Only the fields a
# triage pass genuinely needs stay here; the agent already has
# get_hearing_detail/get_escrow_status/get_matching_session for anything
# deeper once it has picked a specific hearing_id to look at.
_LIST_HEARINGS_TRIAGE_FIELDS = {
    "_id": 0,
    "hearing_id": 1,
    "status": 1,
    "hearing_date": 1,
    "court_id": 1,
    "fee": 1,
    "verification_pending_at": 1,
    "order_sheet_reminder_sent_at": 1,
    "proxy_counsel_user_id": 1,
    "created_at": 1,
    "updated_at": 1,
}


async def list_hearings(db, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Compact triage projection, not the full hearing_requests document —
    see _LIST_HEARINGS_TRIAGE_FIELDS above. Same query shape (status filter,
    updated_at-desc, 200-row cap) as hearings.list_hearings_for_admin, just
    queried directly so that function's full-document contract for the admin
    UI stays untouched."""
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    return await db.hearing_requests.find(query, _LIST_HEARINGS_TRIAGE_FIELDS).sort("updated_at", -1).to_list(200)


# Second-stage context-size fix for summarize_all: even the compact
# list_hearings projection (~9,769 tokens for 70 hearings, measured) still
# exceeded Groq's 8,000 TPM cap once system prompt + tool schemas + the
# echoed tool call are added, because it always returns every hearing. This
# returns platform-wide COVERAGE (a count per status, computed via
# count_documents/aggregate — never row-capped, so no hearing is silently
# dropped from the tally) plus only the hearings that meet a genuine risk
# rule below — deterministic, not an LLM judgment call. Terminal statuses
# (completed/rated/cancelled/rejected/expired) never qualify, mirroring the
# system prompt's existing "don't flag terminal/normal hearings" guidance.
_ATTENTION_TERMINAL_STATUSES = {"completed", "rated", "cancelled", "rejected", "expired"}
# Statuses with their own dedicated rule below — excluded from the generic
# "stalled" catch-all so a hearing isn't flagged with a vague reason when a
# more specific one already applies (or doesn't yet apply).
_ATTENTION_RULE_COVERED_STATUSES = {"disputed", "verification_pending", "hearing_completed", "payment_pending", "verified"}
_ATTENTION_STALLED_THRESHOLD_DAYS = 5
_ATTENTION_VERIFICATION_APPROACHING_DAYS = 2  # hearings.AUTO_RELEASE_DELAY_DAYS - 1
_ATTENTION_PAYMENT_STALLED_DAYS = 1
_ATTENTION_ORDER_SHEET_STALE_DAYS = 3  # matches hearings.ORDER_SHEET_REMINDER_DELAY_DAYS
_ATTENTION_VERIFIED_STALE_DAYS = 3
_ATTENTION_SCAN_CAP = 1000  # safety valve, not a results cap — see get_attention_summary


def _age_in_days(iso_timestamp: Optional[str], now: datetime) -> Optional[float]:
    if not iso_timestamp:
        return None
    try:
        dt = datetime.fromisoformat(iso_timestamp)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 86400


def _attention_risk_reasons(hearing: Dict[str, Any], escalated_unassigned_ids: set, now: datetime) -> List[str]:
    reasons: List[str] = []
    status = hearing["status"]
    if status == "disputed":
        reasons.append("disputed")
    if status == "verification_pending":
        age = _age_in_days(hearing.get("verification_pending_at"), now)
        if age is not None and age >= _ATTENTION_VERIFICATION_APPROACHING_DAYS:
            reasons.append("verification_overdue" if age >= hearings_svc.AUTO_RELEASE_DELAY_DAYS
                            else "verification_approaching_auto_release")
    if status == "hearing_completed":
        age = _age_in_days(hearing.get("updated_at"), now)
        if age is not None and age >= _ATTENTION_ORDER_SHEET_STALE_DAYS:
            reasons.append("order_sheet_overdue")
    if status == "payment_pending":
        age = _age_in_days(hearing.get("updated_at"), now)
        if age is not None and age >= _ATTENTION_PAYMENT_STALLED_DAYS:
            reasons.append("payment_stalled")
    if status == "verified":
        age = _age_in_days(hearing.get("updated_at"), now)
        if age is not None and age >= _ATTENTION_VERIFIED_STALE_DAYS:
            reasons.append("payout_not_released")
    if hearing["hearing_id"] in escalated_unassigned_ids and not hearing.get("proxy_counsel_user_id"):
        reasons.append("escalated_unassigned")
    if status not in _ATTENTION_TERMINAL_STATUSES and status not in _ATTENTION_RULE_COVERED_STATUSES:
        age = _age_in_days(hearing.get("updated_at"), now)
        if age is not None and age >= _ATTENTION_STALLED_THRESHOLD_DAYS:
            reasons.append("stalled")
    return reasons


async def get_attention_summary(db) -> Dict[str, Any]:
    """Platform-wide triage in one small call: total hearing count, counts
    by status (full coverage, not sampled), and only the hearings that meet
    a genuine risk rule — see _attention_risk_reasons. Call this instead of
    list_hearings for a platform-wide summary; use get_hearing_detail/
    get_escrow_status/get_matching_session for a specific candidate only
    when its risk_reasons and triage fields aren't enough on their own."""
    total_hearings = await db.hearing_requests.count_documents({})
    status_rows = await db.hearing_requests.aggregate(
        [{"$group": {"_id": "$status", "count": {"$sum": 1}}}],
    ).to_list(None)
    by_status = {row["_id"]: row["count"] for row in status_rows}

    escalated_unassigned_ids = {
        row["hearing_id"]
        for row in await db.counsel_matching_log.find({"status": "escalated"}, {"_id": 0, "hearing_id": 1}).to_list(1000)
    }

    now = datetime.now(timezone.utc)
    candidates = await db.hearing_requests.find({}, _LIST_HEARINGS_TRIAGE_FIELDS).to_list(_ATTENTION_SCAN_CAP)
    if len(candidates) == _ATTENTION_SCAN_CAP:
        logging.getLogger(__name__).warning(
            "get_attention_summary hit its %s-row scan cap — some hearings were not evaluated for risk", _ATTENTION_SCAN_CAP,
        )

    attention_candidates = [
        {**h, "risk_reasons": reasons}
        for h in candidates
        if (reasons := _attention_risk_reasons(h, escalated_unassigned_ids, now))
    ]

    return {"total_hearings": total_hearings, "by_status": by_status, "attention_candidates": attention_candidates}


async def list_escalated_hearings(db) -> List[Dict[str, Any]]:
    """Same cross-reference server.py's admin_list_hearing_requests already
    performs for ?escalated=true (counsel_matching_log.status == "escalated"
    joined against hearing_requests) — duplicated here verbatim rather than
    imported from server.py, since server.py is the application entrypoint
    and importing from it would invert the dependency direction every other
    module in this codebase avoids."""
    escalated_sessions = await db.counsel_matching_log.find({"status": "escalated"}, {"_id": 0}).to_list(500)
    hearings_by_id = {
        h["hearing_id"]: h for h in await db.hearing_requests.find(
            {"hearing_id": {"$in": [s["hearing_id"] for s in escalated_sessions]}}, {"_id": 0},
        ).to_list(500)
    }
    results = []
    for session in escalated_sessions:
        hearing = hearings_by_id.get(session["hearing_id"])
        if hearing:
            results.append({**hearing, "escalation_reason": session.get("final_decision")})
    return results


async def get_hearing_detail(db, hearing_id: str) -> Optional[Dict[str, Any]]:
    """Admin-context lookup — deliberately bypasses hearings.get_hearing_request's
    _check_visible (that guard exists for participant-facing routes; this tool
    always runs with admin authority already enforced by the calling route)."""
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
    if not hearing:
        return None
    documents = await hearings_svc.list_documents(db, hearing_id)
    return {"hearing": hearing, "documents": documents}


async def get_escrow_status(db, hearing_id: str) -> Optional[Dict[str, Any]]:
    return await escrow_svc.get_for_context(db, "hearing", hearing_id)


async def get_matching_session(db, hearing_id: str) -> Optional[Dict[str, Any]]:
    return await counsel_matching_svc.get_matching_session(db, hearing_id)


# ---------------------------------------------------------------------------
# The one write tool — additive only, never touches an existing collection.
# ---------------------------------------------------------------------------
async def flag_for_admin_review(db, hearing_id: str, reason: str, agent_summary: str) -> Dict[str, Any]:
    """Idempotent: a hearing with an existing OPEN flag is not double-flagged
    — returns the existing flag instead of inserting a duplicate."""
    existing = await db.agent_review_flags.find_one(
        {"hearing_id": hearing_id, "status": "open"}, {"_id": 0},
    )
    if existing:
        return {"flag_id": existing["flag_id"], "ok": True, "created": False}

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "flag_id": new_flag_id(),
        "hearing_id": hearing_id,
        "reason": reason,
        "agent_summary": agent_summary,
        "status": "open",
        "created_at": now,
        "resolved_at": None,
        "resolved_by": None,
    }
    await db.agent_review_flags.insert_one(doc)
    return {"flag_id": doc["flag_id"], "ok": True, "created": True}


async def list_open_flags(db) -> List[Dict[str, Any]]:
    """Read helper for the admin UI — not an LLM tool, just how the summary
    route surfaces previously-raised flags alongside the fresh reasoning."""
    return await db.agent_review_flags.find({"status": "open"}, {"_id": 0}).sort("created_at", -1).to_list(200)
