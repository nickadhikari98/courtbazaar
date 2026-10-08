"""Phase 3C-A — public, read-only live CourtBazaar data tools for Instant
Legal Help (see ai_chat.py's module docstring for where Phase 2 conversation
handling ends and this begins).

Every function here is a thin wrapper around an already-existing, already-
tested service function or route body — court_seed/counsel_matching/server.py
own the real business logic; nothing here re-implements a query, a filter, or
a card shape that already exists elsewhere. Reused as-is:
  - counsel_matching.list_and_recommend / public_advocate_card / verified_counsel_query
  - server.py's _advocate_cards_for / _advocate_profile_or_404 (lazy-imported,
    same cross-module convention this codebase already uses everywhere else,
    e.g. counsel_matching.admin_assign_counsel importing hearings)

Every tool returns one normalized envelope so ai_chat.py never needs to know
which underlying exception type failed — same fail-soft, normalized-result
convention as llm_service.generate_response:
    {"status": "success", "tool": <name>, "data": ..., ...extra}
    {"status": "empty",   "tool": <name>, "data": [] | None, ...extra}
    {"status": "error",   "tool": <name>, "message": <safe, user-facing text>}
`message` on an error envelope is the ONLY thing ai_chat.py may surface to a
user — the real exception is logged here and never returned.

Phase 3C-A tools (public, no auth): get_states/get_courts/get_court/
get_services/search_proxy_counsels/get_proxy_counsel_profile.

Phase 3C-B tools (authenticated, read-only): get_my_orders/get_order/
get_my_hearing_requests/get_hearing_request. Each takes the caller's
server-resolved `user` dict as a required argument and reuses the exact
ownership logic the real routes already enforce — server.py's list_orders/
get_order role-and-ownership checks (mirrored here the same way
get_states/get_courts/etc. mirror their route bodies, since /orders has no
separate service module to import), and hearings.list_hearing_requests/
get_hearing_request/_check_visible (imported and called unchanged). A 403 or
404 on a single-item lookup is deliberately collapsed into the same "empty"
envelope — this module never distinguishes "not yours" from "doesn't exist"
in what it returns, so nothing here can be used to enumerate another user's
orders or hearings. Every authenticated tool also returns each document
trimmed to a small, chat-relevant summary (see _order_summary/
_hearing_summary) — never the raw Mongo document — dropping internal
scheduling fields, other users' ids, and anything not needed to answer a
status question.

Phase 5 — own data only. These tools are narrower than the HTTP routes
they mirror: an admin role, a proxy counsel's view of the open broadcast
pool, or a targeted pre-payment negotiation never widens what the chatbot
returns. A caller sees an order only when they placed it or are its vendor,
and a hearing request only when they requested it or are its assigned
Proxy Counsel. The admin panel and the hearings pages remain the places for
that wider access; a chat answer to "my orders" is never another user's
data. Identifiers from message text or LLM output are only lookup keys —
ownership is always re-checked here against the database.

None of these four ever accept a user_id as an argument — only `user`, the
dict FastAPI's own JWT dependency resolved for the actual authenticated
caller. Callers (ai_chat.py) must never construct or forward a `user` dict
from message text, LLM output, or any other untrusted source.
"""
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TOOL_GET_STATES = "get_states"
TOOL_GET_COURTS = "get_courts"
TOOL_GET_COURT = "get_court"
TOOL_GET_SERVICES = "get_services"
TOOL_SEARCH_PROXY_COUNSELS = "search_proxy_counsels"
TOOL_GET_PROXY_COUNSEL_PROFILE = "get_proxy_counsel_profile"
TOOL_GET_MY_ORDERS = "get_my_orders"
TOOL_GET_ORDER = "get_order"
TOOL_GET_MY_HEARING_REQUESTS = "get_my_hearing_requests"
TOOL_GET_HEARING_REQUEST = "get_hearing_request"

# The only tool names ai_chat.py's routing layer is allowed to invoke — a
# closed registry, not something the LLM can extend or bypass. See
# ai_chat.py's _route_tool_call for the fixed if/elif chain this guards —
# every branch in it calls one of exactly these functions, by hardcoded name.
REGISTERED_TOOLS = (
    TOOL_GET_STATES, TOOL_GET_COURTS, TOOL_GET_COURT, TOOL_GET_SERVICES,
    TOOL_SEARCH_PROXY_COUNSELS, TOOL_GET_PROXY_COUNSEL_PROFILE,
    TOOL_GET_MY_ORDERS, TOOL_GET_ORDER, TOOL_GET_MY_HEARING_REQUESTS, TOOL_GET_HEARING_REQUEST,
)

# Tools in this set require a real, server-resolved `user` dict — ai_chat.py
# checks this before ever routing to one, so an anonymous caller never
# reaches this module for a private tool at all (no DB call happens).
AUTH_REQUIRED_TOOLS = (
    TOOL_GET_MY_ORDERS, TOOL_GET_ORDER, TOOL_GET_MY_HEARING_REQUESTS, TOOL_GET_HEARING_REQUEST,
)

# The single user-facing text for any public live-tool failure — ai_chat.py's
# LIVE_TOOL_FAILURE_MESSAGE is this same constant, so a tool's own error
# envelope and ai_chat's timeout/routing failures always read identically.
ERROR_MESSAGE = "I couldn't retrieve that live CourtBazaar information right now. Please try again shortly."
AUTH_ERROR_MESSAGE = "Unable to retrieve your CourtBazaar information right now."


def _success(tool: str, data: Any, **extra: Any) -> Dict[str, Any]:
    status = "empty" if (isinstance(data, list) and not data) or data is None else "success"
    return {"status": status, "tool": tool, "data": data, **extra}


def _error(tool: str, exc: Exception, message: str = ERROR_MESSAGE) -> Dict[str, Any]:
    """Logs the real exception server-side only; the caller (ai_chat.py, and
    through it the LLM/user) only ever sees `message` — no stack trace, Mongo
    error text, or other internal detail crosses this boundary."""
    import llm_service
    detail = llm_service._safe_error_detail(exc)
    logger.error("court_bazaar_tools.%s failed (%s): %s", tool, type(exc).__name__, detail)
    return {"status": "error", "tool": tool, "message": message}


# Every record id this module looks up (court_, adv_/user_, ORD..., hearing_)
# is a short alphanumeric/underscore token. Anything else — an operator
# object, a huge string, punctuation — is treated exactly like an id that
# doesn't exist, before it reaches a query.
_LOOKUP_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _valid_lookup_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_LOOKUP_ID_RE.fullmatch(value))


def _empty(tool: str) -> Dict[str, Any]:
    return {"status": "empty", "tool": tool, "data": None}


def _require_user(tool: str, user: Optional[dict]) -> Optional[Dict[str, Any]]:
    """Defense in depth only — ai_chat.py's routing is what actually keeps an
    anonymous caller from reaching here at all (see AUTH_REQUIRED_TOOLS
    above), so this should never fire in practice. If it ever does (a bug
    upstream), fail safely instead of crashing or querying with no user
    scope."""
    if not user or not user.get("user_id"):
        logger.error("court_bazaar_tools.%s called without an authenticated user", tool)
        return {"status": "error", "tool": tool, "message": AUTH_ERROR_MESSAGE}
    return None


async def get_states(db) -> Dict[str, Any]:
    """Mirrors GET /api/states exactly (server.py's list_states)."""
    try:
        states = await db.states.find({}, {"_id": 0}).sort("name", 1).to_list(100)
        return _success(TOOL_GET_STATES, states)
    except Exception as e:
        return _error(TOOL_GET_STATES, e)


async def get_courts(db, state_id: Optional[str] = None, q: Optional[str] = None,
                      serviceable_only: bool = False) -> Dict[str, Any]:
    """Mirrors GET /api/courts exactly (server.py's list_courts) — same query
    shape, same has_coordinates omission is intentional: that filter powers a
    map view, not a conversational answer."""
    try:
        query: Dict[str, Any] = {}
        if state_id:
            query["state_id"] = state_id
        if q:
            query["name"] = {"$regex": q, "$options": "i"}
        if serviceable_only:
            query["serviceable"] = True
        courts = await db.courts.find(query, {"_id": 0}).sort("name", 1).to_list(2000)
        return _success(TOOL_GET_COURTS, courts,
                         filters_applied={"state_id": state_id, "q": q, "serviceable_only": serviceable_only})
    except Exception as e:
        return _error(TOOL_GET_COURTS, e)


async def get_court(db, court_id: str) -> Dict[str, Any]:
    """Mirrors GET /api/courts/{court_id} exactly (server.py's get_court)."""
    if not _valid_lookup_id(court_id):
        return {"status": "empty", "tool": TOOL_GET_COURT, "data": None}
    try:
        court = await db.courts.find_one({"court_id": court_id}, {"_id": 0})
        if not court:
            return {"status": "empty", "tool": TOOL_GET_COURT, "data": None}
        vendor_count = await db.vendors.count_documents({"court_ids": court_id, "kyc_status": "approved"})
        return _success(TOOL_GET_COURT, {**court, "vendor_count": vendor_count})
    except Exception as e:
        return _error(TOOL_GET_COURT, e)


async def get_services(db, category: Optional[str] = None) -> Dict[str, Any]:
    """Mirrors GET /api/services exactly (server.py's list_services), always
    with include_hidden=False — a chatbot has no business surfacing a service
    hidden from the marketplace."""
    try:
        query: Dict[str, Any] = {"active": {"$ne": False}, "visibility.marketplace": {"$ne": False}}
        if category:
            query["category"] = category
        services = await db.services.find(query, {"_id": 0}).to_list(500)
        return _success(TOOL_GET_SERVICES, services, filters_applied={"category": category})
    except Exception as e:
        return _error(TOOL_GET_SERVICES, e)


async def search_proxy_counsels(
    db,
    court_id: Optional[str] = None, state_id: Optional[str] = None, district: Optional[str] = None,
    specialization: Optional[str] = None, min_experience_years: Optional[float] = None,
    experience_bracket: Optional[str] = None, min_rating: Optional[float] = None,
    fee_min: Optional[float] = None, fee_max: Optional[float] = None, time_slot: Optional[str] = None,
    available_only: bool = False, hearing_date: Optional[str] = None, limit: int = 20,
) -> Dict[str, Any]:
    """Mirrors GET /api/public/proxy-counsels exactly: same
    counsel_matching.list_and_recommend call, same verified_counsel_query
    trust gate, same public_advocate_card trim (no bio/education/languages/
    availability field) — a chatbot answer can never show more than an
    anonymous browse-page visitor already sees.

    `filters_applied` is echoed back so ai_chat.py's grounding instructions
    can correctly tell the model when available_only=True actually was
    applied (in which case every returned candidate really does have
    availability_mode=True server-side, even though that field itself isn't
    in the trimmed public card) versus when it wasn't (in which case nothing
    about current availability may be stated at all)."""
    import counsel_matching
    try:
        ranked, total = await counsel_matching.list_and_recommend(
            db, court_id=court_id, state_id=state_id, district=district, specialization=specialization,
            min_experience_years=min_experience_years, experience_bracket=experience_bracket,
            min_rating=min_rating, fee_min=fee_min, fee_max=fee_max, time_slot=time_slot,
            available_only=available_only, hearing_date=hearing_date, limit=limit,
        )
        from server import _advocate_cards_for
        cards = await _advocate_cards_for(ranked)
        advocates = [counsel_matching.public_advocate_card(c) for c in cards]
    except Exception as e:
        return _error(TOOL_SEARCH_PROXY_COUNSELS, e)

    filters_applied = {
        "court_id": court_id, "state_id": state_id, "district": district, "specialization": specialization,
        "min_experience_years": min_experience_years, "experience_bracket": experience_bracket,
        "min_rating": min_rating, "fee_min": fee_min, "fee_max": fee_max, "time_slot": time_slot,
        "available_only": available_only, "hearing_date": hearing_date,
    }
    return _success(TOOL_SEARCH_PROXY_COUNSELS, advocates, total_candidates=total, filters_applied=filters_applied)


async def get_proxy_counsel_profile(db, advocate_id: str) -> Dict[str, Any]:
    """Mirrors GET /api/public/proxy-counsels/{advocate_id}/profile exactly —
    reuses server.py's _advocate_profile_or_404 unchanged, so an unverified
    or nonexistent advocate_id returns "empty", never a fabricated profile.

    Callers (ai_chat.py) must only ever pass an advocate_id already obtained
    from this conversation's own prior search_proxy_counsels result — this
    function itself does not and cannot verify that; it will happily look up
    any id, real or not. Never wire this to free-form user/LLM text."""
    if not _valid_lookup_id(advocate_id):
        return _empty(TOOL_GET_PROXY_COUNSEL_PROFILE)
    try:
        from server import _advocate_profile_or_404
        profile = await _advocate_profile_or_404(advocate_id)
        return _success(TOOL_GET_PROXY_COUNSEL_PROFILE, profile)
    except Exception as e:
        from fastapi import HTTPException
        if isinstance(e, HTTPException) and e.status_code == 404:
            return _empty(TOOL_GET_PROXY_COUNSEL_PROFILE)
        return _error(TOOL_GET_PROXY_COUNSEL_PROFILE, e)


# ---------------------------------------------------------------------------
# Phase 3C-B — authenticated, read-only, own-data-only tools
# ---------------------------------------------------------------------------

def _owns_order(order: dict, user: dict) -> bool:
    return user["user_id"] in (order.get("user_id"), order.get("vendor_id"))


def _owns_hearing(hearing: dict, user: dict) -> bool:
    return user["user_id"] in (hearing.get("requesting_user_id"), hearing.get("proxy_counsel_user_id"))


def _order_summary(order: dict) -> Dict[str, Any]:
    """Trims a raw `orders` document to what's needed to answer a status
    question — never the whole document. Drops user_phone, delivery_address,
    file_ids, firm_id, and vendor_sponsored (present on the real document but
    either PII, an internal reference, or simply not needed here)."""
    pricing = order.get("pricing") or {}
    return {
        "order_id": order.get("order_id"),
        "status": order.get("status"),
        "payment_status": order.get("payment_status"),
        "court_name": order.get("court_name"),
        "state_name": order.get("state_name"),
        "services": [
            {"name": item.get("name"), "qty": item.get("qty"), "line_total": item.get("line_total")}
            for item in (pricing.get("breakdown") or [])
        ],
        "total": pricing.get("total"),
        "delivery_option": order.get("delivery_option"),
        "urgent": order.get("urgent"),
        "vendor_name": order.get("vendor_name"),
        "created_at": order.get("created_at"),
        "status_history": [
            {"status": t.get("status"), "at": t.get("at")} for t in (order.get("timeline") or [])
        ],
    }


def _hearing_summary(hearing: dict) -> Dict[str, Any]:
    """Trims a raw `hearing_requests` document the same way _order_summary
    does. Deliberately excludes document_ids, order_sheet_doc_id,
    hearing_notes, rated_by, declined_by (which names OTHER users' ids),
    request_details (free-form, may carry contact details), and every
    internal scheduling/escrow timestamp — none of it is needed to answer
    "what's the status of my hearing request". proxy_counsel_user_id/
    target_advocate_id are reduced to a plain boolean rather than exposing
    another user's id string, which this conversation has no other reason to
    see."""
    return {
        "hearing_id": hearing.get("hearing_id"),
        "status": hearing.get("status"),
        "court_id": hearing.get("court_id"),
        "hearing_date": hearing.get("hearing_date"),
        "fee": hearing.get("fee"),
        "service_type": hearing.get("service_type"),
        "case_details": hearing.get("case_details") if hearing.get("details_submitted") else None,
        "proxy_counsel_assigned": bool(hearing.get("proxy_counsel_user_id")),
        "created_at": hearing.get("created_at"),
        "updated_at": hearing.get("updated_at"),
        "status_history": [
            {"status": t.get("status"), "at": t.get("at")} for t in (hearing.get("timeline") or [])
        ],
    }


async def get_my_orders(db, user: dict, status: Optional[str] = None) -> Dict[str, Any]:
    """Mirrors GET /api/orders exactly — same role-based scoping (server.py's
    list_orders has no separate service function to import, same situation
    as get_states/get_courts/get_services above, so the query is mirrored,
    not duplicated business logic living in two independently-maintained
    places by accident: this IS the same rule, just called from here too).
    `status`, when given, is passed straight through as an equality filter —
    never validated against a hardcoded guess at valid values, since the
    real route doesn't validate it either; an unrecognized status simply
    matches nothing, exactly like calling the real endpoint would."""
    guard = _require_user(TOOL_GET_MY_ORDERS, user)
    if guard:
        return guard
    try:
        # Same role scoping as GET /orders, except that an admin gets their
        # own orders here, never every user's (see "own data only" above).
        query: Dict[str, Any] = {}
        if user.get("role") == "vendor":
            query["vendor_id"] = user["user_id"]
        else:
            query["user_id"] = user["user_id"]
        if status:
            query["status"] = status
        orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
        summaries = [_order_summary(o) for o in orders]
        return _success(TOOL_GET_MY_ORDERS, summaries, filters_applied={"status": status})
    except Exception as e:
        return _error(TOOL_GET_MY_ORDERS, e, message=AUTH_ERROR_MESSAGE)


async def get_order(db, user: dict, order_id: str) -> Dict[str, Any]:
    """Mirrors GET /api/orders/{order_id} exactly, including its ownership
    check (order.user_id/vendor_id == caller, or admin). A 403-shaped case
    (order exists but isn't the caller's) and a genuine 404 are deliberately
    returned as the SAME "empty" envelope — this function must never let a
    caller distinguish "not yours" from "doesn't exist" (see this phase's
    cross-user security requirement)."""
    guard = _require_user(TOOL_GET_ORDER, user)
    if guard:
        return guard
    if not _valid_lookup_id(order_id):
        return _empty(TOOL_GET_ORDER)
    try:
        order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
    except Exception as e:
        return _error(TOOL_GET_ORDER, e, message=AUTH_ERROR_MESSAGE)
    if not order:
        return _empty(TOOL_GET_ORDER)
    if not _owns_order(order, user):  # no admin override here (own data only)
        return _empty(TOOL_GET_ORDER)
    return _success(TOOL_GET_ORDER, _order_summary(order))


async def get_my_hearing_requests(db, user: dict) -> Dict[str, Any]:
    """Calls hearings.list_hearing_requests unchanged — that function already
    derives its query entirely from `user["user_id"]`/`user["capabilities"]`,
    with no parameter through which a different user's data could be
    requested."""
    guard = _require_user(TOOL_GET_MY_HEARING_REQUESTS, user)
    if guard:
        return guard
    try:
        import hearings as hearings_svc
        hearings = await hearings_svc.list_hearing_requests(db, user)
        # list_hearing_requests also returns the open broadcast pool and
        # targeted negotiations for a proxy counsel — other clients' cases.
        summaries = [_hearing_summary(h) for h in hearings if _owns_hearing(h, user)]
        return _success(TOOL_GET_MY_HEARING_REQUESTS, summaries)
    except Exception as e:
        return _error(TOOL_GET_MY_HEARING_REQUESTS, e, message=AUTH_ERROR_MESSAGE)


async def get_hearing_request(db, user: dict, hearing_id: str) -> Dict[str, Any]:
    """Calls hearings.get_hearing_request unchanged, which raises
    HTTPException(404) for an unknown id and calls hearings._check_visible
    (raises 403) for one that exists but isn't visible to this user. Both are
    collapsed into the same "empty" envelope here — same anti-enumeration
    rule as get_order above; the real HTTPException's status code is never
    inspected or forwarded past this function."""
    guard = _require_user(TOOL_GET_HEARING_REQUEST, user)
    if guard:
        return guard
    if not _valid_lookup_id(hearing_id):
        return _empty(TOOL_GET_HEARING_REQUEST)
    try:
        import hearings as hearings_svc
        from fastapi import HTTPException
        try:
            hearing = await hearings_svc.get_hearing_request(db, hearing_id, user)
        except HTTPException as e:
            if e.status_code in (403, 404):
                return _empty(TOOL_GET_HEARING_REQUEST)
            raise
        if not _owns_hearing(hearing, user):  # visible via admin/broadcast is not enough here
            return _empty(TOOL_GET_HEARING_REQUEST)
        return _success(TOOL_GET_HEARING_REQUEST, _hearing_summary(hearing))
    except Exception as e:
        return _error(TOOL_GET_HEARING_REQUEST, e, message=AUTH_ERROR_MESSAGE)
