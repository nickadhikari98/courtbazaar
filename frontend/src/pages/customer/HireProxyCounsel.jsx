import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
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

const serviceConfig = SERVICE_CONFIGS.proxy_counsel;

const STATUS_BADGE = {
  requested: "bg-amber-100 text-amber-700",
  broadcast: "bg-amber-100 text-amber-700",
  accepted: "bg-blue-100 text-blue-700",
  payment_pending: "bg-amber-100 text-amber-700",
  documents_shared: "bg-blue-100 text-blue-700",
  preparation: "bg-blue-100 text-blue-700",
  hearing_scheduled: "bg-blue-100 text-blue-700",
  hearing_completed: "bg-indigo-100 text-indigo-700",
  verification_pending: "bg-amber-100 text-amber-700",
  verified: "bg-emerald-100 text-emerald-700",
  completed: "bg-emerald-100 text-emerald-700",
  rated: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
  cancelled: "bg-red-100 text-red-700",
  disputed: "bg-red-100 text-red-700",
  expired: "bg-slate-100 text-slate-600",
};

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

/* Proxy Counsel request flow (founder direction, see PR description):
     Fill Request -> AI Recommendations (automatic) -> customer selects a
     counsel (from recommendations, or Search More Counsels as the one
     fallback) -> create the hearing request targeted at that counsel ->
     Negotiation Module.

   The actual POST /hearing-requests call is deliberately deferred until a
   counsel is selected (not fired on form submit) — the backend only
   accepts target_advocate_id at creation time, and the founder's explicit
   call was "don't create a hearing request if no counsel is selected,"
   rather than adding a new backend endpoint to attach one after the fact.
   "Continue" on the form below only moves to the recommendations step
   in-memory; nothing is persisted until Select Counsel. */
export default function HireProxyCounsel() {
  const navigate = useNavigate();
  const [hearings, setHearings] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [pendingRequest, setPendingRequest] = useState(null); // { payload, files, context } | null
  const [selectingId, setSelectingId] = useState(null);

  const load = () => listHearingRequests().then(setHearings);
  useEffect(() => { load(); }, []);

  const handleContinue = (payload, files) => {
    setPendingRequest({ payload, files, context: deriveMatchContext(payload) });
  };

  const handleEditRequest = () => setPendingRequest(null);

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
    load();
    navigate(`/hearing-requests/${hearing.hearing_id}/negotiate`, { state: { counsel, hearing } });
  };

  return (
    <PageContainer className="max-w-5xl">
      <PageHeader eyebrow="Services" eyebrowIcon={serviceConfig.heroIcon} title={serviceConfig.title}
                  description={serviceConfig.description} />

      <div className="mt-6">
        {!pendingRequest && (
          <div className="max-w-3xl">
            <LegalServiceRequestForm serviceConfig={serviceConfig} onSubmit={handleContinue} submitting={false} />
          </div>
        )}

        {pendingRequest && (
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

            <CounselDiscoveryPanel context={pendingRequest.context} onSelect={handleSelectCounsel} selectingId={selectingId} />
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
                <Badge className={`${STATUS_BADGE[h.status] || ""} border-0 font-bold uppercase`}>{h.status.replace(/_/g, " ")}</Badge>
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
