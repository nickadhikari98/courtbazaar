import React from "react";
import { Activity } from "lucide-react";

/* Renders hearing.timeline chronologically — the canonical activity history
   for a hearing (every status transition plus non-transition events like
   document uploads and escrow hold/release), not just its current status. */
export default function HearingTimeline({ timeline }) {
  if (!timeline?.length) return null;
  const entries = [...timeline].reverse();
  return (
    <div>
      <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1.5 flex items-center gap-1.5">
        <Activity className="w-3.5 h-3.5" /> Activity history
      </div>
      <div className="space-y-1.5 max-h-48 overflow-y-auto">
        {entries.map((e, i) => (
          <div key={i} className="text-xs border-l-2 border-accent/30 pl-2.5 py-0.5">
            <div className="font-semibold">{e.note}</div>
            <div className="text-muted-foreground">{new Date(e.at).toLocaleString("en-IN")}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
