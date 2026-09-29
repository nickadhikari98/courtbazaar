/* A4 — Practice → Pending Offers → Respond, and the Hearing Detail it opens
   for a counsel whose negotiation is switched off. Real HearingsTab and
   HearingDetailDialog; only the API/auth modules are mocked. */
import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";

import { HearingsTab } from "@/pages/workspace/Practice";
import HearingDetailDialog from "@/components/shared/HearingDetailDialog";
import {
  listHearingRequests, getHearingRequest, acceptHearingAtListedRate, rejectHearingRequest,
  listHearingMessages, listHearingDocuments,
} from "@/lib/hearingRequestsApi";

// react-router v7 publishes "react-router/dom" only through package.json
// "exports", which CRA's jest resolver doesn't read — point it at the file
// (and give it the TextEncoder jsdom lacks; this runs before it loads).
jest.mock("react-router/dom", () => {
  const { TextEncoder, TextDecoder } = require("util");
  Object.assign(global, { TextEncoder, TextDecoder });
  return require("react-router/dist/development/dom-export.js");
}, { virtual: true });
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: global.__testUser }) }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn(), warning: jest.fn() } }));
jest.mock("@/lib/hearingPayment", () => ({ payForHearing: jest.fn() }));
jest.mock("@/lib/hearingRequestsApi", () => ({
  listHearingRequests: jest.fn(),
  getHearingRequest: jest.fn(),
  acceptHearingRequest: jest.fn(),
  declineHearingRequest: jest.fn(),
  rejectHearingRequest: jest.fn(),
  cancelHearingRequest: jest.fn(),
  acceptHearingAtListedRate: jest.fn(),
  markHearingConducted: jest.fn(),
  rateHearingRequest: jest.fn(),
  addHearingNote: jest.fn(),
  listHearingMessages: jest.fn(),
  postHearingMessage: jest.fn(),
  listHearingDocuments: jest.fn(),
  uploadHearingDocument: jest.fn(),
  getHearingDocumentUrl: jest.fn(),
  submitHearingCaseDetails: jest.fn(),
}));

const { act } = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const COUNSEL = { user_id: "user_counsel", capabilities: ["can_practice_proxy_counsel"] };
const OTHER_COUNSEL = { user_id: "user_other_counsel", capabilities: ["can_practice_proxy_counsel"] };

// A fixed-price (negotiation off) offer has no fee until Accept; the backend
// attaches the listed rate Accept would lock (hearings._attach_listed_rates).
const offer = (negotiation_enabled, extra = {}) => ({
  hearing_id: `hearing_${negotiation_enabled}`,
  requesting_user_id: "user_client",
  target_advocate_id: COUNSEL.user_id,
  status: "requested",
  commercially_locked: false,
  negotiation_enabled,
  court_id: "court_tishazari",
  hearing_date: "2026-10-01",
  fee: negotiation_enabled === false ? null : 2500,
  ...(negotiation_enabled === false ? { listed_rate: 2500 } : {}),
  timeline: [],
  ...extra,
});
const RUPEES_2500 = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(2500);

let container;
let root;
let currentLocation;
function LocationProbe() {
  currentLocation = useLocation();
  return null;
}

beforeEach(() => {
  // CRA's jest config resets mock implementations before every test.
  listHearingMessages.mockResolvedValue([]);
  listHearingDocuments.mockResolvedValue([]);
  rejectHearingRequest.mockResolvedValue({ ok: true });
  acceptHearingAtListedRate.mockResolvedValue({ ok: true, fee: 2500 });
  global.__testUser = COUNSEL;
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
const buttonNamed = (label) => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === label);
const click = (el) => act(() => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); });

async function renderHearingsTab(hearings) {
  listHearingRequests.mockResolvedValue(hearings);
  getHearingRequest.mockImplementation((id) => Promise.resolve(hearings.find((h) => h.hearing_id === id)));
  act(() => root.render(
    <MemoryRouter initialEntries={["/practice"]}>
      <Routes>
        <Route path="*" element={<><HearingsTab /><LocationProbe /></>} />
      </Routes>
    </MemoryRouter>,
  ));
  await flush();
}

async function renderDialog(hearing) {
  getHearingRequest.mockResolvedValue(hearing);
  act(() => root.render(
    <MemoryRouter><HearingDetailDialog hearingId={hearing.hearing_id} open onOpenChange={() => {}} /></MemoryRouter>,
  ));
  await flush();
}

describe("negotiation ON — unchanged", () => {
  test("Respond opens the Negotiation Module", async () => {
    await renderHearingsTab([offer(true)]);
    await click(byTestId("respond-to-offer-hearing_true"));
    expect(currentLocation.pathname).toBe("/hearing-requests/hearing_true/negotiate");
    expect(getHearingRequest).not.toHaveBeenCalled(); // no detail dialog
  });

  test("a pre-toggle hearing with no negotiation_enabled field still negotiates", async () => {
    const legacy = offer(undefined);
    delete legacy.negotiation_enabled;
    await renderHearingsTab([legacy]);
    await click(byTestId("respond-to-offer-hearing_undefined"));
    expect(currentLocation.pathname).toBe("/hearing-requests/hearing_undefined/negotiate");
  });

  test("detail still offers Negotiate (counter-offer path) alongside Accept/Reject", async () => {
    await renderDialog(offer(true));
    expect(byTestId("fixed-price-offer")).toBeNull();
    expect(byTestId("negotiate-fee")).not.toBeNull();
    expect(byTestId("accept-listed-rate")).not.toBeNull();
    expect(buttonNamed("Reject")).toBeDefined();
  });
});

describe("negotiation OFF — Respond goes to Hearing Detail", () => {
  test("Respond does not navigate to /negotiate; it opens this hearing's detail", async () => {
    await renderHearingsTab([offer(false)]);
    expect(byTestId("pending-offer-hearing_false").textContent).toContain(RUPEES_2500); // card shows the listed rate
    await click(byTestId("respond-to-offer-hearing_false"));
    await flush();
    expect(currentLocation.pathname).toBe("/practice");
    expect(getHearingRequest).toHaveBeenCalledWith("hearing_false");
    expect(byTestId("listed-rate").textContent).toContain(RUPEES_2500);
    expect(byTestId("accept-listed-rate")).not.toBeNull();
    expect(buttonNamed("Reject")).toBeDefined();
    expect(byTestId("negotiate-fee")).toBeNull();
    expect(document.body.textContent).not.toMatch(/Negotiate|Counter/);
  });

  test("counsel with no pricing set is told so instead of a blank price", async () => {
    await renderDialog(offer(false, { listed_rate: null }));
    expect(byTestId("listed-rate")).toBeNull();
    expect(byTestId("fixed-price-offer").textContent).toContain("haven't set your pricing");
  });

  test("Accept calls the existing accept-at-listed-rate API after confirmation", async () => {
    await renderDialog(offer(false));
    await click(byTestId("accept-listed-rate"));
    expect(document.body.textContent).toContain(`listed rate of ${RUPEES_2500}`);
    const confirm = [...document.querySelectorAll('[role="alertdialog"] button, [role="dialog"] button')]
      .filter((b) => b.textContent.trim() === "Accept").pop();
    await click(confirm);
    await flush();
    expect(acceptHearingAtListedRate).toHaveBeenCalledWith("hearing_false");
  });

  test("Reject calls the existing reject API after confirmation", async () => {
    await renderDialog(offer(false));
    await click(buttonNamed("Reject"));
    const confirm = [...document.querySelectorAll("button")].filter((b) => b.textContent.trim() === "Reject").pop();
    await click(confirm);
    await flush();
    expect(rejectHearingRequest).toHaveBeenCalledWith("hearing_false");
  });
});

describe("authorization in the UI — only the targeted counsel gets actions", () => {
  test("another counsel viewing the same offer sees no Accept/Reject/Negotiate", async () => {
    global.__testUser = OTHER_COUNSEL;
    for (const neg of [false, true]) {
      await renderDialog(offer(neg));
      expect(byTestId("accept-listed-rate")).toBeNull();
      expect(buttonNamed("Reject")).toBeUndefined();
      expect(byTestId("negotiate-fee")).toBeNull();
    }
  });

  test("a fee-locked offer no longer offers Accept/Reject", async () => {
    await renderDialog(offer(false, { commercially_locked: true }));
    expect(byTestId("accept-listed-rate")).toBeNull();
    expect(buttonNamed("Reject")).toBeUndefined();
  });
});
