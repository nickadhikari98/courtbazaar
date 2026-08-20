import React, { useRef, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import DocumentPreviewDialog from "@/components/shared/DocumentPreviewDialog";
import { Lock, Upload, FileText, CheckCircle2, ShieldAlert, Loader2 } from "lucide-react";
import {
  uploadHearingDocument, getHearingDocumentUrl, verifyAndReleaseHearingPayout, raiseHearingDispute,
} from "@/lib/hearingRequestsApi";
import { getErrorMessage, formatINR } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/negotiationRoles";

// Statuses this component owns — everything from "escrow funded, hearing not
// yet conducted" through payout/dispute resolution. NegotiationNextAction
// owns everything before this (requested/payment_pending/broadcast); the two
// never render for the same hearing.status, so there's exactly one "what do
// I do next" surface on the page at any given time.
const OWNED_STATUSES = [
  "documents_shared", "preparation", "hearing_scheduled", "hearing_completed",
  "verification_pending", "disputed", "verified", "completed", "rated",
];

// Mirrors backend hearings.AUTO_RELEASE_DELAY_DAYS — display copy only, the
// actual deadline is enforced server-side by the auto-release scheduler.
const AUTO_RELEASE_DAYS = 3;

/* Escrow Module (founder's rules 3-9) — same one-primary-action-per-stage
   discipline as NegotiationOfferPanel/NegotiationNextAction, now covering
   the post-payment operational lifecycle: escrow-held messaging, Mark
   Conducted, order sheet upload, and the requester's Verify/Dispute action.
   Mark Conducted calls the exact same hearings.mark_hearing_conducted
   endpoint HearingDetailDialog/Practice.jsx's own button uses — self-
   routable, not a hop to a different page to trigger one action. */
export default function EscrowStagePanel({
  hearingId, hearing, viewerRole, onChanged, canMarkConducted, markingConducted, onMarkConducted,
}) {
  const [busy, setBusy] = useState(false);
  const [disputeOpen, setDisputeOpen] = useState(false);
  const [remark, setRemark] = useState("");
  const [preview, setPreview] = useState(null); // { url, filename } — in-page order sheet preview
  const fileInputRef = useRef(null);

  if (!OWNED_STATUSES.includes(hearing.status)) return null;

  const otherRoleLabel = ROLE_LABEL[viewerRole === "customer" ? "counsel" : "customer"];
  const amount = formatINR(hearing.fee);

  const uploadOrderSheet = async () => {
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      toast.error("Choose a file first");
      return;
    }
    setBusy(true);
    try {
      await uploadHearingDocument(hearingId, "order_sheet", file);
      toast.success("Order sheet uploaded — waiting for the Hiring Advocate to verify.");
      fileInputRef.current.value = "";
      await onChanged?.();
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not upload the order sheet"));
    } finally {
      setBusy(false);
    }
  };

  const viewOrderSheet = async () => {
    if (!hearing.order_sheet_doc_id) return;
    try {
      // inline: true — renders in the DocumentPreviewDialog below so it can
      // be checked right there on the same page, no download or new tab.
      const { url, filename } = await getHearingDocumentUrl(hearingId, hearing.order_sheet_doc_id, { inline: true });
      setPreview({ url, filename });
    } catch {
      toast.error("Could not open the order sheet");
    }
  };

  const submitVerifyAndRelease = async () => {
    setBusy(true);
    try {
      await verifyAndReleaseHearingPayout(hearingId);
      toast.success("Hearing verified — escrow released to the Proxy Counsel.");
      await onChanged?.();
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not verify this hearing"));
    } finally {
      setBusy(false);
    }
  };

  const submitDispute = async () => {
    setBusy(true);
    try {
      await raiseHearingDispute(hearingId, remark.trim() || undefined);
      toast.success("Dispute raised — this is now under admin review.");
      setDisputeOpen(false);
      setRemark("");
      await onChanged?.();
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not raise a dispute"));
    } finally {
      setBusy(false);
    }
  };

  // documents_shared/preparation genuinely need no action from either party
  // yet — both auto-progress the moment a case document is shared (see
  // hearings.add_document's auto-chain), unlike hearing_scheduled below.
  // Bug fix: this used to tell the counsel "upload the Court Order Sheet"
  // here too, even though that action isn't reachable until
  // hearing_completed — the exact "told to upload, no upload button
  // anywhere" confusion reported. Order Sheet is mentioned ONLY in the
  // hearing_completed branch below, where the real button actually lives.
  if (["documents_shared", "preparation"].includes(hearing.status)) {
    return (
      <Card className="border-none bg-secondary/50 shadow-none" data-testid="escrow-stage-panel">
        <CardContent className="p-4 flex items-center gap-2 text-sm font-semibold">
          <Lock className="w-4 h-4 text-accent flex-shrink-0" />
          {viewerRole === "customer"
            ? `${amount} is securely held in Escrow — released once the hearing is completed and verified.`
            : `${amount} is securely held in Escrow. Nothing needed from you yet — the hearing is being prepared.`}
        </CardContent>
      </Card>
    );
  }

  // hearing_scheduled has a real pending action — Mark Hearing Conducted,
  // only possible once the actual court date has passed (an order sheet
  // can't exist for a hearing that hasn't happened yet). The previous
  // generic "escrow held" text never said Mark Conducted was needed, which
  // is the gap the production audit traced ("why can't I reach Upload Order
  // Sheet") — this both names the action and lets the counsel do it here.
  if (hearing.status === "hearing_scheduled") {
    return (
      <Card className="border-none bg-secondary/50 shadow-none" data-testid="escrow-stage-panel">
        <CardContent className="p-4 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Lock className="w-4 h-4 text-accent flex-shrink-0" />
            {viewerRole === "customer"
              ? `${amount} is securely held in Escrow — waiting for the ${otherRoleLabel} to mark the hearing conducted.`
              : `${amount} is securely held in Escrow. Once the hearing takes place, mark it conducted to unlock Order Sheet upload.`}
          </div>
          {canMarkConducted && (
            <Button type="button" onClick={onMarkConducted} disabled={markingConducted} className="bg-accent hover:bg-accent/90 font-bold" data-testid="mark-hearing-conducted">
              {markingConducted && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />} Mark Hearing Conducted
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  if (hearing.status === "hearing_completed") {
    return (
      <Card className="border-l-4 border-l-orange-400 shadow-md" data-testid="escrow-stage-panel">
        <CardContent className="p-6">
          <div className="flex items-center gap-1.5 text-2xs font-bold uppercase tracking-wide text-orange-700 bg-orange-100 rounded-full px-2.5 py-1 w-fit mb-3">
            <Lock className="w-3.5 h-3.5" /> Escrow Held
          </div>
          {viewerRole === "counsel" ? (
            <>
              <p className="text-sm font-semibold mb-3">
                {amount} is securely held in Escrow. Payment will only be released after you upload the Court Order
                Sheet and the {otherRoleLabel} verifies the hearing.
              </p>
              <input ref={fileInputRef} type="file" className="text-xs mb-2 w-full" />
              <Button type="button" className="w-full font-bold bg-accent hover:bg-accent/90" disabled={busy} onClick={uploadOrderSheet} data-testid="upload-order-sheet">
                {busy && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />} <Upload className="w-4 h-4 mr-1.5" /> Upload Order Sheet
              </Button>
            </>
          ) : (
            <p className="text-sm font-semibold">
              {amount} is securely held in Escrow — waiting for the Proxy Counsel to upload the Court Order Sheet.
            </p>
          )}
        </CardContent>
      </Card>
    );
  }

  if (hearing.status === "verification_pending") {
    return (
      <>
      <Card className="border-l-4 border-l-orange-400 shadow-md" data-testid="escrow-stage-panel">
        <CardContent className="p-6">
          {viewerRole === "customer" ? (
            <>
              <div className="cb-overline text-accent mb-2">Review Submission</div>
              <p className="text-sm text-muted-foreground mb-3">
                The Proxy Counsel uploaded the Court Order Sheet for {amount} held in Escrow. Review it, then verify
                the hearing to release payment, or raise a dispute if something's wrong.
              </p>
              {hearing.order_sheet_doc_id && (
                <button type="button" onClick={viewOrderSheet} className="flex items-center gap-2 text-sm border rounded-md px-2.5 py-1.5 hover:bg-slate-50 mb-3" data-testid="view-order-sheet">
                  <FileText className="w-4 h-4 text-accent flex-shrink-0" /> Preview Court Order Sheet
                </button>
              )}
              <p className="text-xs text-muted-foreground mb-3">
                If you neither verify nor raise a dispute within {AUTO_RELEASE_DAYS} days of the order sheet being
                uploaded, payment auto-releases to the Proxy Counsel.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <Button type="button" className="font-bold bg-accent hover:bg-accent/90" disabled={busy} onClick={submitVerifyAndRelease} data-testid="verify-hearing">
                  {busy && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />} <CheckCircle2 className="w-4 h-4 mr-1.5" /> Verify Hearing
                </Button>
                <Dialog open={disputeOpen} onOpenChange={setDisputeOpen}>
                  <DialogTrigger asChild>
                    <Button type="button" variant="outline" className="font-bold text-red-600 border-red-200 hover:bg-red-50" disabled={busy} data-testid="raise-dispute">
                      <ShieldAlert className="w-4 h-4 mr-1.5" /> Raise Dispute
                    </Button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>Raise a dispute?</DialogTitle>
                      <DialogDescription>
                        This sends the hearing to CourtBazaar admin for review instead of releasing payment. Explain
                        what's wrong with the submission.
                      </DialogDescription>
                    </DialogHeader>
                    <Textarea rows={3} value={remark} onChange={(e) => setRemark(e.target.value)} placeholder="What's wrong with this submission?" />
                    <DialogFooter>
                      <Button type="button" variant="outline" onClick={() => setDisputeOpen(false)} disabled={busy}>Cancel</Button>
                      <Button type="button" onClick={submitDispute} disabled={busy} className="bg-red-600 hover:bg-red-700 text-white font-bold" data-testid="confirm-raise-dispute">
                        {busy && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />} Raise Dispute
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              </div>
            </>
          ) : (
            <>
              <p className="text-sm font-semibold mb-3">
                Order sheet submitted — waiting for the {otherRoleLabel} to verify. {amount} is securely held in Escrow,
                and auto-releases to you in {AUTO_RELEASE_DAYS} days if the {otherRoleLabel} takes no action.
              </p>
              {hearing.order_sheet_doc_id && (
                <button type="button" onClick={viewOrderSheet} className="flex items-center gap-2 text-sm border rounded-md px-2.5 py-1.5 hover:bg-slate-50" data-testid="view-order-sheet">
                  <FileText className="w-4 h-4 text-accent flex-shrink-0" /> Preview Court Order Sheet
                </button>
              )}
            </>
          )}
        </CardContent>
      </Card>
      <DocumentPreviewDialog
        open={!!preview}
        onOpenChange={(v) => { if (!v) setPreview(null); }}
        url={preview?.url}
        filename={preview?.filename}
      />
      </>
    );
  }

  if (hearing.status === "disputed") {
    return (
      <>
      <Card className="border-none bg-red-50 shadow-none" data-testid="escrow-stage-panel">
        <CardContent className="p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-red-800">
            <ShieldAlert className="w-4 h-4 flex-shrink-0" />
            {viewerRole === "customer"
              ? "Your dispute is under review by CourtBazaar admin. Escrow remains held until it's resolved."
              : "Your submission was disputed and is under review by CourtBazaar admin. Escrow remains held until it's resolved."}
          </div>
          {hearing.order_sheet_doc_id && (
            <button type="button" onClick={viewOrderSheet} className="flex items-center gap-2 text-sm border rounded-md px-2.5 py-1.5 hover:bg-white bg-white/60 mt-3" data-testid="view-order-sheet">
              <FileText className="w-4 h-4 text-accent flex-shrink-0" /> Preview Court Order Sheet
            </button>
          )}
        </CardContent>
      </Card>
      <DocumentPreviewDialog
        open={!!preview}
        onOpenChange={(v) => { if (!v) setPreview(null); }}
        url={preview?.url}
        filename={preview?.filename}
      />
      </>
    );
  }

  if (hearing.status === "verified") {
    return (
      <Card className="border-none bg-emerald-50 shadow-none" data-testid="escrow-stage-panel">
        <CardContent className="p-4 flex items-center gap-2 text-sm font-semibold text-emerald-800">
          <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> Verified — payout release is next.
        </CardContent>
      </Card>
    );
  }

  // completed / rated
  return (
    <Card className="border-none bg-emerald-50 shadow-none" data-testid="escrow-stage-panel">
      <CardContent className="p-4 flex items-center gap-2 text-sm font-semibold text-emerald-800">
        <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
        {viewerRole === "customer"
          ? `Escrow released — ${amount} paid to the ${otherRoleLabel}.`
          : `Escrow released — ${amount} has been paid to your wallet.`}
      </CardContent>
    </Card>
  );
}
