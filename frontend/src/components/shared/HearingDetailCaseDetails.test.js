/* Case Details in the real HearingDetailDialog once a hearing has taken
   place: shown read-only (or an explanation), never the editable form. The
   backend also rejects the update (hearings.submit_case_details); this pins
   what the requester actually sees. */
import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

// react-router v7 publishes "react-router/dom" only through package.json
// "exports" — same shim as PracticeRespond.test.js.
jest.mock("react-router/dom", () => {
  const { TextEncoder, TextDecoder } = require("util");
  Object.assign(global, { TextEncoder, TextDecoder });
  return require("react-router/dist/development/dom-export.js");
}, { virtual: true });
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: global.__testUser }) }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn(), warning: jest.fn() } }));
jest.mock("@/lib/hearingPayment", () => ({ payForHearing: jest.fn() }));
jest.mock("@/lib/hearingRequestsApi", () => ({
  getHearingRequest: jest.fn(), getHearingEscrow: jest.fn(), listHearingMessages: jest.fn(), listHearingDocuments: jest.fn(),
  postHearingMessage: jest.fn(), addHearingNote: jest.fn(), uploadHearingDocument: jest.fn(), getHearingDocumentUrl: jest.fn(),
  submitHearingCaseDetails: jest.fn(), cancelHearingRequest: jest.fn(), acceptHearingRequest: jest.fn(),
  declineHearingRequest: jest.fn(), rejectHearingRequest: jest.fn(), acceptHearingAtListedRate: jest.fn(),
  markHearingConducted: jest.fn(), rateHearingRequest: jest.fn(), verifyAndReleaseHearing: jest.fn(),
}));

const { act } = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
// The case-details form uses Radix controls that need ResizeObserver, which
// jsdom doesn't provide.
globalThis.ResizeObserver = globalThis.ResizeObserver || class { observe() {} unobserve() {} disconnect() {} };
const api = require("@/lib/hearingRequestsApi");
const HearingDetailDialog = require("@/components/shared/HearingDetailDialog").default;

const CLIENT = { user_id: "user_client", role: "client", capabilities: ["can_hire_proxy_counsel"] };
const hearing = (extra) => ({
  hearing_id: "hearing_cd", requesting_user_id: CLIENT.user_id, proxy_counsel_user_id: "user_counsel",
  target_advocate_id: "user_counsel", court_id: "court_bombay_hc", hearing_date: "2026-10-01", fee: 1500,
  commercially_locked: true, payment_confirmed_at: "2026-09-20T10:00:00+00:00", timeline: [], hearing_notes: [],
  rated_by: [], request_details: { common: { case_title: "State v. Example" }, service_specific: {} },
  case_details: "Seek adjournment; client is travelling.", ...extra,
});

let container, root;
async function renderDialog(h) {
  global.__testUser = CLIENT;
  api.getHearingRequest.mockResolvedValue(h);
  api.getHearingEscrow.mockResolvedValue(null);
  api.listHearingMessages.mockResolvedValue([]);
  api.listHearingDocuments.mockResolvedValue([]);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<MemoryRouter><HearingDetailDialog hearingId={h.hearing_id} open onOpenChange={() => {}} /></MemoryRouter>);
  });
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}
afterEach(() => { act(() => root.unmount()); container.remove(); document.body.innerHTML = ""; jest.clearAllMocks(); });

const formShown = () => !!document.querySelector('[data-testid="case-details-title"]');
const text = () => document.body.textContent;

test("completed hearing with shared details: shown read-only, no form, no way to submit", async () => {
  await renderDialog(hearing({ status: "completed", details_submitted: true }));
  expect(text()).toContain("Seek adjournment; client is travelling.");
  expect(formShown()).toBe(false);
  expect(api.submitHearingCaseDetails).not.toHaveBeenCalled();
});

test("hearing already conducted without shared details: explanation instead of the form", async () => {
  await renderDialog(hearing({ status: "hearing_completed", details_submitted: false }));
  expect(formShown()).toBe(false);
  expect(text()).toContain("Case details were not shared before this hearing took place.");
});

test("paid hearing not yet held: the form is still offered (unchanged)", async () => {
  await renderDialog(hearing({ status: "hearing_scheduled", details_submitted: false }));
  expect(formShown()).toBe(true);
});

test("cancelled hearing: existing closed message unchanged", async () => {
  await renderDialog(hearing({ status: "cancelled", details_submitted: false }));
  expect(formShown()).toBe(false);
  expect(text()).toContain("Case details were not shared before this request was closed.");
});
