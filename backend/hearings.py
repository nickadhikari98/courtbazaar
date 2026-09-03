"""Hearing Requests — the "Hire Proxy Counsel" marketplace. A first-class
domain entity, deliberately NOT modeled as an order: its own status
machine/timeline, own documents, own communication thread, own ratings —
none of it shares a collection or status enum with db.orders.

This module owns OPERATIONAL workflow only — broadcast/accept/documents/
hearing/verification — never payment math or state. A hearing's fee is paid
through escrow.py (create_and_hold/release/refund, its own independent
created->captured->held->released|refunded state machine); this module only
reacts to "payment confirmed" as a business event via mark_payment_confirmed,
and calls into escrow.py for release/refund. See escrow.py's module
docstring for why that split exists.

Lifecycle (workflow.StateMachine) — reordered by the Counsel Matching Agent
roadmap's M6 (payment now precedes broadcast, not the other way around):
    requested -> payment_pending -> broadcast -> accepted -> documents_shared
    -> preparation -> hearing_scheduled -> hearing_completed
    -> verification_pending -> verified -> completed -> rated (rated is a
    terminal relabel, not a flag alongside completed — same as before this
    refactor: whichever side rates first flips status to "rated", second
    rater keeps it there)
Off-ramps: rejected (targeted-request decline), cancelled, disputed, expired.
Auto-chained transitions fire on a real event, never a timer: documents_shared
-> preparation -> hearing_scheduled on the first case-document upload,
hearing_completed -> verification_pending on the order-sheet upload.
`accepted` has no auto-chain of its own yet — advancing straight to
documents_shared (assigning the escrow payee, clearing the match-tier
deadline) is M12's job (Acceptance-Side Integration), not M6's, so a hearing
sits at `accepted` until M12 lands; see HEARING_TRANSITIONS below.

Matching is broadcast-based by default (unlike vendor order auto-matching in
server.py): any available proxy counsel can see and accept an open request;
whoever accepts first wins (race-safe — see accept_hearing_request()).
Declining is personal (`declined_by`), not global — one proxy counsel
declining doesn't cancel the request for everyone else. mark_payment_confirmed
kicks off the Counsel Matching Agent (counsel_matching.run_matching, M11)
right after a hearing reaches "broadcast" — tier-1 eligible candidates are
notified automatically; the broadcast pool itself is still "anyone eligible
can accept", matching still doesn't gate who's allowed to accept (that's
M12/M13's job).

`target_advocate_id` (nullable) is the integration point for a separate,
not-yet-built advocate search/select workstream: when set, the request is
addressed to exactly that advocate (only they can see/accept/reject it, and
a reject is a global, terminal `rejected` — not a personal decline). When
absent, the request behaves exactly as the broadcast case above always has.
"""
import inspect
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from fastapi import HTTPException
from pymongo import ReturnDocument

from workflow import StateMachine, IllegalTransition

logger = logging.getLogger(__name__)

HEARING_STATUSES = (
    "requested", "broadcast", "accepted", "payment_pending", "documents_shared", "preparation",
    "hearing_scheduled", "hearing_completed", "verification_pending", "verified",
    "completed", "rated", "rejected", "cancelled", "disputed", "expired",
)

HEARING_TRANSITIONS = {
    # M6 reorder: payment now happens before broadcast — see module docstring.
    ("requested", "initiate_payment"): "payment_pending",
    ("requested", "cancel"): "cancelled",         # new — "requested" is now a real, potentially long-lived pre-payment state
    # Negotiation Module: negotiation happens at "requested" (pre-payment), so
    # the targeted advocate must be able to reject from there too, not just
    # from "broadcast" — same pre-payment/post-payment pairing cancel already
    # has above/below.
    ("requested", "reject"): "rejected",
    ("payment_pending", "confirm_payment"): "broadcast",
    ("payment_pending", "cancel"): "cancelled",
    ("payment_pending", "reject"): "rejected",
    # Self-loop, same precedent as ("rated","rate"):"rated" below — retry
    # path for an abandoned/failed checkout: create-order's initiate_payment
    # call can land here (status already moved) while the actual Razorpay
    # verify never completes, and until this existed there was no way back
    # to "requested" or a fresh order — the hearing was permanently stuck
    # with no Pay button anywhere (see Escrow Module production audit).
    ("payment_pending", "initiate_payment"): "payment_pending",
    ("broadcast", "accept"): "accepted",
    ("broadcast", "reject"): "rejected",          # targeted request only — see accept_hearing_request/reject_hearing_request
    ("broadcast", "cancel"): "cancelled",
    ("broadcast", "expire"): "expired",           # reserved — no scheduled job drives this yet
    ("accepted", "cancel"): "cancelled",
    # M12: auto-chain straight through to documents_shared — same "accept"
    # action reused across two consecutive states, same precedent as
    # ("completed","rate")/("rated","rate") below reusing one action string.
    ("accepted", "accept"): "documents_shared",
    ("documents_shared", "share_documents"): "preparation",
    ("documents_shared", "cancel"): "cancelled",  # money already held — see cancel_hearing_request's refund call
    ("preparation", "schedule"): "hearing_scheduled",
    ("preparation", "cancel"): "cancelled",
    ("hearing_scheduled", "cancel"): "cancelled",
    ("hearing_scheduled", "conduct"): "hearing_completed",
    ("hearing_completed", "cancel"): "cancelled",
    ("hearing_completed", "upload_order_sheet"): "verification_pending",
    ("verification_pending", "verify"): "verified",
    ("verification_pending", "reject_verification"): "disputed",
    ("disputed", "resubmit"): "verification_pending",   # admin resolves — back for another look
    ("disputed", "refund_and_cancel"): "cancelled",     # admin resolves — refund, close out
    ("verified", "release_payout"): "completed",        # Verify and Release are always two separate calls — see server.py
    ("completed", "rate"): "rated",
    ("rated", "rate"): "rated",                         # both sides can rate; second rating doesn't re-transition
}

# Statuses from which cancelling means money is already held and must be
# refunded (see cancel_hearing_request) rather than simply walked back.
# M6 reorder: "broadcast" and "accepted" now happen after payment (they used
# to precede it), so cancelling from either of them now means escrow is
# already held too. Public (no leading underscore) — server.py's cancel
# endpoint reuses this exact set to decide notification copy, rather than
# guessing separately whether a refund happened.
CANCEL_REQUIRES_REFUND = {"broadcast", "accepted", "documents_shared", "preparation", "hearing_scheduled", "hearing_completed"}

# service_id is nullable on escrow_transactions in general, but hearings
# aren't a db.services catalog row — this constant keeps every hearing
# escrow record groupable/reportable by service anyway (see escrow.py).
ESCROW_SERVICE_ID = "hire_proxy_counsel"


def new_hearing_id() -> str:
    return f"hearing_{uuid.uuid4().hex[:12]}"


async def ensure_indexes(db) -> None:
    await db.hearing_requests.create_index([("status", 1), ("created_at", -1)], name="status_created")
    await db.hearing_requests.create_index([("requesting_user_id", 1)], name="requester")
    await db.hearing_requests.create_index([("proxy_counsel_user_id", 1)], name="assigned_proxy_counsel")
    # Ahead of its data on purpose: no hearing is written with match_tier_deadline_at
    # yet (Counsel Matching Agent roadmap M1) — this is the index the M13 scheduler
    # poll will run against once M9/M10 start stamping that field.
    await db.hearing_requests.create_index(
        [("status", 1), ("proxy_counsel_user_id", 1), ("match_tier_deadline_at", 1)],
        name="match_tier_deadline",
    )
    await db.hearing_messages.create_index([("hearing_id", 1), ("created_at", 1)], name="hearing_thread")
    await db.professional_ratings.create_index([("rated_user_id", 1)], name="rated_user")


async def create_hearing_request(db, requesting_user_id: str, court_id: str, hearing_date: str,
                                  case_details: str, fee: Optional[float], matter_id: Optional[str],
                                  target_advocate_id: Optional[str] = None,
                                  service_type: str = "proxy_counsel",
                                  request_details: Optional[dict] = None,
                                  is_fallback: bool = False,
                                  fallback_group_id: Optional[str] = None) -> dict:
    if not court_id or not hearing_date:
        raise HTTPException(400, "Court and hearing date are required")
    now = datetime.now(timezone.utc)
    doc = {
        "hearing_id": new_hearing_id(),
        "requesting_user_id": requesting_user_id,
        "proxy_counsel_user_id": None,
        "target_advocate_id": target_advocate_id,  # set -> addressed to one advocate; None -> broadcast to all
        # Auto top-5 fallback (founder direction, 2026-09): fallback_group_id
        # ties this hearing to the originally-rejected one it was fanned out
        # from (that hearing's own hearing_id — see
        # _create_fallback_requests); is_fallback stops it from spawning
        # *another* round of fallbacks if it too gets rejected, so one
        # manual "Select Counsel" ever produces at most one extra round.
        "is_fallback": is_fallback,
        "fallback_group_id": fallback_group_id,
        "court_id": court_id,
        "hearing_date": hearing_date,
        # BlaBlaCar-style flow (founder direction): the intake form now only
        # collects location + hearing date to get matched and paid — the
        # actual case brief (title, type, instructions, work required, ...)
        # is collected afterward via submit_case_details, once payment is
        # confirmed, so nothing case-specific is visible to a counsel before
        # money is held. `case_details` is left optional here (was previously
        # required) so a hearing can exist before that brief does; every
        # other reader (chat header, Negotiation summary, ...) gets this
        # placeholder in the meantime. `details_submitted` is what the
        # frontend actually branches on to tell "still a placeholder" apart
        # from "customer deliberately wrote something short".
        "case_details": case_details or "Case details will be shared once payment is confirmed.",
        "details_submitted": False,
        "matter_id": matter_id,
        "fee": fee,
        # `service_type` is a discriminator for the generic Legal Service
        # Request architecture (frontend LegalServiceRequestForm) — rows
        # created before this field existed are read as "proxy_counsel" by
        # any consumer. `request_details` is a free-form, structured bag
        # ({common: {...}, service_specific: {...}}) built entirely on the
        # frontend; the backend never branches on its contents, so adding
        # fields to it (or onboarding a new service_type) never requires a
        # schema change here.
        "service_type": service_type,
        "request_details": request_details,
        "status": "requested",
        # Flipped once by negotiation.accept_offer (via set_negotiated_fee)
        # when both sides agree a fee — from then on this hearing is
        # commercially committed: cancel_hearing_request/reject_hearing_request
        # refuse outright, Payment is the only forward action. See those two
        # functions and negotiation.py's accept_offer for the full rule.
        "commercially_locked": False,
        "declined_by": [],
        "document_ids": [],
        "order_sheet_doc_id": None,
        "hearing_notes": [],
        "rated_by": [],
        # Escrow Module: set once by mark_payment_confirmed, read by
        # check_pending_order_sheets' 3-day reminder scan below — never
        # backfilled onto pre-existing rows, so a hearing created before this
        # field existed simply never matches that scan (safe default, no
        # retroactive reminder storm).
        "payment_confirmed_at": None,
        "order_sheet_reminder_sent_at": None,
        # Escrow Module (3-day auto-release rule): set whenever the hearing
        # enters verification_pending, cleared the moment it leaves
        # (verified/disputed) — read by auto_release_stale_verifications
        # below to auto-verify+release if neither side acts within 3 days.
        "verification_pending_at": None,
        "timeline": [{"status": "requested", "at": now.isoformat(), "note": "Request created"}],
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    # M6 reorder: no more auto-chain to "broadcast" here — the hearing now
    # stays at "requested" until the requester pays; see mark_payment_confirmed
    # for where broadcast (and the targeted-vs-broadcast timeline note that
    # used to live here) now happens.
    await db.hearing_requests.insert_one(doc)
    doc.pop("_id", None)
    return doc


def _make_timeline_hook(db):
    async def hook(entity: dict, from_status: str, to_status: str, actor: Optional[dict]) -> None:
        await db.hearing_requests.update_one(
            {"hearing_id": entity["hearing_id"]},
            {"$push": {"timeline": {
                "status": to_status, "at": datetime.now(timezone.utc).isoformat(),
                "note": f"{from_status} -> {to_status}", "by": actor["user_id"] if actor else "system",
            }}},
        )
    return hook


async def _push_activity(db, hearing_id: str, note: str, actor_user_id: Optional[str] = None) -> None:
    """Non-transition activity events (document uploaded, payment initiated,
    escrow held/released amounts) land in the same `timeline` array as status
    transitions — the array is the canonical activity history for a hearing,
    not just its status changes."""
    await db.hearing_requests.update_one(
        {"hearing_id": hearing_id},
        {"$push": {"timeline": {
            "at": datetime.now(timezone.utc).isoformat(), "note": note, "by": actor_user_id or "system",
        }}},
    )


async def _transition(db, sm: StateMachine, entity: dict, from_status: str, action: str,
                       actor: Optional[dict], note: Optional[str] = None,
                       extra_guard: Optional[Dict[str, Any]] = None) -> str:
    """Validates the transition, then persists it as a compare-and-swap on
    `status == from_status` (same race-safe find_one_and_update idiom as
    accept_hearing_request's own broadcast-accept race guard) rather than a
    blind update_one — two requests racing against the same hearing can't
    both apply their transition; the loser's write matches nothing and gets
    a 409 telling the client to refresh. `extra_guard` folds an additional
    field condition into that same atomic write (see
    cancel_hearing_request/reject_hearing_request's commercially_locked
    check) instead of checking it separately, which would reopen the race.

    The on_transition hook (timeline push) and `note` activity only fire
    AFTER the CAS write succeeds — firing them first (as a naive
    `sm.apply()` call would, since the hook runs synchronously inside it)
    would record a "from -> to" timeline entry even on the branch where the
    write is then rejected."""
    to_status = sm.next_state(from_status, action)  # raises IllegalTransition if invalid; no DB write yet
    query: Dict[str, Any] = {"hearing_id": entity["hearing_id"], "status": from_status}
    if extra_guard:
        query.update(extra_guard)
    now = datetime.now(timezone.utc).isoformat()
    updated = await db.hearing_requests.find_one_and_update(
        query, {"$set": {"status": to_status, "updated_at": now}}, projection={"_id": 0},
    )
    if not updated:
        raise HTTPException(409, "This request's status changed — please refresh and try again.")
    if sm.on_transition:
        result = sm.on_transition(entity, from_status, to_status, actor)
        if inspect.isawaitable(result):
            await result
    if note:
        await _push_activity(db, entity["hearing_id"], note, actor["user_id"] if actor else None)
    return to_status


async def list_hearing_requests(db, user: dict) -> List[dict]:
    capabilities = user.get("capabilities") or []
    clauses = [{"requesting_user_id": user["user_id"]}]
    if "can_practice_proxy_counsel" in capabilities:
        clauses.append({
            "status": "broadcast", "declined_by": {"$ne": user["user_id"]},
            "$or": [{"target_advocate_id": None}, {"target_advocate_id": user["user_id"]}],
        })
        clauses.append({"proxy_counsel_user_id": user["user_id"]})
        # Negotiation Module: a hearing targeted at this advocate is invisible
        # everywhere else above until it reaches "broadcast" (post-payment) —
        # but negotiation happens BEFORE payment, so without this clause the
        # advocate would have no way to even discover a pending negotiation.
        clauses.append({"target_advocate_id": user["user_id"], "status": {"$in": ["requested", "payment_pending"]}})
    hearings = await db.hearing_requests.find({"$or": clauses}, {"_id": 0}).sort("created_at", -1).to_list(200)
    await _attach_negotiation_action_flags(db, hearings, user["user_id"])
    return hearings


def _viewer_must_act_on_negotiation(neg: Optional[dict], hearing: dict, user_id: str) -> bool:
    """Is the ball in THIS viewer's court on a live fee negotiation? Powers the
    dashboard "Hearings Needing Action" tile (see hearingLifecycle.js's
    hearingNeedsMyAction). Mirrors NegotiationOfferPanel.jsx's own stage logic:
      - agreed negotiation -> nothing to do here (payment is a separate action
        already counted by hearingNeedsMyAction's paymentDue branch);
      - a standing offer proposed by the OTHER side -> my turn to accept/counter;
      - no offer yet -> the requester is expected to open (the counsel's screen
        literally reads "Waiting for the customer to send an offer"), so it's
        the requester's action, not the counsel's. A hearing with no negotiation
        row created yet is treated the same as "no offer yet"."""
    if neg and neg.get("status") != "open":
        return False
    current_offer_id = neg.get("current_offer_id") if neg else None
    if not current_offer_id:
        return hearing.get("requesting_user_id") == user_id
    current = next((o for o in (neg.get("offers") or []) if o.get("offer_id") == current_offer_id), None)
    if not current:
        return False
    return current.get("proposed_by_user_id") != user_id


async def _attach_negotiation_action_flags(db, hearings: List[dict], user_id: str) -> None:
    """Sets `negotiation_action_required` on each pre-payment negotiation
    hearing — whether `user_id` must act on it right now. Done here (one extra
    query for all of them, keyed by hearing_id) rather than per-hearing on the
    client, because the answer lives in the separate `negotiations` collection
    the hearing doc doesn't carry."""
    pending = [h for h in hearings
               if h.get("target_advocate_id")
               and not h.get("commercially_locked")
               and h.get("status") in ("requested", "payment_pending")]
    if not pending:
        return
    neg_by_hearing = {
        n["hearing_id"]: n
        for n in await db.negotiations.find(
            {"hearing_id": {"$in": [h["hearing_id"] for h in pending]}},
            {"_id": 0, "hearing_id": 1, "status": 1, "current_offer_id": 1, "offers": 1},
        ).to_list(len(pending))
    }
    for h in pending:
        h["negotiation_action_required"] = _viewer_must_act_on_negotiation(
            neg_by_hearing.get(h["hearing_id"]), h, user_id)


async def get_hearing_request(db, hearing_id: str, user: dict) -> dict:
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    _check_visible(hearing, user)
    return hearing


def _check_visible(hearing: dict, user: dict) -> None:
    is_requester = hearing["requesting_user_id"] == user["user_id"]
    is_assigned = hearing.get("proxy_counsel_user_id") == user["user_id"]
    is_targeted_at_me = hearing.get("target_advocate_id") in (None, user["user_id"])
    is_open_to_me = hearing["status"] == "broadcast" and "can_practice_proxy_counsel" in (user.get("capabilities") or []) \
        and is_targeted_at_me
    # Negotiation Module: unlike the broadcast pool above, a hearing
    # specifically targeted at this advocate (not the None/broadcast-to-all
    # case) must be visible to them BEFORE payment too, while status is still
    # "requested"/"payment_pending" — that's the whole pre-payment negotiation
    # window. Deliberately narrower than is_open_to_me: only the exact
    # targeted advocate, never every can_practice_proxy_counsel account.
    is_targeted_pending = hearing.get("target_advocate_id") == user["user_id"] \
        and "can_practice_proxy_counsel" in (user.get("capabilities") or []) \
        and hearing["status"] in ("requested", "payment_pending")
    if not (is_requester or is_assigned or is_open_to_me or is_targeted_pending or user.get("role") == "admin"):
        raise HTTPException(403, "Forbidden")


async def accept_hearing_request(db, hearing_id: str, user: dict) -> dict:
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    # Conditional update on status=="broadcast" (+ target match) is what makes
    # this race-safe: two proxy counsel accepting at the same moment can't
    # both win — whichever commits first flips status away from "broadcast",
    # the other's update matches nothing.
    updated = await db.hearing_requests.find_one_and_update(
        {
            "hearing_id": hearing_id, "status": "broadcast",
            "$or": [{"target_advocate_id": None}, {"target_advocate_id": user["user_id"]}],
        },
        {"$set": {
            "status": "accepted", "proxy_counsel_user_id": user["user_id"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, "$push": {"timeline": {
            "status": "accepted", "at": datetime.now(timezone.utc).isoformat(), "by": user["user_id"],
        }}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        if hearing.get("target_advocate_id") not in (None, user["user_id"]):
            raise HTTPException(403, "This request wasn't sent to you")
        # M6 reorder: "requested"/"payment_pending" are now real, potentially
        # long-lived pre-broadcast states (not just a single-call blip), so an
        # early accept attempt is a distinct, expected case from a genuine
        # accept-race or an already-taken request — give it its own message.
        if hearing["status"] in ("requested", "payment_pending"):
            raise HTTPException(400, "This request isn't open for acceptance yet — payment must be confirmed first")
        raise HTTPException(409, "This request has already been taken by another proxy counsel")

    # M12: only the winner of the race above ever reaches this point, so
    # these side effects run exactly once per hearing. Unlike M11's matching
    # call, none of this is best-effort, so exceptions here are allowed to
    # propagate (same as cancel_hearing_request/release_hearing_payout
    # letting escrow exceptions propagate), not caught and swallowed. The
    # state transition runs LAST, deliberately: if assign_payee (or clearing
    # the deadline) fails, the hearing must stay at "accepted" rather than
    # falsely advancing to documents_shared with no payee attached.
    import escrow as escrow_svc
    await escrow_svc.assign_payee(db, context_type="hearing", context_id=hearing_id, payee_user_id=user["user_id"])
    await db.hearing_requests.update_one(
        {"hearing_id": hearing_id}, {"$set": {"match_tier_deadline_at": None}},
    )
    sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
    await _transition(db, sm, updated, "accepted", "accept", user,
                       note="Payment already held — proceeding directly to document sharing")
    updated["status"] = "documents_shared"
    updated["match_tier_deadline_at"] = None
    # Best-effort, same isolation as every other post-commit side effect in
    # this module — the accept itself already succeeded and must return
    # regardless of whether sibling cleanup does.
    try:
        await _auto_cancel_fallback_siblings(db, updated)
    except Exception as e:
        logger.error(f"fallback sibling auto-cancel failed for {hearing_id}: {e}")
    return updated


async def _auto_cancel_fallback_siblings(db, accepted_hearing: dict) -> None:
    """Counterpart to _create_fallback_requests: once one of the fanned-out
    siblings is actually accepted (paid and confirmed), the other still-open
    siblings from that same fallback round are no longer needed — auto-
    cancel them, refunding escrow for any that had already reached payment,
    so the customer never ends up committed to two counsels for one hearing."""
    group_id = accepted_hearing.get("fallback_group_id")
    if not group_id:
        return
    import escrow as escrow_svc
    from notifications import notify, record_notification_event, get_hearing_email_thread
    open_statuses = ["requested", "payment_pending", "broadcast"]
    siblings = await db.hearing_requests.find({
        "fallback_group_id": group_id,
        "hearing_id": {"$ne": accepted_hearing["hearing_id"]},
        "status": {"$in": open_statuses},
    }, {"_id": 0}).to_list(20)
    sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
    for sib in siblings:
        try:
            await _transition(db, sm, sib, sib["status"], "cancel", None,
                               note="Auto-cancelled — the client accepted a different counsel from the same automatic fallback")
            if sib["status"] in CANCEL_REQUIRES_REFUND:
                await escrow_svc.refund(db, context_type="hearing", context_id=sib["hearing_id"],
                                         reason="Fallback sibling auto-cancelled after another counsel was accepted")
            recipient = await db.users.find_one({"user_id": sib.get("target_advocate_id")})
            if recipient:
                title, body = "Request closed", "This hearing request was automatically closed — the client accepted a different counsel."
                ctx = {"title": title, "body": body}
                if recipient.get("email"):
                    ctx["hearing_thread"] = await get_hearing_email_thread(
                        db, sib["hearing_id"], recipient["email"],
                        f"CourtBazaar — Your Proxy Counsel Hearing (Ref: {sib['hearing_id']})",
                    )
                notify(recipient, "hearing_event", ctx)
                await record_notification_event(db, sib["target_advocate_id"], "hearing_event", title, body,
                                                 "hearing", sib["hearing_id"])
        except (IllegalTransition, HTTPException):
            continue
        except Exception as e:
            logger.error(f"fallback sibling auto-cancel failed for {sib.get('hearing_id')}: {e}")
            continue


async def reject_hearing_request(db, hearing_id: str, user: dict) -> dict:
    """Targeted requests only — a global, terminal reject (customer
    notified), distinct from decline_hearing_request's personal/broadcast
    `declined_by` below. See module docstring."""
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    if hearing.get("target_advocate_id") != user["user_id"]:
        raise HTTPException(403, "Only the advocate this request was sent to can reject it")
    if hearing.get("commercially_locked"):
        raise HTTPException(400, "A fee has been agreed through negotiation — this request is "
                                  "commercially locked and can no longer be rejected. Proceed to payment.")
    sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
    try:
        await _transition(db, sm, hearing, hearing["status"], "reject", user,
                           extra_guard={"commercially_locked": {"$ne": True}})
    except IllegalTransition:
        raise HTTPException(400, "This request can no longer be rejected")
    # Best-effort, same failure-isolation pattern as decline_hearing_request's
    # maybe_early_advance call below — the reject itself already committed,
    # so a fallback-fanout failure must never surface as this call failing.
    try:
        await _create_fallback_requests(db, hearing)
    except Exception as e:
        logger.error(f"fallback request creation failed for {hearing_id}: {e}")
    return {"ok": True, "status": "rejected"}


async def _create_fallback_requests(db, original_hearing: dict) -> None:
    """Auto top-5 fallback (founder direction, 2026-09): the moment a
    customer's manually-Selected Counsel rejects, fan out a fresh targeted
    request — same court/hearing date/filters, same negotiate-then-pay
    pipeline as the original "Select Counsel" action (see
    CounselHiringPage.jsx) — to the next TOP_CANDIDATE_BATCH_SIZE AI-ranked
    candidates, all at once. Whichever of them the customer ends up
    negotiating, paying and getting accepted by first "wins";
    _auto_cancel_fallback_siblings (see accept_hearing_request) closes out
    the rest the moment that happens, refunding any of them that had
    already reached payment.

    Only ever runs off a manually-selected request — original_hearing.is_fallback
    guards against a fallback sibling that itself gets rejected spawning yet
    another round, so this can never cascade unboundedly."""
    if original_hearing.get("is_fallback"):
        return
    import counsel_matching
    from notifications import notify, record_notification_event, get_hearing_email_thread
    exclude_ids = {original_hearing.get("target_advocate_id"), original_hearing.get("requesting_user_id")}
    candidates = await counsel_matching.top_fallback_candidates(db, original_hearing, exclude_ids)
    requester = await db.users.find_one({"user_id": original_hearing["requesting_user_id"]})

    async def _notify(recipient: dict, hearing_id: str, title: str, body: str) -> None:
        ctx = {"title": title, "body": body}
        if recipient.get("email"):
            ctx["hearing_thread"] = await get_hearing_email_thread(
                db, hearing_id, recipient["email"], f"CourtBazaar — Your Proxy Counsel Hearing (Ref: {hearing_id})",
            )
        notify(recipient, "hearing_event", ctx)
        await record_notification_event(db, recipient["user_id"], "hearing_event", title, body, "hearing", hearing_id)

    if not candidates:
        if requester:
            await _notify(requester, original_hearing["hearing_id"], "No further matches found",
                           "Your selected counsel declined this request, and we couldn't find any other "
                           "available counsels matching your filters right now. Please try browsing again "
                           "with different filters.")
        return
    group_id = original_hearing["hearing_id"]
    created = []
    for candidate in candidates:
        try:
            fallback = await create_hearing_request(
                db, original_hearing["requesting_user_id"], original_hearing["court_id"], original_hearing["hearing_date"],
                original_hearing.get("case_details") if original_hearing.get("details_submitted") else None,
                original_hearing.get("fee"), original_hearing.get("matter_id"), candidate["user_id"],
                original_hearing.get("service_type", "proxy_counsel"), original_hearing.get("request_details"),
                is_fallback=True, fallback_group_id=group_id,
            )
            created.append(fallback)
            recipient = await db.users.find_one({"user_id": candidate["user_id"]})
            if recipient:
                await _notify(recipient, fallback["hearing_id"], "New hearing request",
                               f"You've been requested for a hearing at {original_hearing['court_id']}. Open Negotiation to respond.")
        except Exception as e:
            logger.error(f"fallback request creation failed for candidate {candidate.get('user_id')}: {e}")
            continue
    if requester and created:
        await _notify(requester, original_hearing["hearing_id"], "Finding you alternative counsels",
                       f"Your selected counsel declined the request. We've automatically sent it to "
                       f"{len(created)} other top-matched proxy counsels using your original filters.")


async def decline_hearing_request(db, hearing_id: str, user: dict) -> dict:
    """Personal, not global — hides this request from this proxy counsel's
    own open-requests view without affecting anyone else's (broadcast
    requests only; a targeted request uses reject_hearing_request instead).

    M14: after recording the decline, checks whether every counsel notified
    in the current tier has now declined — if so, advances/escalates
    immediately instead of waiting for match_tier_deadline_at. Best-effort,
    same pattern as mark_payment_confirmed's M11 run_matching call: a
    failure here must never undo the decline that was just durably
    recorded, so it's caught and logged, never re-raised."""
    result = await db.hearing_requests.update_one(
        {"hearing_id": hearing_id}, {"$addToSet": {"declined_by": user["user_id"]}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Hearing request not found")

    import counsel_matching
    from audit_log import log_audit
    try:
        await counsel_matching.maybe_early_advance(db, hearing_id)
    except Exception as e:
        await log_audit(db, "matching.early_advance_failed", None, {"hearing_id": hearing_id, "error": str(e)})

    return {"ok": True}


async def cancel_hearing_request(db, hearing_id: str, user: dict) -> dict:
    import escrow as escrow_svc
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    if hearing["requesting_user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(403, "Forbidden")
    if hearing.get("commercially_locked"):
        raise HTTPException(400, "A fee has been agreed through negotiation — this request is "
                                  "commercially locked and can no longer be cancelled. Proceed to payment.")
    sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
    try:
        await _transition(db, sm, hearing, hearing["status"], "cancel", user,
                           extra_guard={"commercially_locked": {"$ne": True}})
    except IllegalTransition:
        raise HTTPException(400, "This request can no longer be cancelled")
    if hearing["status"] in CANCEL_REQUIRES_REFUND:
        await escrow_svc.refund(db, context_type="hearing", context_id=hearing_id, reason="Hearing cancelled after payment was held")
        await _push_activity(db, hearing_id, "Escrow refunded — hearing cancelled after payment was held", user["user_id"])
    return {"ok": True}


async def end_negotiation(db, hearing_id: str, user: dict) -> dict:
    """Customer-only close-out for a targeted negotiation that isn't working
    out. Mechanically identical to cancel_hearing_request (same 'cancel'
    transition/commercially_locked guard — never reaches an escrow-refund
    branch because a hearing can only leave "requested" once
    commercially_locked, see set_negotiated_fee, and that's exactly what's
    guarded against here) — the only difference is the audit-note/
    notification wording (see server.py's endpoint) and who may call it.

    Deliberately does NOT retarget this hearing_id at a new advocate: this
    module treats target_advocate_id as write-once (see HireProxyCounsel.jsx's
    docstring — counsel selection is what creates the hearing row), and the
    `negotiations` collection has a unique index on hearing_id, so reusing
    this row for a second counsel would either destroy the first negotiation's
    history or need a multi-attempt schema. Picking a different counsel means
    the frontend creates a new hearing_id via the normal create_hearing_request
    path — this function's only job is to retire the old one distinctly from
    an outright cancellation."""
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    if hearing["requesting_user_id"] != user["user_id"]:
        raise HTTPException(403, "Only the requester can end this negotiation")
    if not hearing.get("target_advocate_id"):
        raise HTTPException(400, "This request was never sent to a specific advocate")
    if hearing.get("commercially_locked"):
        raise HTTPException(400, "A fee has been agreed through negotiation — this request is "
                                  "commercially locked. Proceed to payment instead.")
    sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
    try:
        await _transition(db, sm, hearing, hearing["status"], "cancel", user,
                           note="Negotiation ended — requester is selecting a different counsel",
                           extra_guard={"commercially_locked": {"$ne": True}})
    except IllegalTransition:
        raise HTTPException(400, "This negotiation can no longer be ended")
    return {"ok": True, "status": "cancelled"}


async def add_note(db, hearing_id: str, user: dict, note: str) -> dict:
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    _check_participant(hearing, user)
    entry = {"text": note, "user_id": user["user_id"], "created_at": datetime.now(timezone.utc).isoformat()}
    await db.hearing_requests.update_one({"hearing_id": hearing_id}, {"$push": {"hearing_notes": entry}})
    return entry


def _check_participant(hearing: dict, user: dict) -> None:
    # target_advocate_id counts as a participant even before formal accept
    # (proxy_counsel_user_id is still None then) — chat/notes/documents must
    # work during negotiation, not just after acceptance.
    is_participant = user["user_id"] in (
        hearing["requesting_user_id"], hearing.get("proxy_counsel_user_id"), hearing.get("target_advocate_id"),
    )
    if not is_participant and user.get("role") != "admin":
        raise HTTPException(403, "Forbidden")


async def add_document(db, put_object_fn, validate_upload_fn, hearing_id: str, user: dict,
                        kind: str, filename: str, content_type: str, data: bytes) -> dict:
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    _check_participant(hearing, user)
    validate_upload_fn(filename, content_type, len(data))
    doc_id = str(uuid.uuid4())
    ext = filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else "bin"
    path = f"hearings/{hearing_id}/{doc_id}.{ext}"
    result = put_object_fn(path, data, content_type)
    record = {
        "doc_id": doc_id,
        "hearing_id": hearing_id,
        "kind": kind,  # "order_sheet" | "case_document"
        "original_filename": filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "storage_path": result["path"],
        "is_deleted": False,
        "uploaded_by": user["user_id"],
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.hearing_documents.insert_one(record)
    update: Dict[str, Any] = {"$push": {"document_ids": doc_id}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
    if kind == "order_sheet":
        update["$set"]["order_sheet_doc_id"] = doc_id
    await db.hearing_requests.update_one({"hearing_id": hearing_id}, update)
    await _push_activity(db, hearing_id, f"{'Order sheet' if kind == 'order_sheet' else 'Case document'} uploaded: {filename}", user["user_id"])

    # Auto-chained status progressions — a real upload event, not a timer.
    sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
    if kind == "case_document" and hearing["status"] == "documents_shared":
        hearing["status"] = await _transition(db, sm, hearing, "documents_shared", "share_documents", user)
        hearing["status"] = await _transition(db, sm, hearing, "preparation", "schedule", None,
                                               note="Hearing date already confirmed at request creation")
    elif kind == "order_sheet" and hearing["status"] == "hearing_completed":
        await _transition(db, sm, hearing, "hearing_completed", "upload_order_sheet", user)
        # Starts the 3-day auto-release clock — see auto_release_stale_verifications.
        await db.hearing_requests.update_one(
            {"hearing_id": hearing_id}, {"$set": {"verification_pending_at": datetime.now(timezone.utc).isoformat()}},
        )

    record.pop("_id", None)
    return record


async def list_documents(db, hearing_id: str) -> List[dict]:
    return await db.hearing_documents.find({"hearing_id": hearing_id, "is_deleted": False}, {"_id": 0}).to_list(100)


async def add_message(db, hearing_id: str, user: dict, text: str) -> dict:
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    _check_participant(hearing, user)
    message = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "hearing_id": hearing_id,
        "sender_user_id": user["user_id"],
        "sender_name": user.get("name") or "User",
        "text": text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.hearing_messages.insert_one(message)
    message.pop("_id", None)
    return message


def other_participant_ids(hearing: dict, sender_user_id: str) -> List[str]:
    """The other side(s) of a hearing's chat thread — everyone
    `_check_participant` would admit, minus whoever just sent the message.
    Used to fan out the new-message notification without notifying yourself."""
    ids = {hearing["requesting_user_id"], hearing.get("proxy_counsel_user_id"), hearing.get("target_advocate_id")}
    ids.discard(None)
    ids.discard(sender_user_id)
    return list(ids)


async def list_messages(db, hearing_id: str) -> List[dict]:
    return await db.hearing_messages.find({"hearing_id": hearing_id}, {"_id": 0}).sort("created_at", 1).to_list(500)


async def set_negotiated_fee(db, hearing_id: str, amount: float) -> bool:
    """The one write negotiation.py makes into hearing_requests — kept here,
    not in negotiation.py, so this module stays the only writer of its own
    collection (same cross-module convention as counsel_matching.py calling
    back into hearings.accept_hearing_request rather than writing
    hearing_requests itself). Called by negotiation.accept_offer BEFORE it
    flips its own negotiation document to "agreed" — this is the single
    cross-collection serialization point against
    cancel_hearing_request/reject_hearing_request, which refuse once
    commercially_locked is set. The compare-and-swap (status not already
    terminal, not already locked) means whichever of "accept this offer" or
    "cancel/reject this hearing" reaches this document first wins; the loser
    gets nothing to match. Returns False on that loss (or if the hearing was
    already cancelled/rejected/expired moments earlier) so the caller can
    abort before ever touching the negotiations collection — an "agreed"
    negotiation must never exist on a dead hearing. From lock onward,
    initiate_payment/create-order read this fee, same as they always have,
    with no idea a negotiation happened."""
    now = datetime.now(timezone.utc).isoformat()
    result = await db.hearing_requests.update_one(
        {
            "hearing_id": hearing_id,
            "status": {"$nin": ["cancelled", "rejected", "expired"]},
            "commercially_locked": {"$ne": True},
        },
        {"$set": {"fee": amount, "commercially_locked": True, "updated_at": now}},
    )
    if result.modified_count != 1:
        return False
    await _push_activity(db, hearing_id, f"Fee agreed through negotiation: Rs.{amount} — request is now commercially locked")
    return True


async def unlock_commercially(db, hearing_id: str) -> None:
    """Compensating rollback for the narrow window where set_negotiated_fee
    above already locked the hearing but negotiation.accept_offer's own
    optimistic-concurrency write then lost (a counter-offer raced in first,
    so no agreement actually landed) — without this the hearing would be
    stuck uncancellable with no agreed fee to show for it."""
    await db.hearing_requests.update_one(
        {"hearing_id": hearing_id},
        {"$set": {"commercially_locked": False, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )


# ---------------------------------------------------------------------------
# Payment — hands off to escrow.py immediately; this module never computes
# commission/payout math itself. See server.py for the Razorpay create-order/
# verify endpoints that call these.
# ---------------------------------------------------------------------------
async def initiate_payment(db, hearing_id: str, user: dict) -> dict:
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    if hearing["requesting_user_id"] != user["user_id"]:
        raise HTTPException(403, "Only the requester can pay for this hearing")
    if not hearing.get("fee"):
        raise HTTPException(400, "A fee must be set before payment can be collected")
    # Negotiation Module: a targeted hearing must go through negotiation
    # first — payment must always use the locked, agreed amount, never the
    # original reference fee. Backend-enforced (not just a disabled frontend
    # button) for the same reason target_advocate_id/fee validation are —
    # never trust the client alone to gate a money action. Broadcast
    # requests (target_advocate_id None) never negotiate, so they're exempt.
    if hearing.get("target_advocate_id"):
        import negotiation as negotiation_svc
        negotiation = await negotiation_svc.get_negotiation(db, hearing_id)
        if not negotiation or negotiation["status"] != "agreed":
            raise HTTPException(400, "Negotiation must be agreed before payment can be collected")
    sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
    try:
        await _transition(db, sm, hearing, hearing["status"], "initiate_payment", user)
    except IllegalTransition:
        raise HTTPException(400, "Payment can't be started from this request's current status")
    return {"ok": True, "status": "payment_pending", "fee": hearing["fee"]}


async def mark_payment_confirmed(db, hearing_id: str, user: dict) -> dict:
    """Called after escrow.create_and_hold succeeds — a separate, explicit
    call into this module's own state machine (payment_pending -> broadcast,
    per the M6 reorder) so payment state and operational state never share
    one transition. The targeted-vs-broadcast distinction note used to fire
    at creation time (pre-M6); it now fires here, since this is the call that
    actually reaches "broadcast"."""
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    if hearing["requesting_user_id"] != user["user_id"]:
        raise HTTPException(403, "Only the requester can confirm payment for this hearing")
    sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
    try:
        await _transition(db, sm, hearing, hearing["status"], "confirm_payment", user,
                           note="Assigned directly to one advocate" if hearing.get("target_advocate_id")
                           else "Payment held by CourtBazaar — broadcast to available proxy counsel")
    except IllegalTransition:
        raise HTTPException(400, "This request isn't awaiting payment")
    # Escrow Module: the one timestamp check_pending_order_sheets' 3-day
    # reminder scan is measured against — set here, not in escrow.py, since
    # this module owns the "order sheet not yet uploaded" business clock,
    # not the payment/escrow mechanics themselves.
    await db.hearing_requests.update_one(
        {"hearing_id": hearing_id}, {"$set": {"payment_confirmed_at": datetime.now(timezone.utc).isoformat()}},
    )

    # M11: kick off the Counsel Matching Agent now that the hearing is
    # durably "broadcast" (the _transition above already committed it).
    # `hearing` here is still the pre-transition snapshot (status
    # "payment_pending" in memory) — that's safe because run_matching's
    # entire pipeline (discover_candidates/score_candidates/notify_tier) never
    # reads hearing["status"]; discover_candidates re-fetches the hearing by
    # hearing_id itself anyway. Best-effort: a matching failure must never
    # undo payment confirmation, which already happened above, so it's caught
    # and logged here rather than allowed to propagate.
    #
    # Targeted requests (target_advocate_id set) skip this entirely — the
    # customer already chose their advocate, so there is no AI pool to
    # discover/score/notify. The server.py caller notifies that one advocate
    # directly right after this function returns.
    if not hearing.get("target_advocate_id"):
        import counsel_matching
        from audit_log import log_audit
        try:
            await counsel_matching.run_matching(db, hearing)
        except Exception as e:
            await log_audit(db, "matching.dispatch_failed", None, {"hearing_id": hearing_id, "error": str(e)})

    return {"ok": True, "status": "broadcast"}


async def submit_case_details(db, hearing_id: str, user: dict, details: dict) -> dict:
    """Requester-only case-brief handoff — the second half of the
    BlaBlaCar-style flow (founder direction): create_hearing_request only
    ever collects court_id/hearing_date, so this is where case_title/
    case_number/case_type/case_stage/work_required/instructions actually
    reach the record. Gated on payment_confirmed_at so nothing case-specific
    is ever visible to a counsel before money is held in escrow — the whole
    point of the reorder. Not write-once: a requester can call this again to
    correct a typo; `details_submitted` only flips the frontend from "fill
    this in" to "here's what was shared", it isn't an access lock."""
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    if hearing["requesting_user_id"] != user["user_id"]:
        raise HTTPException(403, "Only the requester can share case details")
    if not hearing.get("payment_confirmed_at"):
        raise HTTPException(400, "Case details can be shared once payment is confirmed")

    common_fields = ("case_title", "case_number", "case_type", "case_stage", "hearing_time", "priority")
    service_specific_fields = ("work_required", "work_required_notes")
    existing_request_details = hearing.get("request_details") or {}
    common = {**existing_request_details.get("common", {}), **{k: details[k] for k in common_fields if k in details}}
    service_specific = {**existing_request_details.get("service_specific", {}),
                         **{k: details[k] for k in service_specific_fields if k in details}}

    update = {
        "case_details": details.get("case_details") or hearing["case_details"],
        "request_details": {"common": common, "service_specific": service_specific},
        "details_submitted": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.hearing_requests.update_one({"hearing_id": hearing_id}, {"$set": update})
    await _push_activity(db, hearing_id, "Case details shared with the counsel", user["user_id"])
    updated = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
    return updated


async def mark_hearing_conducted(db, hearing_id: str, user: dict) -> dict:
    """Advocate action — replaces the old complete_hearing_request. No
    payout side effect: that only happens after admin verification +
    a separate, explicit release-payout action (see server.py)."""
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    if hearing.get("proxy_counsel_user_id") != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(403, "Only the assigned proxy counsel can mark this hearing conducted")
    sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
    try:
        await _transition(db, sm, hearing, hearing["status"], "conduct", user)
    except IllegalTransition:
        raise HTTPException(400, "This hearing can't be marked conducted from its current status")
    return {"ok": True, "status": "hearing_completed"}


# ---------------------------------------------------------------------------
# Admin verification — Verify and Release Payout are always two separate,
# explicitly-triggered actions (never bundled) so a payout can't happen
# without a distinct verification step immediately before it.
# ---------------------------------------------------------------------------
async def verify_order_sheet(db, hearing_id: str, user: dict) -> dict:
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
    try:
        await _transition(db, sm, hearing, hearing["status"], "verify", user)
    except IllegalTransition:
        raise HTTPException(400, "This hearing isn't awaiting verification")
    await db.hearing_requests.update_one({"hearing_id": hearing_id}, {"$set": {"verification_pending_at": None}})
    return {"ok": True, "status": "verified"}


async def reject_order_sheet(db, hearing_id: str, user: dict, remark: Optional[str] = None) -> dict:
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
    try:
        await _transition(db, sm, hearing, hearing["status"], "reject_verification", user, note=remark)
    except IllegalTransition:
        raise HTTPException(400, "This hearing isn't awaiting verification")
    await db.hearing_requests.update_one({"hearing_id": hearing_id}, {"$set": {"verification_pending_at": None}})
    return {"ok": True, "status": "disputed"}


async def resolve_dispute(db, hearing_id: str, user: dict, action: str, remark: Optional[str] = None) -> dict:
    """`action`: "resubmit" (back to verification_pending for another look)
    or "refund" (refund escrow, close the request as cancelled)."""
    import escrow as escrow_svc
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    sm_action = "resubmit" if action == "resubmit" else "refund_and_cancel"
    sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
    try:
        new_status = await _transition(db, sm, hearing, hearing["status"], sm_action, user, note=remark)
    except IllegalTransition:
        raise HTTPException(400, "This hearing isn't currently disputed")
    if sm_action == "refund_and_cancel":
        await escrow_svc.refund(db, context_type="hearing", context_id=hearing_id, reason=remark or "Dispute resolved with refund")
    elif sm_action == "resubmit":
        # Back at verification_pending for another look — restart the 3-day
        # auto-release clock (see auto_release_stale_verifications).
        await db.hearing_requests.update_one(
            {"hearing_id": hearing_id}, {"$set": {"verification_pending_at": datetime.now(timezone.utc).isoformat()}},
        )
    return {"ok": True, "status": new_status}


async def release_hearing_payout(db, hearing_id: str, user: dict) -> dict:
    """verified -> completed, only reachable once verify_order_sheet has
    already run — see the transition table. Calls escrow.release, which owns
    the actual wallet credit/withdrawable math."""
    import escrow as escrow_svc
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
    try:
        await _transition(db, sm, hearing, hearing["status"], "release_payout", user)
    except IllegalTransition:
        raise HTTPException(400, "This hearing must be verified before its payout can be released")
    escrow = await escrow_svc.release(db, context_type="hearing", context_id=hearing_id, released_by_user_id=user["user_id"])
    await _push_activity(db, hearing_id, f"Payout of ₹{escrow['payee_amount']} released to advocate wallet", user["user_id"])
    await db.proxy_counsel_profiles.update_one(
        {"user_id": hearing["proxy_counsel_user_id"]}, {"$inc": {"cases_completed": 1}},
    )
    return {"ok": True, "status": "completed", "escrow": escrow}


# ---------------------------------------------------------------------------
# Escrow Module: requester-side verification. Deliberately a SEPARATE
# function from the admin pair above, not a shared helper with a role
# branch — verify_order_sheet/release_hearing_payout stay untouched, still
# two explicit admin actions, exactly as before (admin's own tooling is a
# distinct, still-valid path — e.g. manual recovery if this one fails
# partway). This is the Hiring Advocate's one-click "Verify Hearing":
# founder's explicit call, since they already personally reviewed the
# submission — unlike admin verifying on someone else's behalf, there's no
# separate-step safety value in splitting it here.
# ---------------------------------------------------------------------------
async def verify_and_release_payout(db, hearing_id: str, user: dict) -> dict:
    import escrow as escrow_svc
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    if hearing["requesting_user_id"] != user["user_id"]:
        raise HTTPException(403, "Only the requester can verify and release this hearing's payout")
    sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
    try:
        await _transition(db, sm, hearing, hearing["status"], "verify", user)
    except IllegalTransition:
        raise HTTPException(400, "This hearing isn't awaiting verification")
    await db.hearing_requests.update_one({"hearing_id": hearing_id}, {"$set": {"verification_pending_at": None}})
    try:
        await _transition(db, sm, {**hearing, "status": "verified"}, "verified", "release_payout", user)
    except IllegalTransition:
        # Verify already landed and is durable — the hearing is left at
        # "verified" rather than rolled back, so admin's existing
        # release-payout tool remains a valid manual recovery path if this
        # second step ever fails (should not happen in practice: "verified"
        # -> "release_payout" always succeeds immediately after a successful
        # verify, same actor, same request).
        raise HTTPException(500, "Verified, but payout release failed — contact support to complete it")
    escrow = await escrow_svc.release(db, context_type="hearing", context_id=hearing_id, released_by_user_id=user["user_id"])
    await _push_activity(db, hearing_id, f"Payout of ₹{escrow['payee_amount']} released to advocate wallet", user["user_id"])
    await db.proxy_counsel_profiles.update_one(
        {"user_id": hearing["proxy_counsel_user_id"]}, {"$inc": {"cases_completed": 1}},
    )
    return {"ok": True, "status": "completed", "escrow": escrow}


# ---------------------------------------------------------------------------
# Escrow Module: 3-day "upload your order sheet" reminder (founder's rule 6).
# Same registration pattern as counsel_matching.check_stalled_matches — a
# plain scan function, the actual scheduling lives in server.py's
# @app.on_event("startup") alongside the two existing APScheduler jobs.
# ---------------------------------------------------------------------------
_ORDER_SHEET_PENDING_STATUSES = ("broadcast", "documents_shared", "preparation", "hearing_scheduled", "hearing_completed")
ORDER_SHEET_REMINDER_DELAY_DAYS = 3


async def check_pending_order_sheets(db) -> int:
    """Finds hearings where escrow has been held for 3+ days with no order
    sheet uploaded yet and no reminder already sent, and notifies the
    assigned proxy counsel once (in-app + email via notifications.notify).
    Returns the count notified, for the scheduler's log line."""
    from notifications import notify, record_notification_event, get_hearing_email_thread
    cutoff = (datetime.now(timezone.utc) - timedelta(days=ORDER_SHEET_REMINDER_DELAY_DAYS)).isoformat()
    scan_cap = 500
    candidates = await db.hearing_requests.find({
        "status": {"$in": _ORDER_SHEET_PENDING_STATUSES},
        "payment_confirmed_at": {"$ne": None, "$lte": cutoff},
        "order_sheet_reminder_sent_at": None,
        "proxy_counsel_user_id": {"$ne": None},
    }, {"_id": 0}).to_list(scan_cap)
    if len(candidates) == scan_cap:
        # Not lost — just delayed to next hour's poll (each notified hearing
        # sets order_sheet_reminder_sent_at, so it drops out of the query on
        # the next pass) — but silent backlog growth at this volume is worth
        # someone noticing rather than only inferring from delayed reminders.
        logger.warning(f"check_pending_order_sheets hit its {scan_cap}-row scan cap — some reminders deferred to next poll")

    notified = 0
    for hearing in candidates:
        try:
            recipient = await db.users.find_one({"user_id": hearing["proxy_counsel_user_id"]})
            if not recipient:
                continue
            title = "Order sheet reminder"
            body = "Your payment is waiting in Escrow. Please complete the hearing and upload the Court Order Sheet to receive payment."
            ctx = {"title": title, "body": body}
            if recipient.get("email"):
                ctx["hearing_thread"] = await get_hearing_email_thread(
                    db, hearing["hearing_id"], recipient["email"],
                    f"CourtBazaar — Your Proxy Counsel Hearing (Ref: {hearing['hearing_id']})",
                )
            notify(recipient, "hearing_event", ctx)
            await record_notification_event(db, hearing["proxy_counsel_user_id"], "hearing_event", title, body, "hearing", hearing["hearing_id"])
            await db.hearing_requests.update_one(
                {"hearing_id": hearing["hearing_id"]},
                {"$set": {"order_sheet_reminder_sent_at": datetime.now(timezone.utc).isoformat()}},
            )
            notified += 1
        except Exception:
            continue  # best-effort, same as every other notify call site — one failure never blocks the rest of the scan
    return notified


# ---------------------------------------------------------------------------
# Escrow Module: 3-day auto-release. If the requester neither verifies nor
# disputes an uploaded order sheet within 3 days of it landing at
# verification_pending, escrow auto-releases to the proxy counsel exactly as
# verify_and_release_payout would — system-triggered (actor=None), same
# registration pattern as check_pending_order_sheets above.
# ---------------------------------------------------------------------------
AUTO_RELEASE_DELAY_DAYS = 3


async def auto_release_stale_verifications(db) -> int:
    """Finds hearings sitting at verification_pending for 3+ days with no
    Verify/Raise Dispute from the requester, and auto-verifies + releases
    escrow to the proxy counsel. Returns the count auto-released, for the
    scheduler's log line."""
    import escrow as escrow_svc
    from notifications import notify, record_notification_event, get_hearing_email_thread
    cutoff = (datetime.now(timezone.utc) - timedelta(days=AUTO_RELEASE_DELAY_DAYS)).isoformat()
    scan_cap = 500
    candidates = await db.hearing_requests.find({
        "status": "verification_pending",
        "verification_pending_at": {"$ne": None, "$lte": cutoff},
    }, {"_id": 0}).to_list(scan_cap)
    if len(candidates) == scan_cap:
        logger.warning(f"auto_release_stale_verifications hit its {scan_cap}-row scan cap — some releases deferred to next poll")

    released = 0
    for hearing in candidates:
        hearing_id = hearing["hearing_id"]
        try:
            # Re-fetch so a hearing verified/disputed by a human between the
            # scan above and this write is skipped cleanly rather than
            # double-processed — the _transition CAS below would also catch
            # this, but re-checking first avoids a noisy 409 in the common case.
            fresh = await db.hearing_requests.find_one({"hearing_id": hearing_id})
            if not fresh or fresh["status"] != "verification_pending":
                continue
            sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
            try:
                await _transition(db, sm, fresh, "verification_pending", "verify", None,
                                   note=f"Auto-verified — no verification or dispute from the client within {AUTO_RELEASE_DELAY_DAYS} days")
            except (IllegalTransition, HTTPException):
                continue  # lost the race to a human action between scan and write
            await db.hearing_requests.update_one({"hearing_id": hearing_id}, {"$set": {"verification_pending_at": None}})
            await _transition(db, sm, {**fresh, "status": "verified"}, "verified", "release_payout", None)
            escrow = await escrow_svc.release(db, context_type="hearing", context_id=hearing_id, released_by_user_id="system")
            await _push_activity(db, hearing_id, f"Payout of ₹{escrow['payee_amount']} auto-released to advocate wallet (no verification or dispute within {AUTO_RELEASE_DELAY_DAYS} days)")
            await db.proxy_counsel_profiles.update_one(
                {"user_id": fresh["proxy_counsel_user_id"]}, {"$inc": {"cases_completed": 1}},
            )

            title = "Payment auto-released"
            for recipient_id, body in (
                (fresh["requesting_user_id"],
                 f"You didn't verify or dispute the order sheet within {AUTO_RELEASE_DELAY_DAYS} days, so payment for your hearing at "
                 f"{fresh['court_id']} was automatically released to the proxy counsel."),
                (fresh.get("proxy_counsel_user_id"),
                 f"Payment for your hearing at {fresh['court_id']} was automatically released to your wallet — the client didn't verify "
                 f"or dispute the order sheet within {AUTO_RELEASE_DELAY_DAYS} days."),
            ):
                if not recipient_id:
                    continue
                recipient = await db.users.find_one({"user_id": recipient_id})
                if not recipient:
                    continue
                ctx = {"title": title, "body": body}
                if recipient.get("email"):
                    ctx["hearing_thread"] = await get_hearing_email_thread(
                        db, hearing_id, recipient["email"],
                        f"CourtBazaar — Your Proxy Counsel Hearing (Ref: {hearing_id})",
                    )
                notify(recipient, "hearing_event", ctx)
                await record_notification_event(db, recipient_id, "hearing_event", title, body, "hearing", hearing_id)
            released += 1
        except Exception as e:
            logger.error(f"auto_release_stale_verifications failed for {hearing_id}: {e}")
            continue  # best-effort — one failure never blocks the rest of the scan
    return released


async def list_hearings_for_admin(db, status: Optional[str] = None) -> List[dict]:
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    return await db.hearing_requests.find(query, {"_id": 0}).sort("updated_at", -1).to_list(200)


async def rate_hearing_request(db, hearing_id: str, user: dict, rating: int, review: Optional[str]) -> dict:
    if not isinstance(rating, int) or not 1 <= rating <= 5:
        raise HTTPException(400, "Rating must be a whole number from 1 to 5")
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    _check_participant(hearing, user)
    if user["user_id"] in hearing.get("rated_by", []):
        raise HTTPException(400, "You've already rated this hearing")

    is_requester = user["user_id"] == hearing["requesting_user_id"]
    rated_user_id = hearing["proxy_counsel_user_id"] if is_requester else hearing["requesting_user_id"]
    if not rated_user_id:
        raise HTTPException(400, "Nothing to rate yet")

    await db.professional_ratings.insert_one({
        "rating_id": f"prating_{uuid.uuid4().hex[:12]}",
        "rated_user_id": rated_user_id,
        "rated_by_user_id": user["user_id"],
        "context_type": "hearing",
        "context_id": hearing_id,
        "rating": rating,
        "review": review,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    sm = StateMachine(HEARING_TRANSITIONS, _make_timeline_hook(db))
    try:
        await _transition(db, sm, hearing, hearing["status"], "rate", user)
    except IllegalTransition:
        raise HTTPException(400, "This hearing can't be rated yet")
    await db.hearing_requests.update_one(
        {"hearing_id": hearing_id}, {"$addToSet": {"rated_by": user["user_id"]}},
    )

    # Recompute the rated professional's average — same pattern as
    # server.py's rate_order recomputing db.vendors.rating.
    if is_requester:
        cursor = db.professional_ratings.find({"rated_user_id": rated_user_id}, {"rating": 1})
        ratings = [d["rating"] async for d in cursor]
        if ratings:
            avg = sum(ratings) / len(ratings)
            await db.proxy_counsel_profiles.update_one({"user_id": rated_user_id}, {"$set": {"rating": round(avg, 2)}})
    return {"ok": True}
