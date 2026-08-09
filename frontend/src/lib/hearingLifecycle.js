/* Canonical hearing lifecycle/permission resolver — the ONE place every
   screen that shows a hearing (NegotiationModule.jsx, HearingDetailDialog.jsx,
   Dashboard.jsx, Practice.jsx, HireProxyCounsel.jsx) derives status text,
   viewer role, and action-eligibility from. Before this file existed, each
   of those screens computed its own copy of these booleans independently —
   see the production-hardening audit notes below for what that had already
   let drift out of sync. Pure functions only, no React state, no fetching:
   every input is data the caller already has (hearing, user).

   Audit findings this file fixes by existing as the single source:
   - HearingDetailDialog.jsx's inline `isEligibleAdvocate` never checked
     `can_practice_proxy_counsel`, unlike homeWidgets.js's (now this file's)
     `hearingIsAcceptableByMe` — the backend already enforced the capability
     (hearings._check_visible), so this was a UI-only gap (a button could
     render that the backend would then 403), not a security hole, but it's
     exactly the kind of two-screens-disagree bug this file exists to kill.
   - NegotiationModule.jsx derived "is the deal agreed" from the separately-
     polled `negotiation.status`, while HearingDetailDialog.jsx/Dashboard.jsx
     derived it from `hearing.commercially_locked` — two different data
     sources, fetched on two different cadences, that are *supposed* to
     always agree (hearings.set_negotiated_fee sets them atomically) but
     could disagree for the moment between an action and the next poll tick.
     `hearing.commercially_locked` is what the backend itself checks
     (hearings.initiate_payment/cancel_hearing_request), so it's the
     canonical source everywhere now.
   - HearingDetailDialog.jsx showed the raw `hearing.status` string as its
     badge; NegotiationModule.jsx showed a role-aware label for the same
     status. Same hearing, different text depending on which screen you
     opened it from — roleAwareStatusLabel below is now shared by both. */

import {
  FileText, Handshake, UploadCloud, CheckCircle2, CalendarClock, Gavel,
  ShieldCheck, AlertTriangle, Banknote, Star, XCircle, Ban, Clock, Info, Wallet,
} from "lucide-react";

// Truly closed — no further action possible, matches the UI's own "start a
// new request to try again" copy. Deliberately excludes "disputed": that's
// still open, under active admin review (resubmit or refund), not a dead
// end — treating it as closed would be wrong everywhere it's checked.
export const CLOSED_HEARING_STATUSES = ["rejected", "cancelled", "expired"];

export function isHearingClosed(hearing) {
  return !!hearing && CLOSED_HEARING_STATUSES.includes(hearing.status);
}

// Successful, paid-out dead ends — distinct from CLOSED_HEARING_STATUSES
// (rejected/cancelled/expired), which are dead ends with no payout.
export const COMPLETED_HEARING_STATUSES = ["completed", "rated"];

// Still moving: not yet a dead end either way. This is the default-view
// filter for hearing-list screens (Hire Proxy Counsel, My Practice) — keeps
// the list focused on actionable work, with Completed/Cancelled as
// separate tabs rather than mixed into the same list.
export function isHearingActive(hearing) {
  return !!hearing && !CLOSED_HEARING_STATUSES.includes(hearing.status) && !COMPLETED_HEARING_STATUSES.includes(hearing.status);
}

// Same palette every screen showing a hearing.status badge uses.
export const HEARING_STATUS_BADGE_COLOR = {
  requested: "bg-amber-100 text-amber-700",
  broadcast: "bg-amber-100 text-amber-700",
  accepted: "bg-blue-100 text-blue-700",
  payment_pending: "bg-amber-100 text-amber-700",
  documents_shared: "bg-blue-100 text-blue-700",
  preparation: "bg-blue-100 text-blue-700",
  hearing_scheduled: "bg-blue-100 text-blue-700",
  hearing_completed: "bg-indigo-100 text-indigo-700",
  verification_pending: "bg-amber-100 text-amber-700",
  verified: "bg-emerald-100 text-emerald-700",
  completed: "bg-emerald-100 text-emerald-700",
  rated: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
  cancelled: "bg-red-100 text-red-700",
  disputed: "bg-red-100 text-red-700",
  expired: "bg-slate-100 text-slate-600",
};

export function getViewerRole(hearing, userId) {
  if (!hearing || !userId) return null;
  return hearing.requesting_user_id === userId ? "customer" : "counsel";
}

// Same underlying hearing.status, different words per role — "only the
// Hiring Advocate pays" is a business rule, so the badge shouldn't describe
// the payment/escrow stage identically to someone who never pays. Falls
// back to the raw status for stages this hand-off doesn't cover.
export function roleAwareStatusLabel(hearing, viewerRole) {
  if (hearing.status === "requested" && hearing.commercially_locked) {
    return viewerRole === "customer" ? "Payment Required" : "Waiting for Hiring Advocate Payment";
  }
  if (hearing.status === "payment_pending") {
    return viewerRole === "customer" ? "Payment Processing" : "Waiting for Hiring Advocate Payment";
  }
  if (hearing.status === "broadcast" && hearing.target_advocate_id) {
    return viewerRole === "customer" ? "Payment Completed — Escrow Funded" : "Escrow Funded";
  }
  return hearing.status.replace(/_/g, " ");
}

/* Broadcast (or targeted-at-me) requests I'm eligible to accept — the
   backend's own gate (hearings._check_visible/accept_hearing_request) also
   requires can_practice_proxy_counsel; this mirrors it exactly so the
   frontend never shows an Accept/Decline/Reject button the backend would
   then refuse. */
export function hearingIsAcceptableByMe(h, user) {
  if (!user?.capabilities?.includes("can_practice_proxy_counsel")) return false;
  if (h.requesting_user_id === user.user_id || h.proxy_counsel_user_id === user.user_id) return false;
  return h.status === "broadcast" && (!h.target_advocate_id || h.target_advocate_id === user.user_id);
}

/* The commercial gate for payment — mirrors hearings.initiate_payment's
   server-side check exactly: a fee must be set, and a *targeted* hearing
   must be commercially locked; a broadcast hearing (no target_advocate_id)
   never negotiates and is exempt. hearing.status alone can't answer this —
   "requested" covers "not negotiated yet", "negotiating", AND "agreed,
   awaiting payment" all as the same status value. */
export function hearingCommerciallyReadyForPayment(h) {
  return !!h.fee && (!h.target_advocate_id || !!h.commercially_locked);
}

export function hearingNeedsMyDocument(h, userId) {
  return (h.requesting_user_id === userId && h.status === "documents_shared")
    || (h.proxy_counsel_user_id === userId && h.status === "hearing_completed");
}

// "requested" is the normal pre-payment state; "payment_pending" is included
// too because a hearing lands there and can get stuck the moment a payment
// attempt is *initiated* (create-order) even if the Razorpay checkout right
// after it is abandoned or fails — initiate_payment now self-loops on
// "payment_pending" precisely so a retry from here is possible (see
// hearings.HEARING_TRANSITIONS), and the requester must never be left
// staring at a hearing with no way back to Pay.
export const PAYABLE_HEARING_STATUSES = ["requested", "payment_pending"];

export function hearingNeedsMyAction(h, user) {
  const paymentDue = h.requesting_user_id === user?.user_id && PAYABLE_HEARING_STATUSES.includes(h.status)
    && hearingCommerciallyReadyForPayment(h);
  return paymentDue
    // Live fee negotiation where the ball is in my court (make the opening
    // offer, or respond to a standing offer from the other side). Computed
    // server-side in hearings._attach_negotiation_action_flags because whose
    // turn it is lives in the negotiations collection, not on the hearing doc.
    // Without this, a hearing stuck at "Negotiating Fee" never counted here.
    || !!h.negotiation_action_required
    || (h.proxy_counsel_user_id === user?.user_id && h.status === "hearing_scheduled") // mark conducted due
    || hearingIsAcceptableByMe(h, user);
}

/* Full permission/state bundle — the one call NegotiationModule.jsx and
   HearingDetailDialog.jsx both make instead of each re-deriving these
   booleans locally. Returns {} for a not-yet-loaded hearing so callers can
   destructure before their own loading guard without a null-check dance. */
export function getHearingPermissions(hearing, user) {
  if (!hearing) return {};
  const userId = user?.user_id;
  const isRequester = hearing.requesting_user_id === userId;
  const isAssignedProxyCounsel = hearing.proxy_counsel_user_id === userId;
  const isTargetedAtMe = hearing.target_advocate_id === userId;
  const isEligibleAdvocate = hearingIsAcceptableByMe(hearing, user);
  const canAccept = isEligibleAdvocate;
  const canDecline = isEligibleAdvocate && !hearing.target_advocate_id;
  // Deliberately NOT gated on isEligibleAdvocate as a whole (which requires
  // status "broadcast", i.e. post-payment) — hearings.HEARING_TRANSITIONS
  // defines ("requested", "reject") specifically so the targeted advocate
  // can walk away during pre-payment negotiation too, not just from
  // "broadcast" (see hearings.py's module docstring and
  // reject_hearing_request). Still requires can_practice_proxy_counsel,
  // matching the backend endpoint's own capability gate (server.py's PUT
  // .../reject), same "never show a button the backend would then 403"
  // rule the rest of this file follows. Commercially locked (fee agreed)
  // hearings can no longer be walked away from through this pre-negotiation
  // path — mirrors the backend refusal in
  // hearings.reject_hearing_request/cancel_hearing_request.
  const canReject = !!user?.capabilities?.includes("can_practice_proxy_counsel")
    && isTargetedAtMe && !hearing.commercially_locked && ["requested", "broadcast"].includes(hearing.status);
  const negotiationRequired = !!hearing.target_advocate_id;
  const negotiationAgreed = !!hearing.commercially_locked;
  const negotiationPending = (isRequester || isTargetedAtMe) && hearing.status === "requested"
    && negotiationRequired && !negotiationAgreed;
  const canPay = isRequester && PAYABLE_HEARING_STATUSES.includes(hearing.status) && hearingCommerciallyReadyForPayment(hearing);
  const canCancel = isRequester && !hearing.commercially_locked
    && ["requested", "broadcast", "accepted", "payment_pending", "documents_shared", "preparation", "hearing_scheduled", "hearing_completed"].includes(hearing.status);
  const canMarkConducted = isAssignedProxyCounsel && hearing.status === "hearing_scheduled";
  const canRate = ["completed", "rated"].includes(hearing.status) && !hearing.rated_by?.includes(userId)
    && (isRequester || isAssignedProxyCounsel);
  // Escrow Module: only an actual participant ever sees EscrowStagePanel —
  // never an admin or a browsing not-yet-assigned eligible advocate,
  // regardless of which screen renders it.
  const isEscrowParticipant = isRequester || isAssignedProxyCounsel;

  return {
    isRequester, isAssignedProxyCounsel, isTargetedAtMe, isEligibleAdvocate,
    canAccept, canDecline, canReject, canCancel, canMarkConducted, canRate, canPay,
    negotiationRequired, negotiationAgreed, negotiationPending, isEscrowParticipant,
    viewerRole: getViewerRole(hearing, userId),
    isClosed: isHearingClosed(hearing),
  };
}

/* Business-friendly event per to_status — for a hearing.timeline entry
   produced by a state-machine transition (hearings.py's
   _make_timeline_hook writes every entry's `note` as the literal
   "<from_status> -> <to_status>" string and `status` as the to_status).
   That raw string is an implementation detail of the workflow engine, not
   something a Hiring Advocate or Proxy Counsel should ever read — admin/
   audit views may still show the raw transition; every user-facing screen
   must go through humanizeHearingActivity below instead. "requested" never
   appears here because no transition ever produces it (it's only the
   hearing's initial status). */
const HEARING_TRANSITION_EVENT_META = {
  payment_pending: { icon: Wallet, title: "Payment Initiated", description: (h) => `Payment for ${h.court_id || "this hearing"} was initiated — redirecting to checkout.` },
  broadcast: { icon: Wallet, title: "Payment Successful", description: (h) => `Payment confirmed — ${h.fee ? `₹${h.fee} is` : "funds are"} now held in escrow.` },
  accepted: { icon: Handshake, title: "Proxy Counsel Accepted Hearing", description: (h) => `A Proxy Counsel accepted the request for ${h.court_id || "this hearing"}.` },
  documents_shared: { icon: UploadCloud, title: "Case Documents Needed", description: (h) => `Case documents are being exchanged for ${h.court_id || "this hearing"}.` },
  preparation: { icon: CheckCircle2, title: "Documents Shared", description: (h) => `Case documents were shared — ${h.court_id || "the hearing"} is being prepared.` },
  hearing_scheduled: { icon: CalendarClock, title: "Hearing Scheduled", description: (h) => `The hearing at ${h.court_id || "court"} has been scheduled${h.hearing_date ? ` for ${h.hearing_date}` : ""}.` },
  hearing_completed: { icon: Gavel, title: "Hearing Conducted", description: (h) => `The hearing at ${h.court_id || "court"} was conducted.` },
  verification_pending: { icon: UploadCloud, title: "Order Sheet Uploaded", description: (h) => `The Court Order Sheet for ${h.court_id || "the hearing"} is awaiting verification.` },
  verified: { icon: ShieldCheck, title: "Hearing Verified", description: (h) => `The order sheet for ${h.court_id || "the hearing"} was verified.` },
  disputed: { icon: AlertTriangle, title: "Order Sheet Disputed", description: (h) => `The order sheet for ${h.court_id || "the hearing"} was disputed and is under review.` },
  completed: { icon: Banknote, title: "Escrow Released", description: (h) => `Escrow for ${h.court_id || "the hearing"} has been released.` },
  rated: { icon: Star, title: "Rating Submitted", description: () => "A rating was submitted for this hearing." },
  rejected: { icon: XCircle, title: "Request Declined", description: (h) => `The hearing request for ${h.court_id || "this hearing"} was declined.` },
  cancelled: { icon: Ban, title: "Request Cancelled", description: (h) => `The hearing request for ${h.court_id || "this hearing"} was cancelled.` },
  expired: { icon: Clock, title: "Request Expired", description: (h) => `The hearing request for ${h.court_id || "this hearing"} expired.` },
};

// Overrides HEARING_TRANSITION_EVENT_META's by-to_status lookup for specific
// (from_status, to_status) pairs where the same to_status is reached two
// meaningfully different ways — today just the one case: a fresh order-sheet
// upload (hearing_completed -> verification_pending) reads nothing like
// admin approving a resubmission after a dispute (disputed ->
// verification_pending), so the latter needs its own label instead of
// silently reading as a first-time upload.
const HEARING_TRANSITION_EVENT_OVERRIDES = {
  disputed: {
    verification_pending: {
      icon: UploadCloud, title: "Order Sheet Resubmitted",
      description: (h) => `A corrected Court Order Sheet for ${h.court_id || "the hearing"} was resubmitted and is awaiting verification.`,
    },
  },
};

// Non-transition entries (hearings.py's _push_activity — document uploads,
// negotiated fee, refunds, payout release) already carry a full, readable
// sentence in `note`; these just need a short title split out of it, not a
// business-event lookup.
function describeFreeTextActivity(note) {
  if (note === "Request created") return { icon: FileText, title: "Request Created" };
  if (note?.startsWith("Order sheet uploaded")) return { icon: UploadCloud, title: "Order Sheet Uploaded" };
  if (note?.startsWith("Case document uploaded")) return { icon: UploadCloud, title: "Case Document Uploaded" };
  if (note?.startsWith("Fee agreed")) return { icon: Handshake, title: "Fee Agreed" };
  if (note?.startsWith("Payout of")) return { icon: Banknote, title: "Payout Released" };
  if (note?.startsWith("Escrow refunded")) return { icon: Banknote, title: "Refund Issued" };
  return { icon: Info, title: "Update" };
}

/* The one place a hearing.timeline entry becomes user-facing text. Returns
   {icon, title, description} — never the raw entry.note transition string.
   `hearing` is optional context (court_id/fee/hearing_date) for the
   description; omit it and the description just reads a little more
   generically. */
export function humanizeHearingActivity(entry, hearing) {
  const h = hearing || {};
  if (entry.note?.includes(" -> ")) {
    const [fromStatus] = entry.note.split(" -> ");
    const meta = HEARING_TRANSITION_EVENT_OVERRIDES[fromStatus]?.[entry.status] || HEARING_TRANSITION_EVENT_META[entry.status];
    if (meta) return { icon: meta.icon, title: meta.title, description: meta.description(h) };
    return { icon: Info, title: "Status Updated", description: `${h.court_id || "This hearing"} was updated.` };
  }
  // accept_hearing_request pushes the first broadcast -> accepted entry
  // directly ({status, at, by}), without going through _transition/
  // _make_timeline_hook — so it has a `status` but no "from -> to" `note` to
  // match the branch above. Same business event, just missing that note;
  // still look it up by status before falling through to free-text handling
  // (which would otherwise read this as a contentless "Update").
  if (!entry.note && entry.status && HEARING_TRANSITION_EVENT_META[entry.status]) {
    const meta = HEARING_TRANSITION_EVENT_META[entry.status];
    return { icon: meta.icon, title: meta.title, description: meta.description(h) };
  }
  const { icon, title } = describeFreeTextActivity(entry.note);
  return { icon, title, description: entry.note || "" };
}
