/* Admin Cancel & Refund (Task 3). Real panel + ConfirmDialog; only the API
   module and toasts are mocked. The backend is the authority for eligibility
   and race safety — these pin what the UI offers and how it reports results. */
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { toast } from "sonner";

import AdminCancelRefundPanel from "@/components/admin/AdminCancelRefundPanel";
import { adminCancelRefundState } from "@/lib/adminHearingCancel";
import { cancelHearingRequest, adminRetryEscrowRefund, adminListHearingRequests } from "@/lib/hearingRequestsApi";

jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), warning: jest.fn(), info: jest.fn(), message: jest.fn() } }));
jest.mock("@/lib/hearingRequestsApi", () => ({
  cancelHearingRequest: jest.fn(),
  adminRetryEscrowRefund: jest.fn(),
  adminListHearingRequests: jest.fn(),
}));

const { act } = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const RUPEES = (n) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(n);

const hearing = (extra = {}) => ({
  hearing_id: "hearing_paid1", requesting_user_id: "user_client1", court_id: "court_tishazari",
  hearing_date: "2026-10-01", status: "documents_shared", fee: 3000, ...extra,
});
const escrow = (extra = {}) => ({ escrow_id: "escrow_1", status: "held", amount: 3000, ...extra });

let container;
let root;
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.body.innerHTML = "";
});

const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
const byTestId = (id) => document.querySelector(`[data-testid="${id}"]`);
const click = (el) => act(() => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
const confirmButton = () => [...document.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent.trim() === "Cancel & Refund");

/* Holds hearing/escrow like the admin dialog does; onChanged "re-fetches" by
   applying `afterRefetch` — the state the backend would now return. */
function Harness({ initialHearing, initialEscrow, afterRefetch, onChangedSpy }) {
  const [state, setState] = useState({ hearing: initialHearing, escrow: initialEscrow });
  return (
    <AdminCancelRefundPanel
      hearing={state.hearing} escrow={state.escrow}
      onChanged={() => { onChangedSpy?.(); if (afterRefetch) setState(afterRefetch); }}
    />
  );
}
const render = (props) => act(() => root.render(<Harness {...props} />));

describe("eligibility", () => {
  test("1: eligible paid hearing (escrow held) shows Cancel & Refund", () => {
    render({ initialHearing: hearing(), initialEscrow: escrow() });
    expect(byTestId("admin-cancel-refund")).not.toBeNull();
    expect(byTestId("admin-escrow-status").textContent).toBe("Held in escrow");
  });

  test.each(["broadcast", "accepted", "preparation", "hearing_scheduled", "hearing_completed"])(
    "every paid cancellable status (%s) is eligible", (status) => {
      expect(adminCancelRefundState(hearing({ status }), escrow())).toBe("cancellable");
    });

  test("unpaid / payment_pending: no refund action, panel hidden", () => {
    for (const status of ["requested", "payment_pending"]) {
      render({ initialHearing: hearing({ status, fee: 1500 }), initialEscrow: null });
      expect(byTestId("admin-cancel-refund-panel")).toBeNull();
    }
  });

  test("4: already cancelled — no action", () => {
    render({ initialHearing: hearing({ status: "cancelled" }), initialEscrow: escrow({ status: "held" }) });
    expect(byTestId("admin-cancel-refund")).toBeNull();
  });

  test("5: already refunded — shown as refunded, no action", () => {
    render({ initialHearing: hearing({ status: "cancelled" }), initialEscrow: escrow({ status: "refunded", refund_attempts: 1, gateway_refund_id: "rfnd_1" }) });
    expect(byTestId("admin-escrow-status").textContent).toBe("Refunded to client");
    expect(byTestId("admin-cancel-refund")).toBeNull();
    expect(byTestId("admin-retry-refund")).toBeNull();
    expect(container.textContent).toContain("rfnd_1");
  });

  test("6: refund pending/processing — status shown, no cancel and no retry", () => {
    for (const status of ["refund_pending", "refund_processing"]) {
      render({ initialHearing: hearing({ status: "cancelled" }), initialEscrow: escrow({ status }) });
      expect(byTestId("admin-cancel-refund")).toBeNull();
      expect(byTestId("admin-retry-refund")).toBeNull();
      expect(container.textContent).toContain("already in progress");
    }
  });

  test("7: refund failed — failed state + error shown, only the existing Retry refund offered", () => {
    render({ initialHearing: hearing({ status: "cancelled" }), initialEscrow: escrow({ status: "refund_failed", refund_last_error: "invalid request sent", refund_attempts: 1 }) });
    expect(byTestId("admin-escrow-status").textContent).toBe("Refund failed — needs retry");
    expect(byTestId("admin-refund-error").textContent).toContain("invalid request sent");
    expect(byTestId("admin-retry-refund")).not.toBeNull();
    expect(byTestId("admin-cancel-refund")).toBeNull();
  });

  test("released / verification stages / disputed — no action", () => {
    expect(adminCancelRefundState(hearing({ status: "completed" }), escrow({ status: "released" }))).toBe("unavailable");
    for (const status of ["verification_pending", "verified", "disputed"]) {
      expect(adminCancelRefundState(hearing({ status }), escrow())).toBe("unavailable");
    }
    expect(adminCancelRefundState(hearing(), null)).toBe("unavailable"); // paid status but no escrow record
  });
});

describe("cancel & refund flow", () => {
  test("2: confirmation shows id, amount and the admin/refund warning", async () => {
    render({ initialHearing: hearing(), initialEscrow: escrow() });
    await click(byTestId("admin-cancel-refund"));
    const dialog = document.querySelector('[role="dialog"]').textContent;
    expect(dialog).toContain("hearing_paid1");
    expect(dialog).toContain(RUPEES(3000));
    expect(dialog).toContain("Admin action");
    expect(dialog).toContain("refunds");
    expect(dialog).toContain("Do this once");
    expect(cancelHearingRequest).not.toHaveBeenCalled(); // nothing happens until confirmed
  });

  test("3: confirm calls the existing cancel endpoint once, even on a double click, then shows the refreshed state", async () => {
    let resolve;
    cancelHearingRequest.mockImplementation(() => new Promise((r) => { resolve = r; }));
    const onChangedSpy = jest.fn();
    render({
      initialHearing: hearing(), initialEscrow: escrow(), onChangedSpy,
      afterRefetch: { hearing: hearing({ status: "cancelled" }), escrow: escrow({ status: "refund_processing", refund_attempts: 1, gateway_refund_id: "rfnd_2" }) },
    });
    await click(byTestId("admin-cancel-refund"));
    const btn = confirmButton();
    await click(btn);
    await click(btn); // second click while the first is in flight
    expect(cancelHearingRequest).toHaveBeenCalledTimes(1);
    expect(cancelHearingRequest).toHaveBeenCalledWith("hearing_paid1");
    expect(btn.disabled).toBe(true);
    await act(async () => { resolve({ ok: true, refund_status: "refund_processing" }); });
    await flush();
    expect(toast.success).toHaveBeenCalledWith("Hearing cancelled — refund accepted, awaiting bank processing");
    expect(onChangedSpy).toHaveBeenCalledTimes(1);
    expect(byTestId("admin-cancel-refund")).toBeNull();
    expect(byTestId("admin-escrow-status").textContent).toBe("Refund accepted — awaiting bank");
  });

  test("a refund_failed result is reported as a failure, never as refunded", async () => {
    cancelHearingRequest.mockResolvedValue({ ok: true, refund_status: "refund_failed" });
    render({ initialHearing: hearing(), initialEscrow: escrow() });
    await click(byTestId("admin-cancel-refund"));
    await click(confirmButton());
    await flush();
    expect(toast.error).toHaveBeenCalledWith("Hearing cancelled, but the refund failed — use Retry refund");
    expect(toast.success).not.toHaveBeenCalled();
  });

  test("8: unauthorized (403) shows the backend's error and no success", async () => {
    cancelHearingRequest.mockRejectedValue({ response: { status: 403, data: { detail: "Forbidden" } } });
    const onChangedSpy = jest.fn();
    render({ initialHearing: hearing(), initialEscrow: escrow(), onChangedSpy });
    await click(byTestId("admin-cancel-refund"));
    await click(confirmButton());
    await flush();
    expect(toast.error).toHaveBeenCalledWith("Forbidden");
    expect(toast.success).not.toHaveBeenCalled();
    expect(onChangedSpy).toHaveBeenCalled(); // re-fetch so the panel reflects reality
  });

  test("state changed elsewhere (400) — error shown, refetched state removes the action", async () => {
    cancelHearingRequest.mockRejectedValue({ response: { status: 400, data: { detail: "This request can no longer be cancelled" } } });
    render({
      initialHearing: hearing(), initialEscrow: escrow(),
      afterRefetch: { hearing: hearing({ status: "cancelled" }), escrow: escrow({ status: "refunded" }) },
    });
    await click(byTestId("admin-cancel-refund"));
    await click(confirmButton());
    await flush();
    expect(toast.error).toHaveBeenCalledWith("This request can no longer be cancelled");
    expect(byTestId("admin-cancel-refund")).toBeNull();
    expect(byTestId("admin-escrow-status").textContent).toBe("Refunded to client");
  });

  test("9: network failure shows an error and never a success", async () => {
    cancelHearingRequest.mockRejectedValue(new Error("Network Error"));
    render({ initialHearing: hearing(), initialEscrow: escrow() });
    await click(byTestId("admin-cancel-refund"));
    await click(confirmButton());
    await flush();
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.success).not.toHaveBeenCalled();
    expect(byTestId("admin-cancel-refund")).not.toBeNull(); // unchanged — still eligible
  });
});

describe("retry refund (existing endpoint)", () => {
  test("retry calls the existing escrow retry once and reports the real result", async () => {
    let resolve;
    adminRetryEscrowRefund.mockImplementation(() => new Promise((r) => { resolve = r; }));
    render({ initialHearing: hearing({ status: "cancelled" }), initialEscrow: escrow({ status: "refund_failed" }) });
    const btn = byTestId("admin-retry-refund");
    await click(btn);
    await click(btn);
    expect(adminRetryEscrowRefund).toHaveBeenCalledTimes(1);
    expect(adminRetryEscrowRefund).toHaveBeenCalledWith("escrow_1");
    await act(async () => { resolve({ status: "refund_failed", refund_last_error: "still bad" }); });
    await flush();
    expect(toast.error).toHaveBeenCalledWith("Refund still failing: still bad");
    expect(toast.success).not.toHaveBeenCalled();
  });
});

describe("Paid · active admin list", () => {
  test("merges the per-status admin lists for every paid cancellable status", async () => {
    const { listAdminHearingsForTab } = require("@/pages/admin/AdminHearingVerification");
    adminListHearingRequests.mockImplementation((s) => Promise.resolve(
      s === "broadcast" ? [{ hearing_id: "a", updated_at: "2026-09-01" }]
        : s === "hearing_scheduled" ? [{ hearing_id: "b", updated_at: "2026-09-05" }] : [],
    ));
    const list = await listAdminHearingsForTab("paid_active");
    expect(adminListHearingRequests.mock.calls.map((c) => c[0]).sort())
      .toEqual(["accepted", "broadcast", "documents_shared", "hearing_completed", "hearing_scheduled", "preparation"]);
    expect(list.map((h) => h.hearing_id)).toEqual(["b", "a"]);
    await listAdminHearingsForTab("cancelled");
    expect(adminListHearingRequests).toHaveBeenLastCalledWith("cancelled");
  });
});
