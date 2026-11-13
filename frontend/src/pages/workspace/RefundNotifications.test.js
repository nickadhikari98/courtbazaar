/* Task 12: what the client is shown about a refund. The Notification Center
   lists the backend's refund notices as sent (initiated / completed / delayed),
   and the cancel toast only says "refunded" when the refund really completed. */
import React from "react";
import { createRoot } from "react-dom/client";
import { cancelResultMessage } from "@/lib/hearingLifecycle";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), put: jest.fn() } }));
jest.mock("@/pages/customer/NotificationPrefs", () => ({ NotificationPrefsCard: () => null }));

const { act } = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { api } = require("@/lib/api");
const Notifications = require("@/pages/workspace/Notifications").default;

const notice = (id, title, body, read_at = null) => ({ notification_id: id, title, body, read_at,
  event_type: "hearing_event", related_entity_id: "hearing_x", created_at: "2026-11-13T10:00:00+00:00" });
const FEED = [
  notice("n3", "Refund completed", "Your refund of Rs.1500 for the hearing at Tis Hazari has been completed and sent to your original payment method. It can take a few working days to show in your account."),
  notice("n2", "Refund delayed", "Your refund of Rs.1500 for the hearing at Tis Hazari could not be completed automatically. Our team is working on it and you do not need to do anything."),
  notice("n1", "Refund initiated", "Your refund of Rs.1500 for the hearing at Tis Hazari has been initiated and is being processed. We will let you know when it is completed.", "2026-11-13T10:05:00+00:00"),
];

let root, container;
beforeEach(async () => {
  jest.clearAllMocks();
  api.get.mockResolvedValue({ data: FEED });
  api.put.mockResolvedValue({ data: { ok: true } });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(<Notifications />); });
});
afterEach(async () => { await act(async () => { root.unmount(); }); container.remove(); });

test("the refund notices are listed with the backend's own wording", () => {
  expect(api.get).toHaveBeenCalledWith("/notifications");
  const text = container.textContent;
  for (const n of FEED) {
    expect(text).toContain(n.title);
    expect(text).toContain(n.body);
  }
  // Each notice appears once, and nothing on the page shows gateway ids.
  expect(text.split("Refund completed").length - 1).toBe(1);
  expect(text).not.toMatch(/rfnd_|pay_|order_|rzp_/);
});

test("unread refund notices are marked NEW and read once on click", async () => {
  expect(container.textContent.split("NEW").length - 1).toBe(2); // initiated was already read
  const completed = [...container.querySelectorAll("div")].find((d) => d.className.includes("cursor-pointer") && d.textContent.includes("Refund completed"));
  await act(async () => { completed.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
  await act(async () => { completed.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
  expect(api.put).toHaveBeenCalledTimes(1);
  expect(api.put).toHaveBeenCalledWith("/notifications/n3/read");
  expect(container.textContent.split("NEW").length - 1).toBe(1);
});

test.each([
  ["refunded", "success", /has been refunded/],
  ["refund_processing", "success", /refund initiated/],
  ["refund_failed", "warning", /couldn't be completed automatically/],
  ["refund_pending", "warning", /couldn't be completed automatically/],
])("cancel toast for refund status %s", (refund_status, tone, pattern) => {
  const message = cancelResultMessage({ ok: true, refund_status });
  expect(message.tone).toBe(tone);
  expect(message.text).toMatch(pattern);
  if (refund_status !== "refunded") expect(message.text).not.toMatch(/has been refunded/);
});

test("cancel toast without a payment mentions no refund", () => {
  expect(cancelResultMessage({ ok: true })).toEqual({ tone: "success", text: "Request cancelled" });
});

describe("admin dispute refund toast", () => {
  const { disputeRefundMessage } = require("@/pages/admin/AdminHearingVerification");
  test.each([
    ["refunded", /^Refunded & cancelled$/],
    ["refund_processing", /refund initiated/],
    ["refund_failed", /did not complete/],
    [undefined, /did not complete/],
  ])("refund status %s", (refund_status, pattern) => {
    const text = disputeRefundMessage({ ok: true, status: "cancelled", refund_status });
    expect(text).toMatch(pattern);
    if (refund_status !== "refunded") expect(text).not.toMatch(/^Refunded/);
  });
});
