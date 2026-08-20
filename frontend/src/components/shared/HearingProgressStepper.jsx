import React from "react";
import { Check, X, Ban, ShieldAlert, Clock } from "lucide-react";

/* Prospective, at-a-glance progress for the Hire Proxy Counsel journey —
   complements HearingTimeline (the retrospective activity log) rather than
   replacing it. Maps the real hearing.status values (backend/hearings.py's
   HEARING_STATUSES) onto the founder's reference stages.

   Two tracks, not one — a targeted/negotiated hearing (target_advocate_id
   set) never actually goes through an open marketplace broadcast; showing
   it "Broadcast to Advocates → Accepted → Documents Shared → Preparation"
   was leftover legacy-workflow language that stopped matching the business
   process once the Negotiation Module + Escrow Module shipped, and
   contradicted the role-aware status badge (lib/hearingLifecycle.js) sitting
   right next to it. `targeted` (== !!hearing.target_advocate_id, same field
   the rest of the lifecycle resolver keys off) picks which one renders; the
   underlying hearing.status values are identical either way — only the
   user-facing grouping/labels differ, never the backend state machine. */
const BROADCAST_STAGES = [
  // "requested" is overloaded on the backend — it covers "not negotiated
  // yet", "negotiating", AND "agreed, awaiting payment" all as the same
  // status value. `negotiationAgreed` (derived by the caller from
  // hearing.commercially_locked, the actual source of truth) disambiguates
  // the label without adding an extra step to the sequence.
  { statuses: ["requested", "payment_pending"], label: "Payment Pending", labelWhenNegotiating: "Negotiating Fee" },
  { statuses: ["broadcast"], label: "Broadcast to Advocates" },
  { statuses: ["accepted"], label: "Accepted" },
  { statuses: ["documents_shared"], label: "Documents Shared" },
  { statuses: ["preparation"], label: "Preparation" },
  { statuses: ["hearing_scheduled"], label: "Hearing Conducted" },
  { statuses: ["hearing_completed"], label: "Order Sheet Uploaded" },
  { statuses: ["verification_pending", "verified"], label: "Verified" },
  { statuses: ["completed"], label: "Payout Released" },
  { statuses: ["rated"], label: "Reviewed" },
];

// Same backend statuses as BROADCAST_STAGES, grouped into the 5-stage
// escrow-centric view a targeted/negotiated hearing actually reads as:
// there's no advocate pool to broadcast to or accept from (the counsel was
// already chosen in Negotiation), so broadcast/accepted/documents_shared/
// preparation/hearing_scheduled collapse into one "funds are secured,
// nothing for you to see yet" stage instead of four marketplace-specific
// steps that never applied to this hearing.
const TARGETED_STAGES = [
  { statuses: ["requested", "payment_pending"], label: "Payment", labelWhenNegotiating: "Negotiating Fee" },
  { statuses: ["broadcast", "accepted", "documents_shared", "preparation", "hearing_scheduled"], label: "Escrow Funded" },
  { statuses: ["hearing_completed"], label: "Order Sheet Uploaded" },
  { statuses: ["verification_pending", "verified"], label: "Verification" },
  { statuses: ["completed", "rated"], label: "Escrow Released" },
];

const TERMINATED = {
  rejected: { label: "Rejected", icon: X },
  cancelled: { label: "Cancelled", icon: Ban },
  disputed: { label: "Disputed — under review", icon: ShieldAlert },
  expired: { label: "Expired", icon: Clock },
};

function stageIndexFor(stages, status) {
  const idx = stages.findIndex((s) => s.statuses.includes(status));
  return idx === -1 ? 0 : idx;
}

function stageLabel(stage, status, negotiationAgreed) {
  if (stage.labelWhenNegotiating && status === "requested" && !negotiationAgreed) {
    return stage.labelWhenNegotiating;
  }
  return stage.label;
}

export default function HearingProgressStepper({ status, compact = false, negotiationAgreed = true, targeted = false }) {
  const terminated = TERMINATED[status];

  if (terminated) {
    const Icon = terminated.icon;
    return (
      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-red-600" data-testid="hearing-stepper-terminated">
        <Icon className="w-3.5 h-3.5" /> {terminated.label}
      </div>
    );
  }

  const stages = targeted ? TARGETED_STAGES : BROADCAST_STAGES;
  const currentIndex = stageIndexFor(stages, status);

  if (compact) {
    return (
      <div className="text-xs font-semibold text-muted-foreground" data-testid="hearing-stepper-compact">
        Step {currentIndex + 1} of {stages.length}: <span className="text-foreground font-bold">{stageLabel(stages[currentIndex], status, negotiationAgreed)}</span>
      </div>
    );
  }

  return (
    <div className="w-full overflow-x-auto cb-scroll" data-testid="hearing-stepper">
      <div className="flex items-center min-w-max">
        {stages.map((stage, i) => {
          const done = i < currentIndex;
          const active = i === currentIndex;
          return (
            <div key={stage.label} className="flex items-center">
              <div className="flex flex-col items-center gap-1 w-24">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center text-2xs font-bold border-2 ${
                    done
                      ? "bg-accent border-accent text-white"
                      : active
                        ? "border-accent text-accent bg-accent/10"
                        : "border-border text-muted-foreground bg-white"
                  }`}
                >
                  {done ? <Check className="w-3 h-3" /> : i + 1}
                </div>
                <div className={`text-2xs text-center leading-tight font-semibold ${active ? "text-foreground" : "text-muted-foreground"}`}>
                  {stageLabel(stage, status, negotiationAgreed)}
                </div>
              </div>
              {i < stages.length - 1 && (
                <div className={`h-0.5 w-6 -mt-4 ${done ? "bg-accent" : "bg-border"}`} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
