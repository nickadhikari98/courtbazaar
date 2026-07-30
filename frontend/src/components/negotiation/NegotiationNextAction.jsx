import React from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ArrowRight, Loader2 } from "lucide-react";
import { formatINR } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/negotiationRoles";

/* Single always-visible directive, item 5 of the founder's redesign ask —
   "never make the user guess what to do next." Deliberately text-only for
   the no_offer/waiting/action_required stages (those stages' own actions —
   Propose/Accept/Counter — already live in NegotiationOfferPanel directly
   above; repeating the buttons here would be a second, competing place to
   click, which is the opposite of "obvious"). Once agreed, this is where the
   actual Pay button lives (moved out of its own separate card) so there is
   exactly one payment CTA on the page, not two.

   `canPay` is passed down from the same lib/hearingLifecycle.js resolver
   HearingDetailDialog.jsx uses — this component never re-derives its own
   "can this viewer pay" logic from viewerRole/hearing.status locally, so
   the two screens can't drift on when the button shows. */
export default function NegotiationNextAction({ stage, viewerRole, hearing, canPay, paying, onPay }) {
  const navigate = useNavigate();
  const otherRoleLabel = ROLE_LABEL[viewerRole === "customer" ? "counsel" : "customer"];

  // create-order's initiate_payment call can land the hearing on
  // "payment_pending" even when the Razorpay checkout right after it is
  // abandoned or fails — hearings.HEARING_TRANSITIONS now self-loops
  // ("payment_pending","initiate_payment"):"payment_pending" precisely so
  // canPay stays true here and a retry is always possible, instead of a
  // dead end with no button and no way back to "requested".
  if (hearing.status === "payment_pending") {
    return (
      <Card className="border-none bg-amber-50 shadow-none" data-testid="next-action">
        <CardContent className="p-4 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2 text-sm font-semibold text-amber-800">
            <ArrowRight className="w-4 h-4 flex-shrink-0" />
            {viewerRole === "customer"
              ? "A previous payment attempt didn't complete — escrow was never funded."
              : "The requester's payment didn't go through yet — waiting for them to retry."}
          </div>
          {canPay && (
            <Button type="button" onClick={onPay} disabled={paying} className="bg-accent hover:bg-accent/90 font-bold" data-testid="retry-pay-via-escrow">
              {paying && <Loader2 className="w-4 h-4 animate-spin mr-1.5" />} Retry Payment — {formatINR(hearing.fee)}
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  // Payment just landed (targeted hearing, escrow held via
  // escrow.create_and_hold at payment-verify time) — role-aware because only
  // the Hiring Advocate ever pays. The Proxy Counsel's real next action here
  // is Accept — that button lives in HearingDetailDialog/Practice.jsx (per
  // the founder's explicit call not to touch that machinery), not on this
  // page, so this card names the action and links there instead of
  // duplicating the button — the vague "waiting for you to perform the
  // hearing" text this used to show never actually said Accept was needed,
  // which is the gap traced in the production audit.
  if (hearing.status === "broadcast" && hearing.target_advocate_id) {
    return (
      <Card className="border-none bg-emerald-50 shadow-none" data-testid="next-action">
        <CardContent className="p-4 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-800">
            <ArrowRight className="w-4 h-4 flex-shrink-0" />
            {viewerRole === "customer"
              ? "Payment completed — escrow funded. Waiting for the Proxy Counsel to accept and begin work."
              : "Escrow funded — accept this hearing to begin."}
          </div>
          {viewerRole === "counsel" && (
            <Button type="button" variant="outline" className="font-bold" onClick={() => navigate("/practice")} data-testid="go-to-practice-accept">
              Go to Practice to Accept
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  // Only meaningful during the pre-payment negotiation window — once the
  // hearing moves past "requested"/"payment_pending"/"broadcast",
  // HearingProgressStepper (Timeline section below) already carries the
  // current-stage signal.
  if (hearing.status !== "requested") return null;

  if (stage !== "agreed") {
    const text = {
      no_offer: "Propose an offer above to begin the fee negotiation.",
      waiting: `Waiting for ${otherRoleLabel} to respond to your offer.`,
      action_required: "Accept the offer above, or send a counter, to move forward.",
    }[stage];
    return (
      <Card className="border-none bg-secondary/50 shadow-none" data-testid="next-action">
        <CardContent className="p-4 flex items-center gap-2 text-sm font-semibold">
          <ArrowRight className="w-4 h-4 text-accent flex-shrink-0" /> {text}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-none bg-accent/5 shadow-none" data-testid="next-action">
      <CardContent className="p-4 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <ArrowRight className="w-4 h-4 text-accent flex-shrink-0" />
          Amount locked at {formatINR(hearing.fee)} — {canPay
            ? "payment required to proceed."
            : "waiting for Hiring Advocate payment."}
        </div>
        {canPay && (
          <Button type="button" onClick={onPay} disabled={paying} className="bg-accent hover:bg-accent/90 font-bold" data-testid="pay-via-escrow">
            {paying && <Loader2 className="w-4 h-4 animate-spin mr-1.5" />} Pay {formatINR(hearing.fee)} via Escrow
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
