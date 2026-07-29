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
import { homeWidgets, hearingNeedsMyAction, hearingNeedsMyDocument, hearingCommerciallyReadyForPayment } from "@/config/homeWidgets";
import {
  Plus, Printer, FileText, Gavel, Stamp, Package, BookOpen, Sparkles, Truck, ArrowRight,
  Scale, Type, FileSignature, Briefcase, Wallet, CheckCircle2, Circle, Store, Banknote,
  BadgeCheck, Clock, Mic, Star,
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

const PENDING_TIER_BADGE = {
  critical: "bg-amber-100 text-amber-700",
  info: "bg-blue-100 text-blue-700",
  success: "bg-emerald-100 text-emerald-700",
};
const PENDING_TIER_LABEL = { critical: "Action needed", info: "Waiting on CourtBazaar", success: "Done" };

const TERMINAL_HEARING_STATUSES = ["rejected", "cancelled", "disputed", "expired"];

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
    .filter((h) => h.hearing_date >= today && !TERMINAL_HEARING_STATUSES.includes(h.status) && h.status !== "rated")
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
      const isMine = h.requesting_user_id === user?.user_id;
      return {
        label: isMine ? "Upload Case Documents" : "Upload Order Sheet",
        detail: `${h.court_id} is waiting on a document from you.`,
        onClick: () => setActiveHearingId(h.hearing_id), icon: FileText,
      };
    }
    if (walletHeld > 0 && canPracticeProxyCounsel) {
      return { label: "Withdraw Earnings", detail: `${formatINR(walletHeld)} held — check your payout status.`, to: "/earnings", icon: Banknote };
    }
    return { label: "Explore Marketplace", detail: "Browse services you can order in under 30 seconds.", to: "/marketplace", icon: Store };
  }, [canPracticeProxyCounsel, practiceProfile, availabilitySlots, myDocumentHearings, walletHeld, user]);

  // Pending Actions — urgency-tiered (critical/info/success), reusing the
  // same Tailwind classes the codebase's own STATUS_BADGE dicts already use.
  const pendingActions = useMemo(() => {
    const items = [];
    const documentHearingIds = new Set(myDocumentHearings.map((h) => h.hearing_id));

    myDocumentHearings.forEach((h) => {
      const isMine = h.requesting_user_id === user?.user_id;
      items.push({
        tier: "critical", key: `doc-${h.hearing_id}`,
        label: `${isMine ? "Upload case documents" : "Upload order sheet"} — ${h.court_id}`,
        onClick: () => setActiveHearingId(h.hearing_id),
      });
    });
    myActionHearings.forEach((h) => {
      if (documentHearingIds.has(h.hearing_id)) return;
      // M6 reorder: payment is now due at "requested", before broadcast/acceptance.
      const isPaymentDue = h.requesting_user_id === user?.user_id && h.status === "requested"
        && hearingCommerciallyReadyForPayment(h);
      const isMarkConduct = h.proxy_counsel_user_id === user?.user_id && h.status === "hearing_scheduled";
      items.push({
        tier: "critical", key: `act-${h.hearing_id}`,
        label: `${isPaymentDue ? "Payment due" : isMarkConduct ? "Mark hearing conducted" : "New request to review"} — ${h.court_id}`,
        onClick: () => setActiveHearingId(h.hearing_id),
      });
    });
    hearings
      .filter((h) => h.status === "verification_pending" && (h.requesting_user_id === user?.user_id || h.proxy_counsel_user_id === user?.user_id))
      .forEach((h) => items.push({
        tier: "info", key: `verify-${h.hearing_id}`,
        label: `${h.court_id} — order sheet awaiting CourtBazaar verification`,
        onClick: () => setActiveHearingId(h.hearing_id),
      }));
    if (canPracticeProxyCounsel && walletHeld > 0) {
      items.push({ tier: "info", key: "payout-waiting", label: `${formatINR(walletHeld)} held — awaiting payout release`, to: "/earnings" });
    }
    unreadNotifications.slice(0, 3).forEach((n) => items.push({ tier: "info", key: `notif-${n.notification_id}`, label: n.title, to: "/notifications" }));
    hearings.filter((h) => h.status === "completed").slice(0, 2)
      .forEach((h) => items.push({ tier: "success", key: `done-${h.hearing_id}`, label: `Payout released — ${h.court_id}`, onClick: () => setActiveHearingId(h.hearing_id) }));
    return items;
  }, [myDocumentHearings, myActionHearings, hearings, unreadNotifications, canPracticeProxyCounsel, walletHeld, user]);

  // Today's Progress — reuses the shadcn Progress bar, not a new stat type.
  const todayChecklist = useMemo(() => {
    const items = [];
    hearingsToday.forEach((h) => items.push({
      label: `${h.court_id} — hearing today`,
      done: ["hearing_completed", "verification_pending", "verified", "completed", "rated"].includes(h.status),
    }));
    myDocumentHearings.forEach((h) => items.push({
      label: `${h.requesting_user_id === user?.user_id ? "Upload case documents" : "Upload order sheet"} — ${h.court_id}`,
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
  const recentActivity = useMemo(() => {
    const items = [];
    orders.forEach((o) => items.push({
      key: `order-${o.order_id}`, at: o.updated_at || o.created_at,
      label: `Order ${o.order_id} — ${(o.status || "").replace(/_/g, " ")}`, to: `/orders/${o.order_id}`,
    }));
    hearings.forEach((h) => (h.timeline || []).forEach((t, i) => items.push({
      key: `hearing-${h.hearing_id}-${i}`, at: t.at, label: `${h.court_id}: ${t.note}`,
      onClick: () => setActiveHearingId(h.hearing_id),
    })));
    notifications.forEach((n) => items.push({
      key: `notif-${n.notification_id}`, at: n.created_at, label: n.title, to: "/notifications",
    }));
    return items.filter((i) => i.at).sort((a, b) => new Date(b.at) - new Date(a.at)).slice(0, 12);
  }, [orders, hearings, notifications]);

  const advocateOwnedHearings = hearings.filter((h) => h.proxy_counsel_user_id === user?.user_id).length;

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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Upcoming Hearings */}
        <div className="lg:col-span-2">
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
                const isMine = h.requesting_user_id === user?.user_id;
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
                      <HearingProgressStepper status={h.status} compact negotiationAgreed={!h.target_advocate_id || h.commercially_locked} />
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </div>

        {/* Pending Actions — urgency color-coded */}
        <div>
          <h2 className="font-display font-bold text-2xl tracking-tight mb-4">Pending Actions</h2>
          {loading ? (
            <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="h-12 shimmer rounded-xl"></div>)}</div>
          ) : pendingActions.length === 0 ? (
            <Card className="border-dashed border-2" data-testid="empty-pending-actions">
              <CardContent className="p-6 text-center text-sm text-muted-foreground">You're all caught up — nothing needs your attention.</CardContent>
            </Card>
          ) : (
            <div className="space-y-2">
              {pendingActions.map((a) => (
                <button
                  key={a.key}
                  onClick={() => a.onClick ? a.onClick() : navigate(a.to)}
                  className="w-full text-left bento-card p-3 flex items-center gap-2.5"
                  data-testid={`pending-action-${a.key}`}
                >
                  <Badge className={`${PENDING_TIER_BADGE[a.tier]} border-0 text-2xs font-bold uppercase flex-shrink-0`}>{PENDING_TIER_LABEL[a.tier]}</Badge>
                  <span className="text-sm font-semibold truncate flex-1">{a.label}</span>
                </button>
              ))}
            </div>
          )}
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
          <div className="space-y-1.5">
            {recentActivity.map((item) => (
              <button
                key={item.key}
                onClick={() => item.onClick ? item.onClick() : navigate(item.to)}
                className="w-full text-left flex items-center justify-between gap-3 px-4 py-2.5 rounded-lg hover:bg-secondary/60 transition-colors"
                data-testid={`activity-${item.key}`}
              >
                <span className="text-sm font-medium truncate">{item.label}</span>
                <span className="text-2xs text-muted-foreground font-semibold flex-shrink-0">{timeAgo(item.at)}</span>
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
