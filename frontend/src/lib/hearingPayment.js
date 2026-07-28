import { createHearingPaymentOrder, verifyHearingPayment } from "./hearingRequestsApi";

/* Shared Razorpay wiring for a hearing payment — extracted from
   HearingDetailDialog.jsx's original inline payForHearing so
   NegotiationModule.jsx (paying with the negotiated/locked amount, once
   agreed) can reuse the exact same simulated-vs-real Razorpay branch
   instead of duplicating it. Behavior is unchanged from the original:
   HearingDetailDialog still drives its own `paying` state and toasts
   around this call exactly as before — this function only does the
   create-order/simulated-verify/real-Razorpay-checkout part.

   `onSuccess({ simulated })` fires once payment is actually confirmed — via
   the immediate simulated-verify branch, or via Razorpay's own `handler`
   callback for a real checkout (which fires on a later tick, after this
   function has already returned from opening the checkout modal — same
   fire-and-open control flow the original inline version had). */
export async function payForHearing(hearingId, hearing, user, { onSuccess } = {}) {
  const order = await createHearingPaymentOrder(hearingId);
  if (order.simulated) {
    await verifyHearingPayment(hearingId, { razorpay_order_id: order.razorpay_order_id });
    onSuccess?.({ simulated: true });
    return;
  }
  const rzp = new window.Razorpay({
    key: order.key_id,
    amount: order.amount,
    currency: "INR",
    name: "CourtBazaar™",
    description: `Hearing ${hearing.court_id}`,
    order_id: order.razorpay_order_id,
    handler: async (resp) => {
      await verifyHearingPayment(hearingId, resp);
      onSuccess?.({ simulated: false });
    },
    prefill: { name: user?.name, email: user?.email, contact: user?.phone },
    // eslint-disable-next-line no-restricted-syntax -- Razorpay SDK config object, not a Tailwind-styled element (same exception as OrderDetail.jsx's payRazorpay)
    theme: { color: "#D97706" },
  });
  rzp.open();
}
