import React from "react";
import { Link } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";

/* Generic stat-tile grid — configuration-only, no page-specific assumptions.
   Takes a plain `stats` array and renders it; has no idea whether it's
   powering Dashboard, Practice, Earnings, or an admin page. This is the
   single place the icon-badge + cb-overline + big-number card markup
   exists — previously hand-duplicated on each of those pages with drifting
   icon-badge sizes (w-9 vs w-10).

   Each stat is {label, value, icon, color, sub?, link?} — `sub` (a small
   caption line) and `link` (a trailing "View →") are optional, read
   defensively, and simply don't render when a page's stats don't need
   them (e.g. Dashboard/Practice/Earnings' plain stats vs. the admin
   console's richer KPI tiles). */
export default function StatGrid({ stats, columns = "grid-cols-2 lg:grid-cols-4", className = "", testIdPrefix = "stat" }) {
  return (
    <div className={`grid ${columns} gap-4 ${className}`}>
      {stats.map((s) => (
        <Card key={s.label} className={`dashboard-card border-none ${s.link ? "hover:shadow-md transition-all" : ""}`} data-testid={`${testIdPrefix}-${s.label.toLowerCase().replace(/\s+/g, '-')}`}>
          <CardContent className="p-5">
            <div className={`w-10 h-10 rounded-lg ${s.color} flex items-center justify-center mb-3`}>
              <s.icon className="w-5 h-5" />
            </div>
            <div className="cb-overline">{s.label}</div>
            <div className="font-display font-black text-2xl mt-1 tracking-tight truncate">{s.value}</div>
            {s.sub && <div className="text-2xs text-muted-foreground font-bold uppercase tracking-wide mt-0.5">{s.sub}</div>}
            {s.link && <Link to={s.link} className="text-2xs font-bold text-accent hover:underline mt-1 inline-block">View →</Link>}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
