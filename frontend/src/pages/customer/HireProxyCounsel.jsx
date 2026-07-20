import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { createHearingRequest, listHearingRequests, uploadHearingDocument } from "@/lib/hearingRequestsApi";
import HearingDetailDialog from "@/components/shared/HearingDetailDialog";
import LegalServiceRequestForm from "@/components/shared/LegalServiceRequestForm";
import AvailableAdvocatesPanel from "@/components/shared/AvailableAdvocatesPanel";
import { useAdvocateRecommendations } from "@/lib/advocateRecommendationsApi";
import { SERVICE_CONFIGS } from "@/config/serviceRequestFields";

const serviceConfig = SERVICE_CONFIGS.proxy_counsel;

const STATUS_BADGE = {
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

export default function HireProxyCounsel() {
  const [hearings, setHearings] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [activeId, setActiveId] = useState(null);
  const [context, setContext] = useState({});
  const [selectedAdvocate, setSelectedAdvocate] = useState(null);
  const recommendations = useAdvocateRecommendations(context);

  const load = () => listHearingRequests().then(setHearings);
  useEffect(() => { load(); }, []);

  const handleCreate = async (payload, files) => {
    setSubmitting(true);
    try {
      const hearing = await createHearingRequest(payload);
      for (const file of files) {
        // eslint-disable-next-line no-await-in-loop -- sequential uploads to the same hearing, order doesn't matter but simplicity does
        await uploadHearingDocument(hearing.hearing_id, "case_document", file);
      }
      toast.success("Request sent to available proxy counsel");
      setSelectedAdvocate(null);
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not create request");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <PageContainer className="max-w-6xl">
      <PageHeader eyebrow="Services" eyebrowIcon={serviceConfig.heroIcon} title={serviceConfig.title}
                  description={serviceConfig.description} />

      <div className="mt-6 grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-6 items-start">
        <LegalServiceRequestForm
          serviceConfig={serviceConfig} onSubmit={handleCreate} submitting={submitting}
          selectedAdvocate={selectedAdvocate} onContextChange={setContext}
        />
        <AvailableAdvocatesPanel
          {...recommendations}
          context={context}
          selectedAdvocateId={selectedAdvocate?.advocate_id}
          onSelect={setSelectedAdvocate}
          onClear={() => setSelectedAdvocate(null)}
          onRetry={recommendations.refetch}
        />
      </div>

      <div className="mt-8">
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
