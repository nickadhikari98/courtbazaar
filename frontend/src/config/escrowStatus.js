/* Human-readable presentation of backend escrow statuses (escrow.py's
   ESCROW_TRANSITIONS). Single source for every admin screen that shows an
   escrow's status, so internal values like "refund_failed" never reach the
   UI as raw strings. Unknown statuses fall back to the raw value — the
   backend stays the source of truth. */

export const ESCROW_STATUS_META = {
  created: { label: "Payment initiated", tone: "neutral" },
  captured: { label: "Payment captured", tone: "neutral" },
  held: { label: "Held in escrow", tone: "info" },
  released: { label: "Released to counsel", tone: "success" },
  refund_pending: { label: "Refund in progress", tone: "warning" },
  refund_processing: { label: "Refund accepted — awaiting bank", tone: "warning" },
  refund_failed: { label: "Refund failed — needs retry", tone: "danger" },
  refunded: { label: "Refunded to client", tone: "success" },
};

export const ESCROW_TONE_CLASSES = {
  neutral: "bg-secondary text-foreground",
  info: "bg-blue-100 text-blue-700",
  success: "bg-emerald-100 text-emerald-700",
  warning: "bg-amber-100 text-amber-800",
  danger: "bg-rose-100 text-rose-700",
};

export function escrowStatusLabel(status) {
  return ESCROW_STATUS_META[status]?.label || status || "—";
}

export function escrowStatusClasses(status) {
  return ESCROW_TONE_CLASSES[ESCROW_STATUS_META[status]?.tone || "neutral"];
}

/* Mirrors escrow.retry_refund's claim: refund_failed / refund_processing,
   or a refund_pending claim the backend already reported as stale (the
   reconciliation endpoint only lists refund_pending once it is stale). */
export const RETRYABLE_REFUND_STATUSES = ["refund_failed", "refund_processing", "refund_pending"];

export function isRetryableRefund(status) {
  return RETRYABLE_REFUND_STATUSES.includes(status);
}
