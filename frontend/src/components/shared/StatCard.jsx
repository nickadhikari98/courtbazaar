import React from "react";

/* Plain label/value stat tile — no icon badge, unlike the heavier StatGrid
   (which requires an icon+color per stat). Was defined identically in both
   AdminLeads and AdminReviews for their simpler status-count summary rows. */
export default function StatCard({ label, value }) {
  return (
    <div className="rounded-lg border bg-white px-4 py-3">
      <div className="text-2xl font-display font-black tracking-tight">{value}</div>
      <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wide mt-0.5">{label}</div>
    </div>
  );
}
