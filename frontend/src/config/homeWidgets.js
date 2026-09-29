/* Home widget registry — each entry declares whether it applies to the
   current dashboard context and how to render itself, so Home (Dashboard.jsx)
   never hardcodes which cards to show. A future profile type / capability
   adds an entry here; it never requires editing the page that renders them.

   `appliesTo(ctx)` decides visibility; `compute(ctx)` returns the card's
   {label, value, icon, color} given the shared context,
   { user, orders, hearings } — the same data Dashboard.jsx already fetches
   for itself (hearings via listHearingRequests(), added for the Advocate
   Workspace redesign).

   These are the "Today's Priorities" tiles — deliberately action-count-
   shaped (what's outstanding right now), not lifetime/historical stats.
   Lifetime totals (total spent, total completed, lifetime earnings) live on
   Orders.jsx/Earnings.jsx instead — Home stays work-first, not a stat wall. */
import { Clock, FileText, Gavel, Banknote } from "lucide-react";
import { formatINR } from "@/lib/api";

// Production-hardening pass: these four predicates moved to
// lib/hearingLifecycle.js, the one shared resolver every hearing-showing
// screen now uses (NegotiationModule/HearingDetailDialog/Dashboard/Practice/
// HireProxyCounsel) — re-exported here so this file's existing callers
// (Dashboard.jsx) don't need an import-path change.
import {
  hearingNeedsMyDocument, hearingIsAcceptableByMe, hearingCommerciallyReadyForPayment, hearingNeedsMyAction,
} from "@/lib/hearingLifecycle";

export { hearingNeedsMyDocument, hearingIsAcceptableByMe, hearingCommerciallyReadyForPayment, hearingNeedsMyAction };

export const homeWidgets = [
  {
    id: "active-orders",
    appliesTo: () => true,
    compute: ({ orders }) => ({
      label: "Active Orders",
      value: orders.filter((o) => !["completed", "delivered", "cancelled"].includes(o.status)).length,
      icon: Clock,
      color: "bg-accent/10 text-accent",
    }),
  },
  {
    id: "hearings-needing-action",
    appliesTo: (ctx) => Array.isArray(ctx.hearings),
    compute: ({ hearings, user }) => ({
      label: "Hearings Needing Action",
      value: hearings.filter((h) => hearingNeedsMyAction(h, user)).length,
      icon: Gavel,
      color: "bg-amber-100 text-amber-700",
    }),
  },
  {
    id: "documents-pending",
    appliesTo: (ctx) => Array.isArray(ctx.hearings),
    compute: ({ hearings, user }) => ({
      label: "Documents Pending",
      value: hearings.filter((h) => hearingNeedsMyDocument(h, user?.user_id)).length,
      icon: FileText,
      color: "bg-blue-100 text-blue-700",
    }),
  },
  {
    id: "payouts-waiting",
    appliesTo: (ctx) => ctx.user?.capabilities?.includes("can_practice_proxy_counsel"),
    compute: ({ user }) => ({
      label: "Payouts Waiting",
      value: formatINR(user?.wallet_held_balance || 0),
      icon: Banknote,
      color: "bg-emerald-100 text-emerald-700",
    }),
  },
];
