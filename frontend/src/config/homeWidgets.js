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

/* Shared predicate — also used by Dashboard.jsx's Pending Actions list and
   its contextual "next step" suggestion, so all three surfaces agree on what
   "a document is pending from me" means for a given hearing. */
export function hearingNeedsMyDocument(h, userId) {
  return (h.requesting_user_id === userId && h.status === "documents_shared")
    || (h.proxy_counsel_user_id === userId && h.status === "hearing_completed");
}

/* Broadcast (or targeted-at-me) requests I'm eligible to accept — mirrors
   HearingDetailDialog.jsx's `isEligibleAdvocate` gating. */
export function hearingIsAcceptableByMe(h, user) {
  if (!user?.capabilities?.includes("can_practice_proxy_counsel")) return false;
  if (h.requesting_user_id === user.user_id || h.proxy_counsel_user_id === user.user_id) return false;
  return h.status === "broadcast" && (!h.target_advocate_id || h.target_advocate_id === user.user_id);
}

export function hearingNeedsMyAction(h, user) {
  // M6 reorder: payment is now due at "requested", before broadcast/acceptance.
  return (h.requesting_user_id === user?.user_id && h.status === "requested") // payment due
    || (h.proxy_counsel_user_id === user?.user_id && h.status === "hearing_scheduled") // mark conducted due
    || hearingIsAcceptableByMe(h, user);
}

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
