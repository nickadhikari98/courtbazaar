import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Pencil } from "lucide-react";
import { createHearingRequest, listHearingRequests } from "@/lib/hearingRequestsApi";
import { getErrorMessage } from "@/lib/api";
import HearingDetailDialog from "@/components/shared/HearingDetailDialog";
import HearingActivityPreview from "@/components/shared/HearingActivityPreview";
import ProxyCounselLocationForm from "@/components/proxyCounsel/ProxyCounselLocationForm";
import CounselDiscoveryPanel from "@/components/proxyCounsel/CounselDiscoveryPanel";
import { SERVICE_CONFIGS } from "@/config/serviceRequestFields";
import { useAuth } from "@/context/AuthContext";
import {
  HEARING_STATUS_BADGE_COLOR, roleAwareStatusLabel, getViewerRole,
  isHearingActive, COMPLETED_HEARING_STATUSES, CLOSED_HEARING_STATUSES,
} from "@/lib/hearingLifecycle";

const HEARING_TAB_LABELS = { active: "Active", completed: "Completed", cancelled: "Cancelled" };

const serviceConfig = SERVICE_CONFIGS.proxy_counsel;

// AvailableAdvocatesPanel's live-context recommendations (shown while
// typing, before any request existed) is gone — per the founder's product
// direction, recommendations are AI-driven and appear automatically only
// once the (now much shorter) intake form is complete, not before. The
// fields used for matching — court/state/district/hearing_date — are
// exactly the ones the slimmed-down ProxyCounselLocationForm collects; no
// work_type/priority/budget context is available (or needed — see
// counsel_matching.list_and_recommend) until a counsel is selected.
function deriveMatchContext(payload) {
  return {
    court_id: payload.court_id, court_name: payload.court_name,
    state_id: payload.state_id, district: payload.district,
    hearing_date: payload.hearing_date,
  };
}

/* Proxy Counsel request flow — BlaBlaCar-style, per founder direction:
     Fill Location + Date -> Find a Proxy Counsel (AI Recommendation /
     Search Manually toggle, see CounselDiscoveryPanel) -> customer selects
     a counsel -> create the hearing request targeted at that counsel ->
     Negotiation Module (fee agreement + payment) -> only once payment is
     confirmed does HearingDetailDialog reveal the case-details form and
     document sharing. The full case brief (title, type, instructions,
     work required, attachments) is intentionally NOT collected here
     anymore — see ProxyCounselCaseDetailsForm, filled in post-payment.

   The actual POST /hearing-requests call is deliberately deferred until a
   counsel is selected (not fired on form submit) — the backend only
   accepts target_advocate_id at creation time, and the founder's explicit
   call was "don't create a hearing request if no counsel is selected,"
   rather than adding a new backend endpoint to attach one after the fact.
   "Continue" on the form below only moves to the recommendations step
   in-memory; nothing is persisted until Select Counsel. */
export default function HireProxyCounsel() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [hearings, setHearings] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [pendingRequest, setPendingRequest] = useState(null); // { payload, context } | null
  const [editing, setEditing] = useState(false); // true while re-showing the form to edit an already-continued request
  const [selectingId, setSelectingId] = useState(null);
  // Set only via NegotiationModule.jsx's "End Negotiation" — excludes that
  // counsel from the AI recommendations list so the customer isn't nudged
  // right back to the one who just didn't work out.
  const [excludeAdvocateId, setExcludeAdvocateId] = useState(null);

  const load = () => listHearingRequests().then(setHearings);
  useEffect(() => { load(); }, []);

  // Default view stays focused on actionable work — Completed/Cancelled
  // (which also covers rejected/expired) are one tab away, not mixed in.
  const hearingTabs = useMemo(() => {
    const list = hearings || [];
    return {
      active: list.filter(isHearingActive),
      completed: list.filter((h) => COMPLETED_HEARING_STATUSES.includes(h.status)),
      cancelled: list.filter((h) => CLOSED_HEARING_STATUSES.includes(h.status)),
    };
  }, [hearings]);

  // End Negotiation (NegotiationModule.jsx) navigates here with the ended
  // hearing's own case details already filled in, landing straight on the
  // counsel-selection step instead of the empty form — the underlying
  // request was never cancelled, only the negotiation with that one counsel.
  useEffect(() => {
    const resume = location.state?.resumeRequest;
    if (!resume) return;
    setPendingRequest({ payload: resume.payload, context: deriveMatchContext(resume.payload) });
    setExcludeAdvocateId(resume.excludeAdvocateId || null);
    setEditing(false);
    navigate(location.pathname, { replace: true, state: null }); // consume it — a later refresh/back must not replay it
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once, off the location state present on mount only
  }, []);

  const handleContinue = (payload) => {
    setPendingRequest({ payload, context: deriveMatchContext(payload) });
    setExcludeAdvocateId(null); // a freshly-submitted form is unrelated to any prior negotiation
    setEditing(false);
  };

  // Re-shows the form instead of discarding pendingRequest — submitting it
  // again (handleContinue) is what actually replaces the pending request,
  // so everything the customer already filled in stays there to edit
  // rather than being lost.
  const handleEditRequest = () => setEditing(true);

  const handleSelectCounsel = async (counsel) => {
    if (!pendingRequest || selectingId) return;
    setSelectingId(counsel.advocate_id);

    const { state_id, state_name, district, court_id, court_name, hearing_date } = pendingRequest.payload;
    // Minimal, BlaBlaCar-style creation payload — no case_details/work_required/
    // budget/attachments here anymore (case_details is left blank; the
    // backend fills in a placeholder — see hearings.create_hearing_request).
    // The full brief is collected post-payment via ProxyCounselCaseDetailsForm.
    try {
      const hearing = await createHearingRequest({
        court_id, hearing_date, case_details: "", service_type: serviceConfig.serviceType,
        target_advocate_id: counsel.advocate_id,
        request_details: { common: { state_id, state_name, district, court_name }, service_specific: {} },
      });
      toast.success(`Request sent to ${counsel.name} — continue in the Negotiation Module`);
      setPendingRequest(null);
      setSelectingId(null);
      setExcludeAdvocateId(null);
      load();
      navigate(`/hearing-requests/${hearing.hearing_id}/negotiate`, { state: { counsel, hearing } });
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not send the request"));
      setSelectingId(null);
    }
  };

  return (
    <PageContainer className="max-w-5xl">
      <PageHeader eyebrow="Services" eyebrowIcon={serviceConfig.heroIcon} title={serviceConfig.title}
                  description={serviceConfig.description} />

      <div className="mt-6">
        {(!pendingRequest || editing) && (
          <div className="max-w-3xl">
            <ProxyCounselLocationForm
              onSubmit={handleContinue}
              initialValues={pendingRequest ? pendingRequest.payload : undefined}
            />
          </div>
        )}

        {pendingRequest && !editing && (
          <div>
            <Card className="dashboard-card border-none mb-6">
              <CardContent className="p-4 flex items-center justify-between gap-4 flex-wrap">
                <div className="text-sm">
                  <span className="text-muted-foreground">Request ready for</span>{" "}
                  <span className="font-semibold">{pendingRequest.context.court_name || pendingRequest.payload.court_id}</span>
                  {pendingRequest.payload.hearing_date ? <span className="text-muted-foreground"> · {pendingRequest.payload.hearing_date}</span> : null}
                </div>
                <Button type="button" variant="outline" size="sm" onClick={handleEditRequest} disabled={!!selectingId}>
                  <Pencil className="w-3.5 h-3.5 mr-1.5" /> Edit Request
                </Button>
              </CardContent>
            </Card>

            <CounselDiscoveryPanel
              context={pendingRequest.context} onSelect={handleSelectCounsel} selectingId={selectingId}
              excludeAdvocateId={excludeAdvocateId}
            />
          </div>
        )}
      </div>

      <div className="mt-10">
        <h2 className="font-display font-bold text-xl tracking-tight mb-4">My Requests</h2>
        {hearings === null ? (
          <div className="text-center text-muted-foreground py-10">Loading…</div>
        ) : hearings.length === 0 ? (
          <Card className="border-dashed border-2">
            <CardContent className="p-10 text-center">
              <serviceConfig.heroIcon className="w-10 h-10 mx-auto text-muted-foreground mb-3" strokeWidth={1.5} />
              <div className="font-display font-bold">{serviceConfig.emptyStateCopy.title}</div>
              <p className="text-sm text-muted-foreground mt-1">{serviceConfig.emptyStateCopy.body}</p>
            </CardContent>
          </Card>
        ) : (
          <Tabs defaultValue="active">
            <TabsList data-testid="hearing-requests-tabs">
              {Object.entries(hearingTabs).map(([key, list]) => (
                <TabsTrigger key={key} value={key} data-testid={`tab-${key}`}>
                  {HEARING_TAB_LABELS[key]} ({list.length})
                </TabsTrigger>
              ))}
            </TabsList>
            {Object.entries(hearingTabs).map(([key, list]) => (
              <TabsContent value={key} key={key} className="mt-4 space-y-3">
                {list.length === 0 ? (
                  <Card className="border-dashed border-2">
                    <CardContent className="p-8 text-center text-sm text-muted-foreground">
                      No {HEARING_TAB_LABELS[key].toLowerCase()} requests.
                    </CardContent>
                  </Card>
                ) : list.map((h) => (
                  <Card key={h.hearing_id} className="dashboard-card border-none cursor-pointer hover:shadow-md transition-shadow" onClick={() => setActiveId(h.hearing_id)} data-testid={`hearing-row-${h.hearing_id}`}>
                    <CardContent className="p-5">
                      <div className="flex items-center justify-between gap-4">
                        <div className="min-w-0">
                          <div className="font-display font-bold">{h.request_details?.common?.case_title || h.court_id}</div>
                          <div className="text-sm text-muted-foreground">{h.hearing_date} {h.fee ? `· ₹${h.fee}` : ""}</div>
                        </div>
                        <Badge className={`${HEARING_STATUS_BADGE_COLOR[h.status] || ""} border-0 font-bold uppercase`}>
                          {roleAwareStatusLabel(h, getViewerRole(h, user?.user_id))}
                        </Badge>
                      </div>
                      <HearingActivityPreview hearing={h} />
                    </CardContent>
                  </Card>
                ))}
              </TabsContent>
            ))}
          </Tabs>
        )}
      </div>

      <HearingDetailDialog
        hearingId={activeId}
        open={!!activeId}
        onOpenChange={(v) => !v && setActiveId(null)}
        onChanged={load}
      />
    </PageContainer>
  );
}
