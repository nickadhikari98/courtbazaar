import React from "react";
import { Activity } from "lucide-react";
import { humanizeHearingActivity } from "@/lib/hearingLifecycle";

/* Renders hearing.timeline chronologically — the canonical activity history
   for a hearing (every status transition plus non-transition events like
   document uploads and escrow hold/release). Default "friendly" mode never
   shows the raw workflow transition string a state-machine hop writes to
   `note` (hearings.py's _make_timeline_hook writes literally
   "<from_status> -> <to_status>") — every user-facing caller gets a
   business-readable event via humanizeHearingActivity instead. Pass
   mode="raw" for an admin/audit screen that genuinely needs the literal
   technical trail (see AdminHearingVerification.jsx). */
export default function HearingTimeline({ timeline, hearing, mode = "friendly" }) {
  if (!timeline?.length) return null;
  const entries = [...timeline].reverse();
  return (
    <div>
      <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1.5 flex items-center gap-1.5">
        <Activity className="w-3.5 h-3.5" /> Activity history
      </div>
      <div className="space-y-1.5 max-h-48 overflow-y-auto cb-scroll">
        {entries.map((e, i) => {
          if (mode === "raw") {
            return (
              <div key={i} className="text-xs border-l-2 border-accent/30 pl-2.5 py-0.5">
                <div className="font-semibold">{e.note}</div>
                <div className="text-muted-foreground">{new Date(e.at).toLocaleString("en-IN")}</div>
              </div>
            );
          }
          const { icon: Icon, title, description } = humanizeHearingActivity(e, hearing);
          return (
            <div key={i} className="flex items-start gap-2 border-l-2 border-accent/30 pl-2.5 py-0.5">
              <Icon className="w-3.5 h-3.5 text-muted-foreground mt-0.5 flex-shrink-0" strokeWidth={2} />
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold">{title}</div>
                <div className="text-xs text-muted-foreground">{description}</div>
                <div className="text-2xs text-muted-foreground/70">{new Date(e.at).toLocaleString("en-IN")}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
