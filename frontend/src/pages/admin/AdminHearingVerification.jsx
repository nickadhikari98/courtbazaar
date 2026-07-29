import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { formatINR } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { CheckCircle2, XCircle, Banknote, FileText, Loader2 } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import HearingTimeline from "@/components/shared/HearingTimeline";
import HearingProgressStepper from "@/components/shared/HearingProgressStepper";
import {
  adminListHearingRequests, adminVerifyHearingOrderSheet, adminRejectHearingVerification,
  adminResolveHearingDispute, adminReleaseHearingPayout, getHearingEscrow, getHearingRequest,
  listHearingDocuments, getHearingDocumentUrl,
} from "@/lib/hearingRequestsApi";

const STATUS_TABS = [
  { value: "verification_pending", label: "Awaiting verification" },
  { value: "verified", label: "Verified — ready for payout" },
  { value: "disputed", label: "Disputed" },
  { value: "completed", label: "Completed" },
];

export default function AdminHearingVerification() {
  const [status, setStatus] = useState("verification_pending");
  const [hearings, setHearings] = useState(null);
  const [activeId, setActiveId] = useState(null);

  const load = () => { setHearings(null); adminListHearingRequests(status).then(setHearings); };
  useEffect(() => { load(); }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <PageContainer className="max-w-4xl">
      <PageHeader eyebrow="Admin · Hearing Verification" eyebrowIcon={Banknote}
                  title="Verify order sheets & release payouts"
                  description="Verify and Release Payout are always separate steps — payouts only unlock once a hearing is verified." />

      <Tabs value={status} onValueChange={setStatus} className="mt-6">
        <TabsList>
          {STATUS_TABS.map((t) => <TabsTrigger key={t.value} value={t.value}>{t.label}</TabsTrigger>)}
        </TabsList>
      </Tabs>

      <div className="mt-4 space-y-3">
        {hearings === null && <div className="text-center text-muted-foreground py-10">Loading…</div>}
        {hearings?.length === 0 && (
          <Card className="border-dashed border-2">
            <CardContent className="p-10 text-center text-muted-foreground">Nothing here right now.</CardContent>
          </Card>
        )}
        {hearings?.map((h) => (
          <Card key={h.hearing_id} className="dashboard-card border-none cursor-pointer hover:shadow-md transition-shadow"
                onClick={() => setActiveId(h.hearing_id)} data-testid={`admin-hearing-row-${h.hearing_id}`}>
            <CardContent className="p-5 flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="font-display font-bold">{h.court_id}</div>
                <div className="text-sm text-muted-foreground">{h.hearing_date} {h.fee ? `· ${formatINR(h.fee)}` : ""}</div>
              </div>
              <Badge variant="outline" className="font-bold uppercase text-2xs">{h.status.replace(/_/g, " ")}</Badge>
            </CardContent>
          </Card>
        ))}
      </div>

      <HearingVerificationDialog hearingId={activeId} open={!!activeId} onOpenChange={(v) => !v && setActiveId(null)} onChanged={load} />
    </PageContainer>
  );
}

function HearingVerificationDialog({ hearingId, open, onOpenChange, onChanged }) {
  const [hearing, setHearing] = useState(null);
  const [escrow, setEscrow] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [remark, setRemark] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    if (!hearingId) return;
    getHearingRequest(hearingId).then(setHearing).catch(() => {});
    getHearingEscrow(hearingId).then(setEscrow).catch(() => setEscrow(null));
    listHearingDocuments(hearingId).then(setDocuments).catch(() => {});
  };
  useEffect(() => { if (open) load(); }, [open, hearingId]); // eslint-disable-line react-hooks/exhaustive-deps

  const orderSheet = documents.find((d) => d.kind === "order_sheet");

  const run = async (fn, successMsg) => {
    setBusy(true);
    try {
      await fn();
      toast.success(successMsg);
      onChanged?.();
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "That didn't work");
    } finally {
      setBusy(false);
    }
  };

  const openOrderSheet = async () => {
    if (!orderSheet) return;
    const { url } = await getHearingDocumentUrl(hearingId, orderSheet.doc_id);
    window.open(url, "_blank", "noopener,noreferrer");
  };

  if (!hearing) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>Hearing verification</DialogTitle></DialogHeader>
          <div className="text-center text-muted-foreground py-6">{open ? "Loading…" : null}</div>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display text-xl flex items-center gap-2">
            {hearing.court_id}
            <Badge variant="outline" className="uppercase text-2xs font-bold">{hearing.status.replace(/_/g, " ")}</Badge>
          </DialogTitle>
          <DialogDescription>Hearing date {hearing.hearing_date}</DialogDescription>
        </DialogHeader>

        <HearingProgressStepper status={hearing.status} compact targeted={!!hearing.target_advocate_id} />

        {/* Escrow amount / commission / final payout — shown before any action */}
        {escrow && (
          <div className="rounded-lg border p-4 grid grid-cols-3 gap-3 text-center bg-secondary/30">
            <div>
              <div className="cb-overline">Escrow amount</div>
              <div className="font-display font-bold">{formatINR(escrow.amount)}</div>
            </div>
            <div>
              <div className="cb-overline">Commission</div>
              <div className="font-display font-bold">{(escrow.platform_commission_pct * 100).toFixed(0)}%</div>
            </div>
            <div>
              <div className="cb-overline">Advocate payout</div>
              <div className="font-display font-bold text-accent">{formatINR(escrow.payee_amount)}</div>
            </div>
          </div>
        )}

        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1.5">Order sheet</div>
          {orderSheet ? (
            <button type="button" onClick={openOrderSheet} className="w-full flex items-center gap-2 text-sm border rounded-md px-2.5 py-1.5 hover:bg-slate-50 text-left">
              <FileText className="w-4 h-4 text-accent flex-shrink-0" />
              <span className="truncate flex-1">{orderSheet.original_filename}</span>
            </button>
          ) : <p className="text-sm text-muted-foreground">No order sheet uploaded yet.</p>}
        </div>

        {["verification_pending", "disputed"].includes(hearing.status) && (
          <Textarea rows={2} value={remark} onChange={(e) => setRemark(e.target.value)} placeholder="Remark (shown to the advocate)" />
        )}

        <div className="border-t pt-3 flex flex-wrap gap-2">
          {hearing.status === "verification_pending" && (
            <>
              <Button type="button" disabled={busy} onClick={() => run(() => adminVerifyHearingOrderSheet(hearingId), "Verified")} className="bg-emerald-600 hover:bg-emerald-700 font-bold">
                {busy ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <CheckCircle2 className="w-4 h-4 mr-1.5" />} Verify
              </Button>
              <Button type="button" disabled={busy} variant="outline" onClick={() => run(() => adminRejectHearingVerification(hearingId, remark), "Marked disputed")} className="font-bold text-red-600 border-red-200 hover:bg-red-50">
                <XCircle className="w-4 h-4 mr-1.5" /> Reject (raise dispute)
              </Button>
            </>
          )}
          {hearing.status === "disputed" && (
            <>
              <Button type="button" disabled={busy} onClick={() => run(() => adminResolveHearingDispute(hearingId, "resubmit", remark), "Back to verification")} className="bg-primary font-bold">
                Resubmit for review
              </Button>
              <Button type="button" disabled={busy} variant="outline" onClick={() => run(() => adminResolveHearingDispute(hearingId, "refund", remark), "Refunded & cancelled")} className="font-bold text-red-600 border-red-200 hover:bg-red-50">
                Refund & cancel
              </Button>
            </>
          )}
          {/* Release Payout: only ever enabled once `verify` has already run — never bundled with it. */}
          {hearing.status === "completed" ? (
            <Badge className="bg-emerald-100 text-emerald-700 border-0 font-bold">Payout released</Badge>
          ) : (
            <Button type="button" disabled={busy || hearing.status !== "verified"}
                    onClick={() => run(() => adminReleaseHearingPayout(hearingId), "Payout released")}
                    className="bg-accent hover:bg-accent/90 font-bold"
                    title={hearing.status !== "verified" ? "Verify the order sheet first" : undefined}>
              <Banknote className="w-4 h-4 mr-1.5" /> Release Payout
            </Button>
          )}
        </div>

        <div className="border-t pt-3">
          <HearingTimeline timeline={hearing.timeline} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
