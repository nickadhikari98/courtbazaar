import React, { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Pencil } from "lucide-react";
import { createHearingRequest, listHearingRequests, uploadHearingDocument } from "@/lib/hearingRequestsApi";
import { getErrorMessage } from "@/lib/api";
import HearingDetailDialog from "@/components/shared/HearingDetailDialog";
import LegalServiceRequestForm from "@/components/shared/LegalServiceRequestForm";
import CounselDiscoveryPanel from "@/components/proxyCounsel/CounselDiscoveryPanel";
import { SERVICE_CONFIGS } from "@/config/serviceRequestFields";
import { useAuth } from "@/context/AuthContext";
import { HEARING_STATUS_BADGE_COLOR, roleAwareStatusLabel, getViewerRole } from "@/lib/hearingLifecycle";

const serviceConfig = SERVICE_CONFIGS.proxy_counsel;

// AvailableAdvocatesPanel's live-context recommendations (shown while
// typing, before any request existed) is gone — per the founder's product
// direction, recommendations are AI-driven and appear automatically only
// once the request form itself is complete, not before. The fields used
// for matching are exactly the ones already collected by the form, so no
// new inputs are introduced here — just read back out of its payload.
function deriveMatchContext(payload) {
  const common = payload.request_details?.common || {};
  const serviceSpecific = payload.request_details?.service_specific || {};
  return {
    court_id: payload.court_id, court_name: common.court_name,
    state_id: common.state_id, district: common.district,
    work_type: serviceSpecific.work_required, priority: common.priority,
    hearing_date: payload.hearing_date, budget: payload.fee,
  };
}

// Inverse of LegalServiceRequestForm's handleSubmit payload-building — used
// only to re-populate the form's fields when the customer clicks "Edit
// Request" after already continuing past it, so editing one field doesn't
// throw away everything else they filled in.
function payloadToFields(payload) {
  const common = payload.request_details?.common || {};
  const serviceSpecific = payload.request_details?.service_specific || {};
  return {
    state_id: common.state_id || "", state_name: common.state_name || "", district: common.district || "",
    court_id: payload.court_id || "", court_name: common.court_name || "",
    case_title: common.case_title || "", case_number: common.case_number || "", case_type: common.case_type || "",
    hearing_date: payload.hearing_date || "", hearing_time: common.hearing_time || "", case_stage: common.case_stage || "",
    work_required: serviceSpecific.work_required || [], work_required_notes: serviceSpecific.work_required_notes || "",
    priority: common.priority || "Normal",
    case_details: payload.case_details || "",
    budget: payload.fee != null ? String(payload.fee) : "",
    target_type: payload.target_advocate_id ? "specific" : "any", target_advocate_id: payload.target_advocate_id || "",
  };
}

/* Proxy Counsel request flow (founder direction, see PR description):
     Fill Request -> Find a Proxy Counsel (AI Recommendation / Search
     Manually toggle, see CounselDiscoveryPanel) -> customer selects a
     counsel from whichever tab they used -> create the hearing request
     targeted at that counsel -> Negotiation Module.

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
  const [pendingRequest, setPendingRequest] = useState(null); // { payload, files, context } | null
  const [editing, setEditing] = useState(false); // true while re-showing the form to edit an already-continued request
  const [selectingId, setSelectingId] = useState(null);
  // Set only via NegotiationModule.jsx's "End Negotiation" — excludes that
  // counsel from the AI recommendations list so the customer isn't nudged
  // right back to the one who just didn't work out.
  const [excludeAdvocateId, setExcludeAdvocateId] = useState(null);

  const load = () => listHearingRequests().then(setHearings);
  useEffect(() => { load(); }, []);

  // End Negotiation (NegotiationModule.jsx) navigates here with the ended
  // hearing's own case details already filled in, landing straight on the
  // counsel-selection step instead of the empty form — the underlying
  // request was never cancelled, only the negotiation with that one counsel.
  useEffect(() => {
    const resume = location.state?.resumeRequest;
    if (!resume) return;
    setPendingRequest({ payload: resume.payload, files: [], context: deriveMatchContext(resume.payload) });
    setExcludeAdvocateId(resume.excludeAdvocateId || null);
    setEditing(false);
    navigate(location.pathname, { replace: true, state: null }); // consume it — a later refresh/back must not replay it
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once, off the location state present on mount only
  }, []);

  const handleContinue = (payload, files) => {
    setPendingRequest({ payload, files, context: deriveMatchContext(payload) });
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

    let hearing;
    try {
      hearing = await createHearingRequest({ ...pendingRequest.payload, target_advocate_id: counsel.advocate_id });
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not send the request"));
      setSelectingId(null);
      return;
    }

    // The hearing now exists in the backend — nothing past this point may
    // block navigation or make it look like the request failed. Document
    // upload is best-effort: a failed upload is recoverable (documents can
    // be added later from the hearing itself) and must never be conflated
    // with hearing-creation failure.
    let uploadFailures = 0;
    for (const file of pendingRequest.files) {
      try {
        // eslint-disable-next-line no-await-in-loop -- sequential uploads to the same hearing, order doesn't matter but simplicity does
        await uploadHearingDocument(hearing.hearing_id, "case_document", file);
      } catch {
        uploadFailures += 1;
      }
    }

    if (uploadFailures > 0) {
      const plural = uploadFailures > 1 ? "s" : "";
      toast.warning(`Request sent to ${counsel.name} — ${uploadFailures} document${plural} could not be uploaded and can be added later.`);
    } else {
      toast.success(`Request sent to ${counsel.name} — continue in the Negotiation Module`);
    }

    setPendingRequest(null);
    setSelectingId(null);
    setExcludeAdvocateId(null);
    load();
    navigate(`/hearing-requests/${hearing.hearing_id}/negotiate`, { state: { counsel, hearing } });
  };

  return (
    <PageContainer className="max-w-5xl">
      <PageHeader eyebrow="Services" eyebrowIcon={serviceConfig.heroIcon} title={serviceConfig.title}
                  description={serviceConfig.description} />

      <div className="mt-6">
        {(!pendingRequest || editing) && (
          <div className="max-w-3xl">
            <LegalServiceRequestForm
              serviceConfig={serviceConfig} onSubmit={handleContinue} submitting={false}
              initialValues={pendingRequest ? payloadToFields(pendingRequest.payload) : undefined}
              initialFiles={pendingRequest?.files}
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
        {hearings === null && <div className="text-center text-muted-foreground py-10">Loading…</div>}
        {hearings?.length === 0 && (
          <Card className="border-dashed border-2">
            <CardContent className="p-10 text-center">
              <serviceConfig.heroIcon className="w-10 h-10 mx-auto text-muted-foreground mb-3" strokeWidth={1.5} />
              <div className="font-display font-bold">{serviceConfig.emptyStateCopy.title}</div>
              <p className="text-sm text-muted-foreground mt-1">{serviceConfig.emptyStateCopy.body}</p>
            </CardContent>
          </Card>
        )}
        <div className="space-y-3">
          {hearings?.map((h) => (
            <Card key={h.hearing_id} className="dashboard-card border-none cursor-pointer hover:shadow-md transition-shadow" onClick={() => setActiveId(h.hearing_id)}>
              <CardContent className="p-5 flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="font-display font-bold">{h.request_details?.common?.case_title || h.court_id}</div>
                  <div className="text-sm text-muted-foreground">{h.hearing_date} {h.fee ? `· ₹${h.fee}` : ""}</div>
                </div>
                <Badge className={`${HEARING_STATUS_BADGE_COLOR[h.status] || ""} border-0 font-bold uppercase`}>
                  {roleAwareStatusLabel(h, getViewerRole(h, user?.user_id))}
                </Badge>
              </CardContent>
            </Card>
          ))}
        </div>
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
