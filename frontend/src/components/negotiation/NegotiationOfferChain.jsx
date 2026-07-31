import React from "react";
import { ArrowRight } from "lucide-react";
import { formatINR } from "@/lib/api";

/* "Offer ₹2200 → Counter ₹2500 → Agreement ₹2500" — the commercial half of
   the redesigned Timeline section (item 6 of the founder's UX ask), reusing
   negotiation.timeline (already the source HearingTimeline/NegotiationChat
   read) rather than a new backend field. Sits above HearingProgressStepper,
   which continues the same visual line into the operational stages
   (Payment → Broadcast → ... → Payout Released). */
export default function NegotiationOfferChain({ negotiation }) {
  const events = (negotiation?.timeline || []).filter((e) => e.event === "offer_proposed" || e.event === "negotiation_agreed");
  if (!events.length) return null;

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="negotiation-offer-chain">
      {events.map((e, i) => {
        const isAgreed = e.event === "negotiation_agreed";
        const label = isAgreed ? "Agreement" : (e.detail.is_counter ? "Counter" : "Offer");
        return (
          <React.Fragment key={`${e.event}_${e.at}`}>
            {i > 0 && <ArrowRight className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />}
            <div
              className={`text-2xs font-bold px-2.5 py-1 rounded-full border ${
                isAgreed ? "bg-emerald-100 text-emerald-700 border-emerald-200" : "bg-secondary text-foreground border-border"
              }`}
            >
              {label} {formatINR(e.detail.amount)}
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}
