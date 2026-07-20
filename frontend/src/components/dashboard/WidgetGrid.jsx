import React from "react";
import StatGrid from "@/components/shared/StatGrid";

/* Registry evaluator for a home-widget registry (see config/homeWidgets.js)
   — filters by appliesTo(context), computes each surviving entry's stat
   shape, and hands the resulting array to StatGrid (components/shared) for
   the actual rendering. This keeps the stat-tile markup itself in exactly
   one place, shared with Practice/Earnings/Admin's plain (non-registry)
   stat rows — WidgetGrid only owns the conditional-widget-selection layer
   Dashboard specifically needs. */
export default function WidgetGrid({ widgets, context }) {
  const stats = widgets.filter((w) => w.appliesTo(context)).map((w) => w.compute(context));
  return <StatGrid stats={stats} columns="grid-cols-2 lg:grid-cols-4" className="mb-8" testIdPrefix="dash-stat" />;
}
