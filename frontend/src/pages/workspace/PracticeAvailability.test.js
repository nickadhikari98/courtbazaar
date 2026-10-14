/* My Practice → Availability (CourtBazaar meeting, 2026-10-13): edit in
   place, legacy clock-time rows, past slots, and failures that used to be
   silent. Real AvailabilityTab; only the API/toast modules are mocked. */
import React from "react";
import { createRoot } from "react-dom/client";

import { AvailabilityTab } from "@/pages/workspace/Practice";
import {
  listAvailabilitySlots, addAvailabilitySlot, updateAvailabilitySlot, removeAvailabilitySlot,
} from "@/lib/practiceApi";
import { toast } from "sonner";
import { getPracticeVisibility } from "@/lib/practiceApi";
import { searchCourts, getCourt } from "@/lib/referenceDataApi";

jest.mock("react-router/dom", () => {
  const { TextEncoder, TextDecoder } = require("util");
  Object.assign(global, { TextEncoder, TextDecoder });
  return require("react-router/dist/development/dom-export.js");
}, { virtual: true });
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: null }) }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn(), warning: jest.fn() } }));
jest.mock("@/lib/practiceApi", () => ({
  getPracticeProfile: jest.fn(),
  updatePracticeProfile: jest.fn(),
  listAvailabilitySlots: jest.fn(),
  addAvailabilitySlot: jest.fn(),
  updateAvailabilitySlot: jest.fn(),
  removeAvailabilitySlot: jest.fn(),
  getPracticePerformance: jest.fn(),
  getPracticeVisibility: jest.fn(),
}));
jest.mock("@/lib/referenceDataApi", () => ({
  searchCourts: jest.fn(),
  getCourt: jest.fn(),
}));

const { act } = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const localDate = (offsetDays) => {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toLocaleDateString("en-CA");
};
const FUTURE = localDate(10);
const PAST = localDate(-3);

const WEEKLY = {
  slot_id: "slot_weekly", kind: "recurring_weekly", day_of_week: 1, date: null,
  court_id: "court_delhi_hc", court_name: "Delhi High Court", court_known: true,
  start_time: "10 AM – 1 PM", end_time: null, is_past: false,
};
const LEGACY_PAST = {
  slot_id: "slot_legacy", kind: "holiday_block", day_of_week: null, date: PAST,
  court_id: null, start_time: "09:03", end_time: "18:03", is_past: true,
};
const CUSTOM = {
  slot_id: "slot_custom", kind: "custom_date", day_of_week: null, date: FUTURE,
  court_id: null, start_time: "Full Day", end_time: null, is_past: false,
};

let container;
let root;
beforeEach(() => {
  getPracticeVisibility.mockResolvedValue({ visible: true, checks: [] });
  getCourt.mockImplementation((id) => Promise.resolve({ court_id: id, name: id === "court_delhi_hc" ? "Delhi High Court" : id }));
  searchCourts.mockResolvedValue([{ court_id: "court_saket", name: "Saket District Court", type: "district" }]);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  jest.clearAllMocks();
});

const $ = (testId) => container.querySelector(`[data-testid="${testId}"]`);
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
async function renderTab(slots) {
  listAvailabilitySlots.mockResolvedValue(slots);
  await act(async () => root.render(<AvailabilityTab />));
  await flush();
}
function typeInto(input, value) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

async function pickCourt(query) {
  await act(async () => typeInto($("availability-court-search"), query));
  await act(async () => { await new Promise((r) => setTimeout(r, 350)); }); // search debounce
  const option = [...container.querySelectorAll("button")].find((b) => b.textContent.includes("Saket District Court"));
  await act(async () => option.click());
}

test("legacy clock-time rows show both ends, and past slots are marked and listed last", async () => {
  await renderTab([LEGACY_PAST, WEEKLY]);
  const rows = [...container.querySelectorAll('[data-testid^="availability-row-"]')];
  expect(rows.map((r) => r.dataset.testid)).toEqual(["availability-row-slot_weekly", "availability-row-slot_legacy"]);
  expect(rows[1].textContent).toContain("09:03 – 18:03");
  expect(rows[1].textContent).toContain("Past");
  expect(rows[0].textContent).not.toContain("Past");
  // A past slot can still be removed, but not edited.
  expect($("availability-edit-slot_legacy")).toBeNull();
  expect($("availability-remove-slot_legacy")).not.toBeNull();
});

test("editing a slot saves it in place via PUT instead of adding a new one", async () => {
  updateAvailabilitySlot.mockResolvedValue({ ...WEEKLY, court_id: "court_saket" });
  await renderTab([WEEKLY]);
  await act(async () => $("availability-edit-slot_weekly").click());
  expect(container.textContent).toContain("Edit availability");
  expect($("availability-submit").textContent).toBe("Save changes");
  await flush();
  expect(container.textContent).toContain("Delhi High Court"); // current court shown as a chip
  // Court is picked from search (a real court_id), not typed as free text.
  await pickCourt("Saket");
  await act(async () => $("availability-submit").click());
  await flush();
  expect(updateAvailabilitySlot).toHaveBeenCalledWith("slot_weekly", {
    kind: "recurring_weekly", day_of_week: 1, date: undefined, court_id: "court_saket", start_time: "10 AM – 1 PM",
  });
  expect(addAvailabilitySlot).not.toHaveBeenCalled();
  expect(listAvailabilitySlots).toHaveBeenCalledTimes(2); // reloaded after the save
  expect($("availability-submit").textContent).toBe("Add"); // back to add mode
});

test("a past date can't be submitted", async () => {
  await renderTab([CUSTOM]);
  await act(async () => $("availability-edit-slot_custom").click());
  const dateInput = $("availability-date");
  expect(dateInput.value).toBe(FUTURE);
  expect(dateInput.min).toBe(localDate(0));
  await act(async () => typeInto(dateInput, PAST));
  expect(container.textContent).toContain("This date has already passed");
  await act(async () => $("availability-submit").click());
  expect(updateAvailabilitySlot).not.toHaveBeenCalled();
  expect(toast.error).toHaveBeenCalledWith("That date has already passed. Pick today or a future date.");
});

test("editing a legacy clock-time slot requires picking a real time slot", async () => {
  await renderTab([{ ...LEGACY_PAST, date: FUTURE, is_past: false }]);
  await act(async () => $("availability-edit-slot_legacy").click());
  await act(async () => $("availability-submit").click());
  expect(updateAvailabilitySlot).not.toHaveBeenCalled();
  expect(toast.error).toHaveBeenCalledWith("Select a time slot");
});

test("save and remove failures are reported instead of failing silently", async () => {
  removeAvailabilitySlot.mockRejectedValue({ response: { data: { detail: "Slot not found" } } });
  await renderTab([WEEKLY]);
  await act(async () => $("availability-remove-slot_weekly").click());
  await flush();
  expect(toast.error).toHaveBeenCalledTimes(1);

  updateAvailabilitySlot.mockRejectedValue({ response: { status: 409, data: { detail: "You've already added this availability" } } });
  await act(async () => $("availability-edit-slot_weekly").click());
  await act(async () => $("availability-submit").click());
  await flush();
  expect(toast.error).toHaveBeenCalledTimes(2);
  expect($("availability-submit").textContent).toBe("Save changes"); // stays in edit mode to fix it
});

test("a failed load shows an error instead of spinning forever", async () => {
  listAvailabilitySlots.mockRejectedValue(new Error("network"));
  await act(async () => root.render(<AvailabilityTab />));
  await flush();
  expect(container.textContent).toContain("Couldn't load your availability");
});

test("visibility card lists why clients can't find the counsel", async () => {
  getPracticeVisibility.mockResolvedValue({
    visible: false,
    checks: [
      { key: "kyc_approved", ok: false, severity: "blocking", message: "Your KYC is still pending admin approval" },
      { key: "courts", ok: true, severity: "blocking", message: "Clients searching Delhi High Court can find you" },
      { key: "availability_pricing", ok: false, severity: "warning", message: "No price set for 2 PM – 5 PM" },
    ],
  });
  await renderTab([WEEKLY]);
  expect($("client-visibility-status").textContent).toBe("Clients can't find you yet");
  expect($("client-visibility-kyc_approved").textContent).toContain("KYC is still pending");
  expect($("client-visibility-availability_pricing")).not.toBeNull();
  expect($("client-visibility-courts")).toBeNull(); // passing checks aren't listed
});

test("visibility card is refreshed after the availability changes", async () => {
  removeAvailabilitySlot.mockResolvedValue({ ok: true });
  await renderTab([WEEKLY]);
  expect($("client-visibility-status").textContent).toBe("Clients can find you");
  expect(getPracticeVisibility).toHaveBeenCalledTimes(1);
  getPracticeVisibility.mockResolvedValue({
    visible: true,
    checks: [{ key: "availability_mode", ok: false, severity: "warning", message: "Available for hearings is off" }],
  });
  await act(async () => $("availability-remove-slot_weekly").click());
  await flush();
  expect(getPracticeVisibility).toHaveBeenCalledTimes(2);
  expect($("client-visibility-status").textContent).toBe("Clients can find you, with gaps");
});

test("a legacy free-text court is flagged and must be re-picked on edit", async () => {
  updateAvailabilitySlot.mockResolvedValue({});
  const legacy = { ...WEEKLY, slot_id: "slot_legacy_court", court_id: "Delhi High Court", court_name: "Delhi High Court", court_known: false };
  await renderTab([legacy]);
  expect($("availability-row-slot_legacy_court").textContent).toContain("Not a recognized court");
  await act(async () => $("availability-edit-slot_legacy_court").click());
  await act(async () => $("availability-submit").click());
  await flush();
  expect(updateAvailabilitySlot).toHaveBeenCalledWith("slot_legacy_court", expect.objectContaining({ court_id: undefined }));
});
