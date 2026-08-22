import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import AppLayout from "@/components/layout/AppLayout";
import MarketingLayout from "@/components/layout/MarketingLayout";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { RefreshCw, Users, Trash2, Clock } from "lucide-react";
import { createHearingRequest, listHearingRequests, cancelHearingRequest } from "@/lib/hearingRequestsApi";
import { getErrorMessage, formatINR } from "@/lib/api";
import { getPublicProxyCounsels, getAdvocateProfile } from "@/lib/advocateRecommendationsApi";
import HearingDetailDialog from "@/components/shared/HearingDetailDialog";
import HearingActivityPreview from "@/components/shared/HearingActivityPreview";
import CourtLocationSelector from "@/components/shared/CourtLocationSelector";
import CounselCard from "@/components/proxyCounsel/CounselCard";
import CounselProfileDialog from "@/components/proxyCounsel/CounselProfileDialog";
import EmptyState from "@/components/shared/EmptyState";
import Loading from "@/components/shared/Loading";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import { SERVICE_CONFIGS } from "@/config/serviceRequestFields";
import { resolveDateBound } from "@/lib/utils";
import { useAuth } from "@/context/AuthContext";
import {
  HEARING_STATUS_BADGE_COLOR, roleAwareStatusLabel, getViewerRole,
  isHearingActive, COMPLETED_HEARING_STATUSES, CLOSED_HEARING_STATUSES,
} from "@/lib/hearingLifecycle";

const HEARING_TAB_LABELS = { active: "Active", completed: "Completed", cancelled: "Cancelled" };

const serviceConfig = SERVICE_CONFIGS.proxy_counsel;
const TODAY = resolveDateBound("today");

/* Proxy Counsel browse page — founder direction (2026-08): the counsel grid
   and full profile view are both public (no login wall, filters narrow the
   same grid in place, no separate step/page to "unlock" it); only booking a
   counsel ("Select Counsel") requires an account (see requireLogin below).
   Replaces
   the earlier BlaBlaCar-style "fill a form, then reveal recommendations"
   flow — that flow's now-orphaned pieces (ProxyCounselLocationForm,
   CounselDiscoveryPanel, ManualCounselSearch) were removed rather than left
   unused; CounselCard/CounselProfileDialog are still shared with
   NegotiationModule.jsx's counsel-profile fallback.

   Anonymous visitors render inside MarketingLayout (same public shell as
   Landing/Pricing/About); a logged-in visitor gets the normal AppLayout
   sidebar shell — both wrap the exact same page content below. */
export default function HireProxyCounsel() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [filters, setFilters] = useState({
    state_id: "", state_name: "", district: "", court_id: "", court_name: "", court_type: "", hearing_date: "",
  });
  const [status, setStatus] = useState("loading"); // loading | ready | empty | error
  const [advocates, setAdvocates] = useState([]);
  const [selectingId, setSelectingId] = useState(null);
  const [profileCounsel, setProfileCounsel] = useState(null);
  // Set only via NegotiationModule.jsx's "End Negotiation" — excludes that
  // counsel from the grid so the customer isn't nudged right back to the
  // one who just didn't work out.
  const [excludeAdvocateId, setExcludeAdvocateId] = useState(null);
  // "Urgent / Same-day" intent — informational only at this stage (the
  // actual case Priority is still set post-payment via the case-details
  // form). When on, every card surfaces that counsel's own saved Urgent
  // slot fee instead of the generic "starting from" figure, and selecting
  // a counsel confirms that fee before the request is sent.
  const [isUrgent, setIsUrgent] = useState(false);
  const [sortBy, setSortBy] = useState("match"); // match | experience | rating
  const [urgentConfirmTarget, setUrgentConfirmTarget] = useState(null); // counsel awaiting the urgent-fee confirm

  const [hearings, setHearings] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [cancelTarget, setCancelTarget] = useState(null); // hearing being confirmed for cancel
  const [cancelling, setCancelling] = useState(false);

  const fetchAdvocates = () => {
    setStatus("loading");
    getPublicProxyCounsels({ court_id: filters.court_id, state_id: filters.state_id, district: filters.district })
      .then(({ advocates: list }) => {
        // A logged-in customer who is also a verified proxy counsel
        // themselves shouldn't see their own card in the grid they're
        // browsing to hire someone else.
        const filtered = list.filter((a) => a.advocate_id !== excludeAdvocateId && a.advocate_id !== user?.user_id);
        setAdvocates(filtered);
        setStatus(filtered.length ? "ready" : "empty");
      })
      .catch(() => setStatus("error"));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- re-fetch on the location filters the backend filters by, plus whichever account is viewing (so self-exclusion re-applies across login/logout)
  useEffect(() => { fetchAdvocates(); }, [filters.court_id, filters.state_id, filters.district, excludeAdvocateId, user?.user_id]);

  // Client-side sort over the already-fetched page (the backend's own order
  // is its AI match ranking — "match" keeps that as-is; the other two just
  // re-order the same list already on screen, no extra request).
  const sortedAdvocates = useMemo(() => {
    if (sortBy === "match") return advocates;
    const key = sortBy === "experience" ? "experience_years" : "rating";
    return [...advocates].sort((a, b) => (b[key] ?? -1) - (a[key] ?? -1));
  }, [advocates, sortBy]);

  // The counsel's own saved rate for the court type currently filtered on
  // (district vs high court); falls back to whichever court type they've
  // actually priced if the browse page has no court-type filter active yet
  // (e.g. before a state/court is picked), so the badge still shows
  // *something* rather than nothing whenever a rate exists at all.
  const urgentFeeFor = (counsel) => {
    const byType = counsel.pricing?.[filters.court_type]?.urgent;
    if (byType != null) return byType;
    return counsel.pricing?.district?.urgent ?? counsel.pricing?.high_court?.urgent ?? null;
  };

  useEffect(() => { if (user) listHearingRequests().then(setHearings); }, [user]);

  const hearingTabs = useMemo(() => {
    const list = hearings || [];
    return {
      active: list.filter(isHearingActive),
      completed: list.filter((h) => COMPLETED_HEARING_STATUSES.includes(h.status)),
      cancelled: list.filter((h) => CLOSED_HEARING_STATUSES.includes(h.status)),
    };
  }, [hearings]);

  // Same resumeRequest handoff NegotiationModule.jsx's "End Negotiation"
  // always used — only ever reached already logged in, so no interaction
  // with the anonymous-browsing path below.
  useEffect(() => {
    const resume = location.state?.resumeRequest;
    if (!resume) return;
    setFilters((f) => ({ ...f, ...resume.payload }));
    setExcludeAdvocateId(resume.excludeAdvocateId || null);
    navigate(location.pathname, { replace: true, state: null }); // consume it — a later refresh/back must not replay it
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once, off the location state present on mount only
  }, []);

  const requireLogin = () => navigate("/login", { state: { from: "/hire-proxy-counsel" } });

  const handleViewProfile = async (counsel) => {
    try {
      const full = await getAdvocateProfile(counsel.advocate_id);
      setProfileCounsel(full);
    } catch {
      toast.error("Could not load this profile right now");
    }
  };

  const handleSelectCounsel = (counsel) => {
    if (!user) { requireLogin(); return; }
    if (!filters.court_id || !filters.hearing_date) {
      toast.error("Pick a court and hearing date above first");
      return;
    }
    if (filters.hearing_date < TODAY) {
      toast.error("Hearing date can't be in the past");
      return;
    }
    if (selectingId) return;
    // Urgent requests stop for an explicit confirm so the Counsel sees this
    // counsel's own saved Urgent Fee before the request goes out — see
    // urgentConfirmTarget's ConfirmDialog below. A non-urgent pick sends
    // immediately, unchanged from before.
    if (isUrgent) { setUrgentConfirmTarget(counsel); return; }
    sendRequestTo(counsel);
  };

  const sendRequestTo = async (counsel) => {
    setSelectingId(counsel.advocate_id);
    try {
      const hearing = await createHearingRequest({
        court_id: filters.court_id, hearing_date: filters.hearing_date, case_details: "",
        service_type: serviceConfig.serviceType, target_advocate_id: counsel.advocate_id,
        request_details: {
          common: {
            state_id: filters.state_id, state_name: filters.state_name, district: filters.district, court_name: filters.court_name,
            ...(isUrgent ? { priority: "Urgent" } : {}),
          },
          service_specific: {},
        },
      });
      toast.success(`Request sent to ${counsel.name} — continue in the Negotiation Module`);
      setSelectingId(null);
      setExcludeAdvocateId(null);
      setUrgentConfirmTarget(null);
      if (user) listHearingRequests().then(setHearings);
      navigate(`/hearing-requests/${hearing.hearing_id}/negotiate`, { state: { counsel, hearing } });
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not send the request"));
      setSelectingId(null);
    }
  };

  // "Delete" in the founder's ask maps to the backend's cancel transition —
  // there's no hard-delete of a hearing request (audit/refund history has
  // to survive), so this moves it into the Cancelled tab rather than
  // removing it outright. Refunds automatically if payment was already held
  // (hearings.cancel_hearing_request); refused (with a clear error) once a
  // fee's been agreed through negotiation.
  const handleCancelRequest = async () => {
    if (!cancelTarget) return;
    setCancelling(true);
    try {
      await cancelHearingRequest(cancelTarget.hearing_id);
      toast.success("Request cancelled");
      setCancelTarget(null);
      listHearingRequests().then(setHearings);
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not cancel this request"));
    } finally {
      setCancelling(false);
    }
  };

  const content = (
    <PageContainer className="max-w-6xl">
      <PageHeader eyebrow="Services" eyebrowIcon={serviceConfig.heroIcon} title={serviceConfig.title}
                  description={serviceConfig.description} />

      <Card className="dashboard-card border-none mt-6">
        <CardContent className="p-5">
          <div className="font-display font-bold mb-3">Filter by location</div>
          <CourtLocationSelector
            value={filters}
            onChange={(loc) => setFilters((f) => ({ ...f, ...loc }))}
          />
          <div className="mt-3 flex flex-wrap items-end gap-4">
            <div className="max-w-xs">
              <Label>Hearing Date <span className="text-muted-foreground font-normal">(needed to book)</span></Label>
              <Input
                type="date" value={filters.hearing_date} min={TODAY}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v && v < TODAY) { toast.error("Hearing date can't be in the past"); return; }
                  setFilters((f) => ({ ...f, hearing_date: v }));
                }}
                data-testid="proxy-counsel-hearing-date"
              />
            </div>
            <div className="flex items-center gap-2 pb-1.5">
              <Switch checked={isUrgent} onCheckedChange={setIsUrgent} data-testid="urgent-toggle" />
              <div className="flex items-center gap-1 text-sm font-semibold">
                <Clock className="w-3.5 h-3.5 text-amber-600" /> Urgent / Same-day request
              </div>
            </div>
          </div>
          {isUrgent && (
            <p className="text-xs text-muted-foreground mt-2">
              Each counsel below now shows their own saved Urgent Fee — you'll see it again to confirm before the request is sent.
            </p>
          )}
        </CardContent>
      </Card>

      <div className="mt-6">
        {status === "loading" && <Loading />}
        {status === "error" && (
          <EmptyState
            description="Couldn't load counsels right now."
            action={<Button type="button" variant="outline" size="sm" onClick={fetchAdvocates}><RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Retry</Button>}
          />
        )}
        {status === "empty" && (
          <EmptyState icon={Users} title="No counsels match these filters" description="Try widening or clearing the location filters above." />
        )}
        {status === "ready" && (
          <>
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs text-muted-foreground">{advocates.length} proxy counsel{advocates.length === 1 ? "" : "s"}</p>
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground">Sort by</Label>
              <Select value={sortBy} onValueChange={setSortBy}>
                <SelectTrigger className="w-40 h-8 text-xs" data-testid="counsel-sort-by"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="match">Best Match</SelectItem>
                  <SelectItem value="experience">Experience</SelectItem>
                  <SelectItem value="rating">Rating</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {sortedAdvocates.map((a) => (
              <CounselCard
                key={a.advocate_id} counsel={a} onViewProfile={handleViewProfile}
                onSelect={handleSelectCounsel} selecting={selectingId === a.advocate_id}
                disabled={!!selectingId && selectingId !== a.advocate_id}
                showUrgentFee={isUrgent} urgentFee={urgentFeeFor(a)}
              />
            ))}
          </div>
          </>
        )}
      </div>

      <ConfirmDialog
        open={!!urgentConfirmTarget}
        onOpenChange={(v) => !v && setUrgentConfirmTarget(null)}
        busy={selectingId === urgentConfirmTarget?.advocate_id}
        title="Send urgent request?"
        description={(
          <>
            {urgentFeeFor(urgentConfirmTarget || {}) != null ? (
              <>
                <b className="text-foreground">{urgentConfirmTarget?.name}</b>'s Urgent (same-day) fee is{" "}
                <b className="text-foreground">{formatINR(urgentFeeFor(urgentConfirmTarget || {}))}</b>. This is their reference
                rate for urgent work — the final fee is still confirmed with them during negotiation.
              </>
            ) : (
              <>
                <b className="text-foreground">{urgentConfirmTarget?.name}</b> hasn't set a specific Urgent Fee yet — you can
                still send the request and discuss the fee during negotiation.
              </>
            )}
          </>
        )}
        confirmLabel="Send Request"
        confirmVariant="default"
        onConfirm={() => urgentConfirmTarget && sendRequestTo(urgentConfirmTarget)}
      />

      <CounselProfileDialog counsel={profileCounsel} onOpenChange={(v) => !v && setProfileCounsel(null)} />

      {user && (
        <div className="mt-10">
          <h2 className="font-display font-bold text-xl tracking-tight mb-4">My Requests</h2>
          {hearings === null ? (
            <Loading />
          ) : hearings.length === 0 ? (
            <EmptyState
              icon={serviceConfig.heroIcon}
              title={serviceConfig.emptyStateCopy.title}
              description={serviceConfig.emptyStateCopy.body}
            />
          ) : (
            <Card className="dashboard-card border-none">
              <CardContent className="p-4">
                <Tabs defaultValue="active">
                  <TabsList data-testid="hearing-requests-tabs">
                    {Object.entries(hearingTabs).map(([key, list]) => (
                      <TabsTrigger key={key} value={key} data-testid={`tab-${key}`}>
                        {HEARING_TAB_LABELS[key]} ({list.length})
                      </TabsTrigger>
                    ))}
                  </TabsList>
                  {Object.entries(hearingTabs).map(([key, list]) => (
                    <TabsContent value={key} key={key} className="mt-4">
                      {/* Fixed height (not max-height) — a request completing/moving
                          tabs shrinks the list, and max-height let the whole card
                          (and the page below it) suddenly jump up to fill the gap.
                          Fixed height + inner scroll keeps the page layout stable
                          regardless of how many items are in a given tab. Sized for
                          ~2 full cards visible (was one fixed 480px box showing 4+ —
                          felt oversized) with a sliver of the next to hint scroll. */}
                      <div className="h-[260px] overflow-y-auto cb-scroll">
                        {list.length === 0 ? (
                          <div className="h-full flex items-center justify-center">
                            <EmptyState size="sm" description={`No ${HEARING_TAB_LABELS[key].toLowerCase()} requests.`} />
                          </div>
                        ) : (
                          <div className="space-y-3 pr-1">
                            {list.map((h) => (
                              <Card key={h.hearing_id} className="dashboard-card border-none cursor-pointer hover:shadow-md transition-shadow" onClick={() => setActiveId(h.hearing_id)} data-testid={`hearing-row-${h.hearing_id}`}>
                                <CardContent className="p-5">
                                  <div className="flex items-start justify-between gap-4">
                                    <div className="min-w-0">
                                      <div className="font-display font-bold">{h.request_details?.common?.case_title || h.court_id}</div>
                                      <div className="text-sm text-muted-foreground">{h.hearing_date} {h.fee ? `· ₹${h.fee}` : ""}</div>
                                    </div>
                                    <div className="flex items-center gap-2 flex-shrink-0">
                                      <Badge className={`${HEARING_STATUS_BADGE_COLOR[h.status] || ""} border-0 font-bold uppercase`}>
                                        {roleAwareStatusLabel(h, getViewerRole(h, user?.user_id))}
                                      </Badge>
                                      {key === "active" && (
                                        <button
                                          type="button"
                                          onClick={(e) => { e.stopPropagation(); setCancelTarget(h); }}
                                          className="p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                                          aria-label="Cancel request"
                                          data-testid={`cancel-hearing-${h.hearing_id}`}
                                        >
                                          <Trash2 className="w-4 h-4" />
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                  <HearingActivityPreview hearing={h} />
                                </CardContent>
                              </Card>
                            ))}
                          </div>
                        )}
                      </div>
                    </TabsContent>
                  ))}
                </Tabs>
              </CardContent>
            </Card>
          )}

          <HearingDetailDialog
            hearingId={activeId}
            open={!!activeId}
            onOpenChange={(v) => !v && setActiveId(null)}
            onChanged={() => listHearingRequests().then(setHearings)}
          />

          <ConfirmDialog
            open={!!cancelTarget}
            onOpenChange={(v) => !v && setCancelTarget(null)}
            busy={cancelling}
            title="Cancel this request?"
            description={(
              <>
                Are you sure you want to cancel the request for{" "}
                <b className="text-foreground">{cancelTarget?.request_details?.common?.case_title || cancelTarget?.court_id}</b>?
                {" "}If payment has already been held, it will be refunded automatically.
              </>
            )}
            confirmLabel="Cancel Request"
            confirmIcon={Trash2}
            onConfirm={handleCancelRequest}
          />
        </div>
      )}
    </PageContainer>
  );

  if (!user) return <MarketingLayout>{content}</MarketingLayout>;
  return <AppLayout>{content}</AppLayout>;
}
