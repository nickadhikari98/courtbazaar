import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, formatINR } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import PageContainer from "@/components/layout/PageContainer";
import WidgetGrid from "@/components/dashboard/WidgetGrid";
import { homeWidgets, hearingNeedsMyAction, hearingNeedsMyDocument } from "@/config/homeWidgets";
import { CLOSED_HEARING_STATUSES, getHearingPermissions, humanizeHearingActivity } from "@/lib/hearingLifecycle";
import {
  Plus, Printer, FileText, Gavel, Stamp, Package, BookOpen, Sparkles, Truck, ArrowRight,
  Scale, Type, FileSignature, Briefcase, Wallet, CheckCircle2, Circle, Store, Banknote,
  BadgeCheck, Clock, Mic, Star, UploadCloud, ShieldCheck, AlertTriangle, XCircle, Info, Bell,
} from "lucide-react";
import { isFeatureEnabled } from "@/config/featureFlags";
import { listPublicServices } from "@/lib/servicesApi";
import { listHearingRequests } from "@/lib/hearingRequestsApi";
import { getPracticeProfile, listAvailabilitySlots } from "@/lib/practiceApi";
import { CAPABILITY_LABELS } from "@/components/shared/CapabilitiesCard";
import HearingDetailDialog from "@/components/shared/HearingDetailDialog";
import HearingProgressStepper from "@/components/shared/HearingProgressStepper";
import WorkspaceHero from "@/components/shared/WorkspaceHero";

const aiQuickAction = { id: "__ai_assistant", icon: Sparkles, label: "AI Assistant", price: "Ask anything", color: "bg-violet-50", iconColor: "text-violet-700" };

// Presentation-only overrides (curated label/price shorthand/color) for the
// quick-order tiles — same "which id, what surface" question as everywhere
// else: the *set and order* of ids comes from the backend
// (visibility.sidebar, court_seed.py), this map only decides how a known id
// is drawn. Anything visible.sidebar without an entry here still renders,
// using the catalog name/price and a generic icon (defensive default).
const QUICK_TILE_PRESENTATION = {
  svc_bw_photocopy: { icon: Printer, label: "B&W Photocopy", price: "₹1/pg", color: "bg-amber-50", iconColor: "text-amber-700" },
  svc_bw_print: { icon: Printer, label: "B&W Print", price: "₹2/pg", color: "bg-blue-50", iconColor: "text-blue-700" },
  svc_spiral_binding: { icon: BookOpen, label: "Spiral Binding", price: "₹40", color: "bg-emerald-50", iconColor: "text-emerald-700" },
  svc_hard_binding: { icon: Package, label: "Hard Binding", price: "₹250", color: "bg-rose-50", iconColor: "text-rose-700" },
  svc_efile_hc: { icon: Gavel, label: "High Court Filing", price: "₹900", color: "bg-purple-50", iconColor: "text-purple-700" },
  svc_efile_district: { icon: Scale, label: "District Filing", price: "₹500", color: "bg-cyan-50", iconColor: "text-cyan-700" },
  svc_notary_doc: { icon: Stamp, label: "Notarization", price: "₹100", color: "bg-yellow-50", iconColor: "text-yellow-700" },
  svc_typing_petition: { icon: Type, label: "Petition Typing", price: "₹15/pg", color: "bg-orange-50", iconColor: "text-orange-700" },
  svc_court_bundle: { icon: FileText, label: "Court Bundle", price: "₹500", color: "bg-indigo-50", iconColor: "text-indigo-700" },
  svc_court_runner: { icon: Truck, label: "Court Runner", price: "₹500", color: "bg-teal-50", iconColor: "text-teal-700" },
  svc_affidavit_draft: { icon: FileSignature, label: "Affidavit", price: "₹300", color: "bg-pink-50", iconColor: "text-pink-700" },
  svc_ocr: { icon: Sparkles, label: "OCR + AI", price: "₹5/pg", color: "bg-violet-50", iconColor: "text-violet-700" },
};

// Notification Center — three priority groups. Only the icon tint carries
// the group in the compact dashboard card (no section headers/text badge —
// there's no vertical budget for one at 60-70px/card), but the same groups
// still drive sort order (Action Required surfaces first) and are reused
// as-is by the full /notifications page.
const NOTIFICATION_GROUP_META = {
  action: { label: "Action Required", order: 0, iconWrap: "bg-red-100 text-red-700" },
  activity: { label: "Recent Activity", order: 1, iconWrap: "bg-blue-100 text-blue-700" },
  info: { label: "Information", order: 2, iconWrap: "bg-slate-100 text-slate-600" },
};

// Every real backend-emitted hearing-lifecycle title (see server.py's
// _notify_hearing_event call sites) mapped to how it should render here —
// event_type on notification_events is generically "hearing_event" for all
// of these, so the title text itself (stable, one call site each) is the
// only reliable classifier.
const HEARING_EVENT_META = {
  "New hearing request": { group: "action", icon: Gavel },
  "New offer": { group: "action", icon: Gavel },
  "Counter offer": { group: "action", icon: Gavel },
  "Order sheet uploaded": { group: "action", icon: UploadCloud },
  "Order sheet reminder": { group: "action", icon: UploadCloud },
  "Resubmission requested": { group: "action", icon: UploadCloud },
  "Order sheet disputed": { group: "activity", icon: AlertTriangle },
  "Payment received": { group: "activity", icon: ShieldCheck },
  "Order sheet verified": { group: "activity", icon: ShieldCheck },
  "Payment successful": { group: "activity", icon: CheckCircle2 },
  "Offer accepted": { group: "activity", icon: CheckCircle2 },
  "Payout released": { group: "activity", icon: Banknote },
  "Escrow released": { group: "activity", icon: ShieldCheck },
  "Refund issued": { group: "activity", icon: Banknote },
  "Rating received": { group: "activity", icon: Star },
  "Hearing cancelled": { group: "activity", icon: XCircle },
  "Request accepted": { group: "info", icon: CheckCircle2 },
  "Request declined": { group: "info", icon: XCircle },
  "Negotiation ended": { group: "info", icon: Info },
  "Dispute resolved — no payout": { group: "info", icon: Info },
};

// Classifies a raw /notifications feed row (order/settlement/hearing events
// all share this one collection) into {group, icon}. Falls back to a
// generic "Information" card for anything not explicitly mapped, so a
// future event type never disappears — it just renders unstyled until
// someone adds it above.
function classifyNotification(n) {
  if (n.event_type === "hearing_event" && HEARING_EVENT_META[n.title]) return HEARING_EVENT_META[n.title];
  if (n.event_type === "settlement_paid") return { group: "activity", icon: Banknote };
  if (n.event_type === "settlement_queued") return { group: "activity", icon: Clock };
  if (n.event_type === "settlement_failed") return { group: "action", icon: AlertTriangle };
  if (n.event_type === "order_placed") return { group: "info", icon: Package };
  if (n.event_type === "order_status") {
    const label = (n.title || "").toLowerCase();
    if (label.includes("complet") || label.includes("deliver")) return { group: "activity", icon: CheckCircle2 };
    return { group: "info", icon: Package };
  }
  return { group: "info", icon: Bell };
}

// This widget's own "not worth showing as upcoming" set, not a generic
// lifecycle concept — genuinely broader than lib/hearingLifecycle.js's
// CLOSED_HEARING_STATUSES: a "disputed" hearing's court date has already
// passed (it's stuck in post-hearing order-sheet review, not a future
// commitment) and "rated" is the terminal relabel of "completed", so both
// are excluded here for reasons specific to an *upcoming*-hearings list,
// not because either is "closed" in the NegotiationModule.jsx sense.
const UPCOMING_HEARINGS_EXCLUDED_STATUSES = [...CLOSED_HEARING_STATUSES, "disputed", "rated"];

function timeAgo(iso) {
  if (!iso) return "";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export default function Dashboard() {
  const { user, hasCapability } = useAuth();
  const navigate = useNavigate();
  const [orders, setOrders] = useState([]);
  const [hearings, setHearings] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [practiceProfile, setPracticeProfile] = useState(null);
  const [availabilitySlots, setAvailabilitySlots] = useState(null);
  const [loading, setLoading] = useState(true);
  const [quickServices, setQuickServices] = useState([]);
  const [activeHearingId, setActiveHearingId] = useState(null);

  const canPracticeProxyCounsel = hasCapability("can_practice_proxy_counsel");
  const canHireProxyCounsel = hasCapability("can_hire_proxy_counsel");

  useEffect(() => {
    listPublicServices("sidebar")
      .then((services) => setQuickServices(services.map((s) => {
        const presentation = QUICK_TILE_PRESENTATION[s.service_id];
        return {
          id: s.service_id,
          icon: presentation?.icon || FileText,
          label: presentation?.label || s.name,
          price: presentation?.price || `₹${s.base_price}`,
          color: presentation?.color || "bg-slate-50",
          iconColor: presentation?.iconColor || "text-slate-700",
        };
      })))
      .catch(() => setQuickServices([]));
  }, []);

  // Single fetch per data source, shared by every section below — Today's
  // Priorities, Upcoming Hearings, Pending Actions, and Recent Activity all
  // read the same `orders`/`hearings`/`notifications` state rather than each
  // re-fetching it.
  useEffect(() => {
    Promise.all([
      api.get("/orders"),
      listHearingRequests().catch(() => []),
      api.get("/notifications").catch(() => ({ data: [] })),
    ]).then(([ordersRes, hearingsRes, notifRes]) => {
      setOrders(ordersRes.data || []);
      setHearings(hearingsRes || []);
      setNotifications(notifRes.data || []);
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!canPracticeProxyCounsel) return;
    getPracticeProfile().then(setPracticeProfile).catch(() => {});
    listAvailabilitySlots().then(setAvailabilitySlots).catch(() => setAvailabilitySlots([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canPracticeProxyCounsel]);

  const active = useMemo(() => orders.filter((o) => !["completed", "delivered", "cancelled"].includes(o.status)), [orders]);
  const unreadNotifications = useMemo(() => notifications.filter((n) => !n.read_at), [notifications]);
  const myActionHearings = useMemo(() => hearings.filter((h) => hearingNeedsMyAction(h, user)), [hearings, user]);
  const myDocumentHearings = useMemo(() => hearings.filter((h) => hearingNeedsMyDocument(h, user?.user_id)), [hearings, user]);

  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const hearingsToday = useMemo(() => hearings.filter((h) => h.hearing_date === today), [hearings, today]);

  const upcomingHearings = useMemo(() => hearings
    .filter((h) => h.hearing_date >= today && !UPCOMING_HEARINGS_EXCLUDED_STATUSES.includes(h.status))
    .sort((a, b) => a.hearing_date.localeCompare(b.hearing_date))
    .slice(0, 5), [hearings, today]);

  const greeting = useMemo(() => {
    const hr = new Date().getHours();
    return hr < 12 ? "Good Morning" : hr < 17 ? "Good Afternoon" : "Good Evening";
  }, []);

  const capabilityBadges = (user?.capabilities || []).map((c) => CAPABILITY_LABELS[c]).filter(Boolean);
  const walletHeld = user?.wallet_held_balance || 0;

  // Contextual "next step" — a single suggested action, not a replacement
  // for the static Quick Actions grid below. First matching rule wins.
  const suggestion = useMemo(() => {
    if (canPracticeProxyCounsel && practiceProfile && !practiceProfile.practice_areas?.length) {
      return { label: "Complete Practice Profile", detail: "Add your practice areas so requests can find you.", to: "/practice", icon: Briefcase };
    }
    if (canPracticeProxyCounsel && Array.isArray(availabilitySlots) && availabilitySlots.length === 0) {
      return { label: "Add Availability", detail: "Let clients know when you're free to appear.", to: "/practice", icon: Clock };
    }
    if (myDocumentHearings.length > 0) {
      const h = myDocumentHearings[0];
      const { isRequester } = getHearingPermissions(h, user);
      return {
        label: isRequester ? "Upload Case Documents" : "Upload Order Sheet",
        detail: `${h.court_id} is waiting on a document from you.`,
        onClick: () => setActiveHearingId(h.hearing_id), icon: FileText,
      };
    }
    if (walletHeld > 0 && canPracticeProxyCounsel) {
      return { label: "Withdraw Earnings", detail: `${formatINR(walletHeld)} held — check your payout status.`, to: "/earnings", icon: Banknote };
    }
    return { label: "Explore Marketplace", detail: "Browse services you can order in under 30 seconds.", to: "/marketplace", icon: Store };
  }, [canPracticeProxyCounsel, practiceProfile, availabilitySlots, myDocumentHearings, walletHeld, user]);

  // Notification Center — merges two sources into one {group, icon, title,
  // description, at, cta} shape: (1) live hearing *state* that needs action
  // right now (upload/pay/accept/mark-conducted — there's no one-time event
  // for "still pending", it just is), and (2) the real notification_events
  // feed (server.py's _notify_hearing_event / record_notification_event call
  // sites), which already carries production-accurate titles/bodies/
  // timestamps per event — see classifyNotification/HEARING_EVENT_META
  // above. No client-side guessing of "what happened" once the feed has it.
  const notificationItems = useMemo(() => {
    const items = [];
    const documentHearingIds = new Set(myDocumentHearings.map((h) => h.hearing_id));

    myDocumentHearings.forEach((h) => {
      const { isRequester } = getHearingPermissions(h, user);
      items.push({
        key: `doc-${h.hearing_id}`, group: "action", icon: UploadCloud,
        title: isRequester ? "Case Documents Needed" : "Order Sheet Needed",
        description: `${h.court_id} is waiting on ${isRequester ? "a case document" : "the Court Order Sheet"} from you.`,
        at: h.updated_at || h.created_at,
        cta: { label: isRequester ? "Upload Documents" : "Upload Order Sheet", onClick: () => setActiveHearingId(h.hearing_id) },
      });
    });
    myActionHearings.forEach((h) => {
      if (documentHearingIds.has(h.hearing_id)) return;
      const { canPay, canMarkConducted } = getHearingPermissions(h, user);
      items.push({
        key: `act-${h.hearing_id}`, group: "action", icon: canPay ? Wallet : canMarkConducted ? Gavel : Sparkles,
        title: canPay ? "Payment Required" : canMarkConducted ? "Mark Hearing Conducted" : "New Hearing Offer",
        description: `${h.court_id}${h.fee ? ` · ${formatINR(h.fee)}` : ""}`,
        at: h.updated_at || h.created_at,
        cta: { label: canPay ? "Pay Now" : canMarkConducted ? "Mark Conducted" : "Review Offer", onClick: () => setActiveHearingId(h.hearing_id) },
      });
    });
    if (canPracticeProxyCounsel && walletHeld > 0) {
      items.push({
        key: "payout-waiting", group: "activity", icon: Clock,
        title: "Payout Pending", description: `${formatINR(walletHeld)} held — awaiting release.`,
        at: null, cta: { label: "View Earnings", to: "/earnings" },
      });
    }
    notifications.forEach((n) => {
      const meta = classifyNotification(n);
      const target = n.related_entity_type === "hearing" && n.related_entity_id
        ? (n.title === "New hearing request"
          ? { onClick: () => navigate(`/hearing-requests/${n.related_entity_id}/negotiate`) }
          : { onClick: () => setActiveHearingId(n.related_entity_id) })
        : n.related_entity_type === "order" && n.related_entity_id
          ? { to: `/orders/${n.related_entity_id}` }
          : n.event_type?.startsWith("settlement") ? { to: "/earnings" } : { to: "/notifications" };
      items.push({
        key: `notif-${n.notification_id}`, group: meta.group, icon: meta.icon,
        title: n.title, description: n.body, at: n.created_at, unread: !n.read_at,
        cta: { label: "View", ...target },
      });
    });

    return items.sort((a, b) => new Date(b.at || 0) - new Date(a.at || 0));
  }, [myDocumentHearings, myActionHearings, notifications, canPracticeProxyCounsel, walletHeld, user, navigate]);

  // Dashboard widget only ever shows the top 4 — Action Required bubbles
  // above Recent Activity/Information (stable sort keeps each tier's own
  // newest-first order from notificationItems above), full history lives on
  // /notifications behind "View All Notifications".
  const dashboardNotifications = useMemo(() => (
    [...notificationItems]
      .sort((a, b) => (NOTIFICATION_GROUP_META[a.group].order === 0 ? 0 : 1) - (NOTIFICATION_GROUP_META[b.group].order === 0 ? 0 : 1))
      .slice(0, 4)
  ), [notificationItems]);

  // Today's Progress — reuses the shadcn Progress bar, not a new stat type.
  const todayChecklist = useMemo(() => {
    const items = [];
    hearingsToday.forEach((h) => items.push({
      label: `${h.court_id} — hearing today`,
      done: ["hearing_completed", "verification_pending", "verified", "completed", "rated"].includes(h.status),
    }));
    myDocumentHearings.forEach((h) => items.push({
      label: `${getHearingPermissions(h, user).isRequester ? "Upload case documents" : "Upload order sheet"} — ${h.court_id}`,
      done: false,
    }));
    myActionHearings.forEach((h) => {
      if (myDocumentHearings.some((d) => d.hearing_id === h.hearing_id)) return;
      items.push({ label: `Respond — ${h.court_id}`, done: false });
    });
    return items;
  }, [hearingsToday, myDocumentHearings, myActionHearings, user]);
  const todayDone = todayChecklist.filter((i) => i.done).length;

  // Recent Activity — orders + every hearing's own timeline + notifications,
  // merged and sorted client-side, newest first. No new backend endpoint.
  // Hearing timeline entries go through humanizeHearingActivity so this
  // reads as a timeline of business events (Payment Successful, Hearing
  // Scheduled, ...) — never the raw "<from_status> -> <to_status>" string
  // hearings.py's state machine writes to timeline[].note. Those raw
  // transitions stay admin-only (see HearingTimeline's mode="raw" in
  // AdminHearingVerification.jsx).
  const recentActivity = useMemo(() => {
    const items = [];
    orders.forEach((o) => {
      const statusLabel = (o.status || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
      items.push({
        key: `order-${o.order_id}`, at: o.updated_at || o.created_at, icon: Package,
        title: `Order ${statusLabel}`, description: `Order ${o.order_id}`,
        to: `/orders/${o.order_id}`,
      });
    });
    hearings.forEach((h) => (h.timeline || []).forEach((t, i) => {
      const { icon, title, description } = humanizeHearingActivity(t, h);
      items.push({
        key: `hearing-${h.hearing_id}-${i}`, at: t.at, icon, title, description,
        onClick: () => setActiveHearingId(h.hearing_id),
      });
    }));
    notifications.forEach((n) => items.push({
      key: `notif-${n.notification_id}`, at: n.created_at, icon: classifyNotification(n).icon,
      title: n.title, description: n.body, to: "/notifications",
    }));
    return items.filter((i) => i.at).sort((a, b) => new Date(b.at) - new Date(a.at)).slice(0, 12);
  }, [orders, hearings, notifications]);

  const advocateOwnedHearings = hearings.filter((h) => getHearingPermissions(h, user).isAssignedProxyCounsel).length;

  return (
    <PageContainer>
      {/* Hero — greeting, dual identity, today's summary, two intent-based CTA groups */}
      <WorkspaceHero
        data-testid="dashboard-hero"
        eyebrow={greeting}
        title={user?.name || "Advocate"}
        badges={(
          <>
            <Badge className="bg-white/15 text-white border-0 font-bold">Advocate</Badge>
            {user?.bar_council_id && (
              <Badge className="bg-white/15 text-white border-0 font-semibold gap-1" data-testid="bar-council-chip">
                <BadgeCheck className="w-3 h-3" /> Bar Council ID on file
              </Badge>
            )}
            {capabilityBadges.map((label) => (
              <Badge key={label} variant="outline" className="border-white/30 text-white font-semibold" data-testid={`hero-capability-${label.toLowerCase().replace(/\s+/g, '-')}`}>
                ✓ {label}
              </Badge>
            ))}
          </>
        )}
        summary={!loading ? [
          hearingsToday.length > 0 && `${hearingsToday.length} hearing${hearingsToday.length > 1 ? "s" : ""} today`,
          myDocumentHearings.length > 0 && `${myDocumentHearings.length} document${myDocumentHearings.length > 1 ? "s" : ""} pending`,
          walletHeld > 0 && `${formatINR(walletHeld)} awaiting release`,
          unreadNotifications.length > 0 && `${unreadNotifications.length} unread notification${unreadNotifications.length > 1 ? "s" : ""}`,
        ].filter(Boolean) : []}
        actions={(
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <div className="text-sm font-bold text-white/70 mb-2">Need legal services today?</div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => navigate("/marketplace")} className="bg-white/15 hover:bg-white/25 text-white font-bold border border-white/20" data-testid="hero-cta-marketplace">
                  <Store className="w-4 h-4 mr-1.5" /> Marketplace
                </Button>
                <Button onClick={() => navigate("/order/new")} className="bg-accent hover:bg-accent/90 font-bold" data-testid="hero-cta-new-order">
                  <Plus className="w-4 h-4 mr-1.5" /> New Order
                </Button>
              </div>
            </div>
            <div>
              <div className="text-sm font-bold text-white/70 mb-2">Want to earn today?</div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => navigate(canPracticeProxyCounsel ? "/practice" : "/hire-proxy-counsel")}
                        className="bg-white/15 hover:bg-white/25 text-white font-bold border border-white/20" data-testid="hero-cta-open-requests">
                  <Gavel className="w-4 h-4 mr-1.5" /> {canPracticeProxyCounsel ? "Open Hearing Requests" : "Hire Proxy Counsel"}
                </Button>
                {canPracticeProxyCounsel && (
                  <Button onClick={() => navigate("/practice")} variant="outline" className="border-white/30 text-white hover:bg-white/10 font-bold" data-testid="hero-cta-my-practice">
                    <Briefcase className="w-4 h-4 mr-1.5" /> My Practice
                  </Button>
                )}
              </div>
            </div>
          </div>
        )}
      />

      {/* Today's Priorities — action counts, not lifetime stats (registry-driven, config/homeWidgets.js) */}
      <div className="mb-2">
        <div className="cb-overline text-accent">Today's Priorities</div>
      </div>
      <WidgetGrid widgets={homeWidgets} context={{ user, orders, hearings }} />

      {/* Contextual next step — one suggestion, highest priority first */}
      <Card className="bento-card border-none mb-8 bg-accent/5" data-testid="suggested-next-step">
        <CardContent className="p-5 flex items-center gap-4">
          <div className="w-11 h-11 rounded-xl bg-accent/15 flex items-center justify-center flex-shrink-0">
            <suggestion.icon className="w-5 h-5 text-accent" strokeWidth={2} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="cb-overline text-accent">Suggested next step</div>
            <div className="font-display font-bold">{suggestion.label}</div>
            <p className="text-sm text-muted-foreground">{suggestion.detail}</p>
          </div>
          <Button onClick={() => suggestion.onClick ? suggestion.onClick() : navigate(suggestion.to)} className="bg-accent hover:bg-accent/90 font-bold flex-shrink-0">
            Go <ArrowRight className="w-4 h-4 ml-1.5" />
          </Button>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6 mb-8">
        {/* Upcoming Hearings — the primary column; the sidebar next to it is
            a fixed ~360px so it can't crowd this out on wide screens. */}
        <div className="min-w-0">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display font-bold text-2xl tracking-tight">Upcoming Hearings</h2>
            {canHireProxyCounsel && (
              <Link to="/hire-proxy-counsel" className="text-sm font-bold text-accent hover:underline" data-testid="dash-view-hearings">All hearings →</Link>
            )}
          </div>
          {loading ? (
            <div className="space-y-3">{[1, 2].map((i) => <div key={i} className="h-28 shimmer rounded-xl"></div>)}</div>
          ) : upcomingHearings.length === 0 ? (
            <Card className="border-dashed border-2" data-testid="empty-upcoming-hearings">
              <CardContent className="p-10 text-center">
                <Gavel className="w-12 h-12 mx-auto text-muted-foreground mb-3" strokeWidth={1.5} />
                <div className="font-display font-bold text-lg">You don't have any hearings scheduled.</div>
                {canHireProxyCounsel && (
                  <>
                    <p className="text-sm text-muted-foreground mt-1">Send a request and any available Proxy Counsel can accept it.</p>
                    <Button onClick={() => navigate("/hire-proxy-counsel")} className="mt-4 bg-accent hover:bg-accent/90 font-bold">
                      <Plus className="w-4 h-4 mr-2" /> Browse Hearing Requests
                    </Button>
                  </>
                )}
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {upcomingHearings.map((h) => {
                const isToday = h.hearing_date === today;
                const { isRequester: isMine, negotiationRequired, negotiationAgreed } = getHearingPermissions(h, user);
                const isMyDoc = myDocumentHearings.some((d) => d.hearing_id === h.hearing_id);
                const isMyAction = myActionHearings.some((d) => d.hearing_id === h.hearing_id);
                const actionLabel = isMyDoc ? (isMine ? "Upload Documents" : "Upload Order Sheet")
                  : isMyAction ? (isMine ? "Pay Now" : h.status === "broadcast" ? "Accept" : "Mark Conducted")
                  : "Open Hearing";
                return (
                  <Card key={h.hearing_id} className="dashboard-card border-none hover:shadow-md transition-all cursor-pointer" onClick={() => setActiveHearingId(h.hearing_id)} data-testid={`upcoming-hearing-${h.hearing_id}`}>
                    <CardContent className="p-5">
                      <div className="flex items-start justify-between gap-4 mb-3">
                        <div className="min-w-0">
                          <div className="font-display font-bold text-lg truncate">{h.court_id}</div>
                          <div className="text-sm text-muted-foreground font-medium mt-0.5">
                            {isToday ? "Today" : h.hearing_date}{h.fee ? ` · ${formatINR(h.fee)}` : ""}
                          </div>
                        </div>
                        <Button size="sm" onClick={(e) => { e.stopPropagation(); setActiveHearingId(h.hearing_id); }} className="bg-accent hover:bg-accent/90 font-bold flex-shrink-0">
                          {actionLabel}
                        </Button>
                      </div>
                      <HearingProgressStepper status={h.status} compact negotiationAgreed={!negotiationRequired || negotiationAgreed} targeted={negotiationRequired} />
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </div>

        {/* Notifications — compact SaaS-style sidebar widget (Linear/Stripe/
            GitHub-ish): fixed ~60-70px rows, top 4 only, full history is one
            click away on /notifications. Group (Action Required > Recent
            Activity > Information) decides sort + icon tint, not a section
            header — there's no vertical room for one at this row height. */}
        <div className="w-full lg:w-[360px] flex-shrink-0">
          <div className="bg-white border border-border rounded-2xl p-3">
            <div className="flex items-center justify-between px-1 pb-2">
              <h2 className="font-display font-bold text-base tracking-tight">Notifications</h2>
              {unreadNotifications.length > 0 && (
                <Badge className="bg-accent/10 text-accent border-0 text-2xs font-bold h-5 px-2">{unreadNotifications.length} new</Badge>
              )}
            </div>
            {loading ? (
              <div className="space-y-1.5">{[1, 2, 3, 4].map((i) => <div key={i} className="h-16 shimmer rounded-lg"></div>)}</div>
            ) : dashboardNotifications.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground" data-testid="empty-pending-actions">
                You're all caught up.
              </div>
            ) : (
              <div className="divide-y divide-border/60">
                {dashboardNotifications.map((n) => {
                  const meta = NOTIFICATION_GROUP_META[n.group];
                  return (
                    <div key={n.key} className="flex items-center gap-2.5 py-2.5 px-1" data-testid={`notification-${n.key}`}>
                      <div className={`relative w-8 h-8 rounded-full ${meta.iconWrap} flex items-center justify-center flex-shrink-0`}>
                        <n.icon className="w-4 h-4" strokeWidth={2} />
                        {n.unread && <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-accent ring-2 ring-white" aria-hidden="true" />}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-bold truncate">{n.title}</span>
                          <span className="text-2xs text-muted-foreground/70 font-semibold flex-shrink-0">{n.at ? timeAgo(n.at) : ""}</span>
                        </div>
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs text-muted-foreground truncate">{n.description}</span>
                          {n.cta && (
                            <button
                              onClick={() => n.cta.onClick ? n.cta.onClick() : navigate(n.cta.to)}
                              title={n.cta.label}
                              aria-label={n.cta.label}
                              className="text-xs font-bold text-accent hover:underline flex-shrink-0"
                              data-testid={`notification-cta-${n.key}`}
                            >
                              View →
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            <Link
              to="/notifications"
              className="mt-2 flex items-center justify-center text-xs font-bold text-accent hover:underline py-2 border-t border-border/60"
              data-testid="dash-view-all-notifications"
            >
              View All Notifications →
            </Link>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="cb-overline text-accent">Quick Actions</div>
            <h2 className="font-display font-bold text-2xl mt-1 tracking-tight">Tap to start</h2>
          </div>
          <Link to="/marketplace" className="text-sm font-bold text-accent hover:underline" data-testid="dash-view-all-services">View all services →</Link>
        </div>
        <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-3">
          {quickServices.map((s) => (
            <button
              key={s.id}
              onClick={() => navigate(`/order/new?service=${s.id}`)}
              className="bento-card p-4 text-left group"
              data-testid={`quick-service-${s.id}`}
            >
              <div className={`w-11 h-11 rounded-xl ${s.color} flex items-center justify-center mb-3 group-hover:scale-105 transition-transform`}>
                <s.icon className={`w-5 h-5 ${s.iconColor}`} strokeWidth={2} />
              </div>
              <div className="font-display font-bold text-sm leading-tight">{s.label}</div>
              <div className="text-xs text-muted-foreground font-semibold mt-1">{s.price}</div>
            </button>
          ))}
          {isFeatureEnabled("quickActions.aiAssistant") && (
            <button
              onClick={() => navigate("/ai")}
              className="bento-card p-4 text-left group"
              data-testid="quick-service-ai-assistant"
            >
              <div className={`w-11 h-11 rounded-xl ${aiQuickAction.color} flex items-center justify-center mb-3 group-hover:scale-105 transition-transform`}>
                <aiQuickAction.icon className={`w-5 h-5 ${aiQuickAction.iconColor}`} strokeWidth={2} />
              </div>
              <div className="font-display font-bold text-sm leading-tight">{aiQuickAction.label}</div>
              <div className="text-xs text-muted-foreground font-semibold mt-1">{aiQuickAction.price}</div>
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Get Work Done / Grow Your Practice */}
        <div className="lg:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-6">
          <div>
            <h2 className="font-display font-bold text-xl tracking-tight mb-3">Get Work Done</h2>
            <div className="space-y-2">
              <Link to="/marketplace" className="bento-card p-3.5 flex items-center gap-2.5" data-testid="workdone-marketplace">
                <Store className="w-4 h-4 text-accent flex-shrink-0" /> <span className="text-sm font-semibold">Marketplace</span>
              </Link>
              <Link to="/order/new" className="bento-card p-3.5 flex items-center gap-2.5" data-testid="workdone-new-order">
                <Plus className="w-4 h-4 text-accent flex-shrink-0" /> <span className="text-sm font-semibold">New Order (Printing, Scanning, E-Filing)</span>
              </Link>
              {canHireProxyCounsel && (
                <Link to="/hire-proxy-counsel" className="bento-card p-3.5 flex items-center gap-2.5" data-testid="workdone-hire-proxy-counsel">
                  <Gavel className="w-4 h-4 text-accent flex-shrink-0" /> <span className="text-sm font-semibold">Hire Proxy Counsel</span>
                </Link>
              )}
              <Link to="/stenographer" className="bento-card p-3.5 flex items-center gap-2.5" data-testid="workdone-stenographer">
                <Mic className="w-4 h-4 text-accent flex-shrink-0" /> <span className="text-sm font-semibold">Stenographer</span>
              </Link>
            </div>
          </div>
          <div>
            <h2 className="font-display font-bold text-xl tracking-tight mb-3">Grow Your Practice</h2>
            {canPracticeProxyCounsel ? (
              <>
                <div className="space-y-2">
                  <Link to="/practice" className="bento-card p-3.5 flex items-center gap-2.5" data-testid="grow-proxy-requests">
                    <Gavel className="w-4 h-4 text-accent flex-shrink-0" /> <span className="text-sm font-semibold">Proxy Counsel Requests</span>
                  </Link>
                  <Link to="/practice" className="bento-card p-3.5 flex items-center gap-2.5" data-testid="grow-my-practice">
                    <Briefcase className="w-4 h-4 text-accent flex-shrink-0" /> <span className="text-sm font-semibold">My Practice</span>
                  </Link>
                  <Link to="/earnings" className="bento-card p-3.5 flex items-center gap-2.5" data-testid="grow-earnings">
                    <Wallet className="w-4 h-4 text-accent flex-shrink-0" /> <span className="text-sm font-semibold">Earnings</span>
                  </Link>
                  <Link to="/practice" className="bento-card p-3.5 flex items-center gap-2.5" data-testid="grow-ratings">
                    <Star className="w-4 h-4 text-accent flex-shrink-0" /> <span className="text-sm font-semibold">Ratings &amp; Visibility</span>
                  </Link>
                  {/* Not real backend capabilities today (server.py's ROLE_CAPABILITIES)
                      — shown disabled so the founder's intended shape is visible without
                      faking functionality. See plan §2. */}
                  <div className="bento-card p-3.5 flex items-center gap-2.5 opacity-50 cursor-not-allowed" data-testid="grow-efiling-work">
                    <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" /> <span className="text-sm font-semibold flex-1">E-Filing Work</span>
                    <Badge variant="outline" className="text-2xs">Coming soon</Badge>
                  </div>
                  <div className="bento-card p-3.5 flex items-center gap-2.5 opacity-50 cursor-not-allowed" data-testid="grow-stenographer-assignments">
                    <Mic className="w-4 h-4 text-muted-foreground flex-shrink-0" /> <span className="text-sm font-semibold flex-1">Stenographer Assignments</span>
                    <Badge variant="outline" className="text-2xs">Coming soon</Badge>
                  </div>
                </div>
                {advocateOwnedHearings === 0 && (
                  <p className="text-xs text-muted-foreground mt-2">Start accepting proxy counsel requests to earn.</p>
                )}
              </>
            ) : (
              <Card className="border-dashed border-2">
                <CardContent className="p-5 text-sm text-muted-foreground">
                  Enable Proxy Counsel practice from <Link to="/practice" className="text-accent font-bold hover:underline">My Practice</Link> to start earning through CourtBazaar.
                </CardContent>
              </Card>
            )}
          </div>
        </div>

        {/* Today's Progress — reuses the shadcn Progress bar, not a new stat */}
        <div>
          <h2 className="font-display font-bold text-xl tracking-tight mb-3">Today's Progress</h2>
          <Card className="dashboard-card" data-testid="todays-progress-card">
            <CardContent className="p-5">
              {todayChecklist.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nothing on your plate today. Enjoy the quiet.</p>
              ) : (
                <>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-bold">{todayDone} of {todayChecklist.length} done</span>
                  </div>
                  <Progress value={(todayDone / todayChecklist.length) * 100} className="h-2 mb-3" />
                  <div className="space-y-1.5">
                    {todayChecklist.map((item, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm">
                        {item.done ? <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" /> : <Circle className="w-4 h-4 text-muted-foreground flex-shrink-0" />}
                        <span className={item.done ? "text-muted-foreground line-through" : "font-medium"}>{item.label}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Recent Activity — orders + hearing timelines + notifications, merged newest-first */}
      <div>
        <h2 className="font-display font-bold text-2xl tracking-tight mb-4">Recent Activity</h2>
        {loading ? (
          <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="h-12 shimmer rounded-xl"></div>)}</div>
        ) : recentActivity.length === 0 ? (
          <Card className="border-dashed border-2" data-testid="empty-recent-activity">
            <CardContent className="p-10 text-center">
              <Package className="w-12 h-12 mx-auto text-muted-foreground mb-3" strokeWidth={1.5} />
              <div className="font-display font-bold text-lg">Need legal services today?</div>
              <p className="text-sm text-muted-foreground mt-1">Place your first order — it takes 30 seconds.</p>
              <Button onClick={() => navigate("/marketplace")} className="mt-4 bg-accent hover:bg-accent/90 font-bold" data-testid="dash-empty-activity-marketplace">
                <Store className="w-4 h-4 mr-2" /> Marketplace
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-1">
            {recentActivity.map((item) => (
              <button
                key={item.key}
                onClick={() => item.onClick ? item.onClick() : navigate(item.to)}
                className="w-full text-left flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-secondary/60 transition-colors"
                data-testid={`activity-${item.key}`}
              >
                <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center flex-shrink-0">
                  <item.icon className="w-4 h-4 text-muted-foreground" strokeWidth={2} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-bold truncate">{item.title}</span>
                    <span className="text-2xs text-muted-foreground font-semibold flex-shrink-0">{timeAgo(item.at)}</span>
                  </div>
                  {item.description && <p className="text-xs text-muted-foreground truncate">{item.description}</p>}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      <HearingDetailDialog
        hearingId={activeHearingId}
        open={!!activeHearingId}
        onOpenChange={(v) => !v && setActiveHearingId(null)}
        onChanged={() => listHearingRequests().then(setHearings).catch(() => {})}
      />
    </PageContainer>
  );
}
