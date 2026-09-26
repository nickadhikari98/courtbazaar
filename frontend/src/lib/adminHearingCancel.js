/* Admin "Cancel & Refund" (founder rule, B6): after payment the client can
   cancel only within 1 hour; after that only an admin can cancel + refund.
   The backend is the authority — PUT /hearing-requests/{id}/cancel lets an
   admin cancel any paid hearing and refunds through escrow.refund() (atomic,
   idempotent), and POST /admin/escrow-transactions/{escrow_id}/retry-refund
   recovers a failed refund. This only decides what the admin UI offers. */
import { PAID_CANCELLABLE_HEARING_STATUSES } from "@/lib/hearingLifecycle";

export const REFUND_IN_PROGRESS_STATUSES = ["refund_pending", "refund_processing"];

/* One of:
   - "cancellable":       paid, escrow still held — Cancel & Refund offered
   - "refund_in_progress": refund_pending / refund_processing — nothing to start
   - "refunded":          refund completed — nothing to start
   - "refund_failed":     offer the existing Retry refund, never a new cancel
   - "unavailable":       anything else (unpaid, released, verification stages,
                          disputed — which has its own Refund & cancel) */
export function adminCancelRefundState(hearing, escrow) {
  const escrowStatus = escrow?.status;
  if (escrowStatus === "refunded") return "refunded";
  if (escrowStatus === "refund_failed") return "refund_failed";
  if (REFUND_IN_PROGRESS_STATUSES.includes(escrowStatus)) return "refund_in_progress";
  if (hearing && PAID_CANCELLABLE_HEARING_STATUSES.includes(hearing.status) && escrowStatus === "held") {
    return "cancellable";
  }
  return "unavailable";
}

/* Toast after an admin cancel, from the refund_status the cancel endpoint
   returns — only ever says "refunded" when the refund actually completed. */
export function adminCancelResultMessage(result) {
  const s = result?.refund_status;
  if (s === "refunded") return { tone: "success", text: "Hearing cancelled — payment refunded to the client" };
  if (s === "refund_processing") return { tone: "success", text: "Hearing cancelled — refund accepted, awaiting bank processing" };
  if (s === "refund_failed") return { tone: "error", text: "Hearing cancelled, but the refund failed — use Retry refund" };
  if (s) return { tone: "warning", text: "Hearing cancelled — refund still in progress" };
  return { tone: "success", text: "Hearing cancelled" };
}
