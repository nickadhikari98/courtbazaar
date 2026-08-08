import React from "react";
import { humanizeHearingActivity } from "@/lib/hearingLifecycle";
import { timeAgo } from "@/lib/utils";

/* A one-line "what happened last" preview for a hearing's row/card in a
   list (HireProxyCounsel.jsx's My Requests, Practice.jsx's Open Requests/My
   Hearings) — so the latest activity (payment confirmed, escrow funded,
   order sheet uploaded, ...) is visible without opening HearingDetailDialog
   first. Reuses the same hearing.timeline + humanizeHearingActivity the
   dialog's own HearingTimeline renders in full, just the single latest
   entry instead of the whole history. Renders nothing for a hearing with no
   timeline yet (freshly created, nothing has happened), same as
   HearingTimeline's own empty-state. */
export default function HearingActivityPreview({ hearing }) {
  const latest = hearing?.timeline?.[hearing.timeline.length - 1];
  if (!latest) return null;
  const { icon: Icon, title, description } = humanizeHearingActivity(latest, hearing);
  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-foreground min-w-0 mt-1">
      <Icon className="w-3.5 h-3.5 flex-shrink-0" strokeWidth={2} />
      <span className="font-semibold text-foreground flex-shrink-0">{title}</span>
      {description && <span className="truncate">— {description}</span>}
      <span className="flex-shrink-0 ml-auto pl-2">{timeAgo(latest.at)}</span>
    </div>
  );
}
