import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { formatINR, getErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Ban, RotateCcw, UserPlus } from "lucide-react";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import { cancelHearingRequest, adminRetryEscrowRefund, adminProposeReassignment } from "@/lib/hearingRequestsApi";
import { getPublicProxyCounsels } from "@/lib/advocateRecommendationsApi";
import { isEscalatedUnassignedHearing } from "@/lib/hearingLifecycle";
import { escrowStatusLabel, escrowStatusClasses } from "@/config/escrowStatus";
import { adminCancelRefundState, adminCancelResultMessage } from "@/lib/adminHearingCancel";

const TOAST = { success: toast.success, warning: toast.warning, error: toast.error };

/* Admin Cancel & Refund (founder rule, B6): once the client's 1-hour window
   has passed only an admin can cancel a paid hearing. Reuses the existing
   PUT /hearing-requests/{id}/cancel (admin-authorized, atomic, refunds via
   escrow.refund) and POST /admin/escrow-transactions/{id}/retry-refund — no
   separate refund path. `onChanged` re-fetches the hearing + escrow after
   every attempt, success or not, so the panel always shows the backend's
   actual state. */
export default function AdminCancelRefundPanel({ hearing, escrow, onChanged }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  // State updates aren't synchronous — a second click in the same tick
  // would still see busy=false. The ref closes that gap.
  const inFlight = useRef(false);
  const state = adminCancelRefundState(hearing, escrow);
  // Escalated paid targeted request (D3): propose a replacement for the
  // client to approve. The list is the same eligible pool the public listing
  // shows; the backend re-checks eligibility on propose and on approval.
  const escalated = isEscalatedUnassignedHearing(hearing);
  const [counselOptions, setCounselOptions] = useState(null);
  const [replacementId, setReplacementId] = useState("");
  useEffect(() => {
    if (!escalated || hearing.reassignment_proposal || counselOptions) return;
    getPublicProxyCounsels({ limit: 100 })
      .then(({ advocates }) => setCounselOptions(advocates.filter((a) => a.advocate_id !== hearing.target_advocate_id)))
      .catch(() => setCounselOptions([]));
  }, [escalated, hearing.reassignment_proposal, hearing.target_advocate_id, counselOptions]);

  if (state === "unavailable" && !escrow) return null;

  const guarded = async (fn) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    try {
      await fn();
    } finally {
      inFlight.current = false;
      setBusy(false);
      onChanged?.();
    }
  };

  const cancelAndRefund = () => guarded(async () => {
    try {
      const { tone, text } = adminCancelResultMessage(await cancelHearingRequest(hearing.hearing_id));
      TOAST[tone](text);
      setConfirming(false);
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not cancel this hearing"));
      setConfirming(false);
    }
  });

  const retryRefund = () => guarded(async () => {
    try {
      const result = await adminRetryEscrowRefund(escrow.escrow_id);
      if (result.status === "refunded") toast.success("Refund completed — refunded to client");
      else if (result.status === "refund_failed") toast.error(`Refund still failing${result.refund_last_error ? `: ${result.refund_last_error}` : ""}`);
      else toast.message(escrowStatusLabel(result.status));
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not retry the refund"));
    }
  });

  const proposeReplacement = () => guarded(async () => {
    try {
      await adminProposeReassignment(hearing.hearing_id, replacementId);
      toast.success("Replacement proposed — waiting for the client's approval");
      setReplacementId("");
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not propose this counsel"));
    }
  });

  const amount = escrow?.amount ?? hearing.fee;

  return (
    <div className="rounded-lg border p-4 space-y-2" data-testid="admin-cancel-refund-panel">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Cancellation &amp; refund</div>
        {escrow && (
          <Badge className={`${escrowStatusClasses(escrow.status)} border-0 font-bold text-2xs`} data-testid="admin-escrow-status">
            {escrowStatusLabel(escrow.status)}
          </Badge>
        )}
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <div><span className="text-muted-foreground">Hearing:</span> <span className="font-mono text-xs">{hearing.hearing_id}</span></div>
        <div><span className="text-muted-foreground">Status:</span> {hearing.status.replace(/_/g, " ")}</div>
        <div><span className="text-muted-foreground">Client:</span> <span className="font-mono text-xs">{hearing.requesting_user_id}</span></div>
        {amount != null && <div><span className="text-muted-foreground">Paid:</span> <span className="font-bold">{formatINR(amount)}</span></div>}
        {!!escrow?.refund_attempts && <div><span className="text-muted-foreground">Refund attempts:</span> {escrow.refund_attempts}</div>}
        {escrow?.gateway_refund_id && <div><span className="text-muted-foreground">Refund ID:</span> <span className="font-mono text-xs">{escrow.gateway_refund_id}</span></div>}
      </div>
      {state === "refund_failed" && escrow?.refund_last_error && (
        <p className="text-xs text-rose-700" data-testid="admin-refund-error">Last error: {escrow.refund_last_error}</p>
      )}
      {state === "refund_in_progress" && (
        <p className="text-xs text-muted-foreground">A refund is already in progress — nothing to start here. Stuck refunds can be retried from Reconciliation.</p>
      )}

      {escalated && (
        <div className="rounded-md bg-amber-50 border border-amber-200 p-3 space-y-2" data-testid="admin-escalation">
          <p className="text-xs">
            <b>Escalated:</b> the client&apos;s selected counsel{" "}
            {hearing.targeted_escalation_reason === "targeted_accept_timeout" ? "didn't accept within 24 hours" : "is no longer eligible"}.
            {" "}Propose a replacement (the client must approve) or cancel &amp; refund.
          </p>
          {hearing.reassignment_proposal ? (
            <p className="text-xs text-muted-foreground" data-testid="admin-proposal-pending">
              Awaiting the client&apos;s answer on {hearing.reassignment_proposal.counsel_name || hearing.reassignment_proposal.counsel_user_id}.
            </p>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Select value={replacementId} onValueChange={setReplacementId} disabled={busy || !counselOptions?.length}>
                <SelectTrigger className="w-64" aria-label="Replacement counsel" data-testid="admin-replacement-select">
                  <SelectValue placeholder={counselOptions?.length === 0 ? "No eligible counsel available" : "Choose a replacement counsel"} />
                </SelectTrigger>
                <SelectContent>
                  {(counselOptions || []).map((a) => (
                    <SelectItem key={a.advocate_id} value={a.advocate_id}>{a.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button type="button" variant="outline" disabled={busy || !replacementId} onClick={proposeReplacement}
                      className="font-bold" data-testid="admin-propose-replacement">
                <UserPlus className="w-4 h-4 mr-1.5" /> Propose to client
              </Button>
            </div>
          )}
        </div>
      )}

      {state === "cancellable" && (
        <Button type="button" variant="outline" disabled={busy} onClick={() => setConfirming(true)}
                className="font-bold text-red-600 border-red-200 hover:bg-red-50" data-testid="admin-cancel-refund">
          <Ban className="w-4 h-4 mr-1.5" /> Cancel &amp; Refund
        </Button>
      )}
      {state === "refund_failed" && (
        <Button type="button" variant="outline" disabled={busy} onClick={retryRefund} className="font-bold" data-testid="admin-retry-refund">
          <RotateCcw className="w-4 h-4 mr-1.5" /> {busy ? "Retrying…" : "Retry refund"}
        </Button>
      )}

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        busy={busy}
        title="Cancel & refund this hearing?"
        description={(
          <>
            Admin action on <b className="text-foreground font-mono">{hearing.hearing_id}</b> ({hearing.court_id}, {hearing.hearing_date}).
            {" "}This cancels the hearing and refunds <b className="text-foreground">{amount != null ? formatINR(amount) : "the held payment"}</b> to
            the client&apos;s original payment method. Clients can only cancel within 1 hour of payment; admins can at any time.
            Do this once — if the refund doesn&apos;t complete immediately it shows here as in progress or failed.
          </>
        )}
        confirmLabel="Cancel & Refund"
        confirmIcon={Ban}
        onConfirm={cancelAndRefund}
      />
    </div>
  );
}
