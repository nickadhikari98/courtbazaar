/* Task 12: the offer panel follows the server's negotiation state — only the
   other party can accept the active offer, an agreed negotiation offers no
   further actions, and when the server refuses an offer or an accept (stale,
   already agreed) the user sees why and the panel reloads the current state. */
import React from "react";
import { createRoot } from "react-dom/client";

jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn(), warning: jest.fn() } }));
jest.mock("@/lib/negotiationApi");
jest.mock("@/lib/hearingRequestsApi");

const { act } = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.ResizeObserver = globalThis.ResizeObserver || class { observe() {} unobserve() {} disconnect() {} };
const { toast } = require("sonner");
const negotiationApi = require("@/lib/negotiationApi");
const hearingApi = require("@/lib/hearingRequestsApi");
const NegotiationOfferPanel = require("@/components/negotiation/NegotiationOfferPanel").default;

const HEARING = { hearing_id: "hearing_t12", requesting_user_id: "user_client", target_advocate_id: "user_counsel",
  status: "requested", service_type: "proxy_counsel", negotiation_enabled: true };
const offer = (id, by, status, amount) => ({ offer_id: id, amount, note: null, status, proposed_by_user_id: by,
  proposed_by_role: by === "user_client" ? "customer" : "counsel", created_at: `2026-11-13T10:00:0${id.slice(-1)}+00:00` });
const OPEN = { negotiation_id: "neg_1", hearing_id: "hearing_t12", status: "open", current_offer_id: "offer_1",
  offers: [offer("offer_1", "user_client", "active", 2000)], timeline: [] };
const AGREED = { ...OPEN, status: "agreed", locked_amount: 2000, offers: [offer("offer_1", "user_client", "accepted", 2000)] };
const stale = (detail) => Object.assign(new Error("409"), { response: { status: 409, data: { detail } } });

let root, container, onChanged;
const mount = async (props) => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<NegotiationOfferPanel hearingId="hearing_t12" hearing={HEARING} onChanged={onChanged} {...props} />);
  });
};
const q = (testid) => document.querySelector(`[data-testid="${testid}"]`);
const click = async (el) => { await act(async () => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); }); };
const type = async (el, value) => {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value").set;
  await act(async () => { setter.call(el, value); el.dispatchEvent(new Event("input", { bubbles: true })); });
};
const actions = () => [...Object.values(negotiationApi), ...Object.values(hearingApi)]
  .filter((fn) => typeof fn === "function" && fn.mock).reduce((n, fn) => n + fn.mock.calls.length, 0);

beforeEach(() => { jest.clearAllMocks(); onChanged = jest.fn(); });
afterEach(async () => { await act(async () => { root.unmount(); }); container.remove(); });

test("the counsel can accept the client's active offer; the client who made it cannot", async () => {
  await mount({ negotiation: OPEN, viewerUserId: "user_client", viewerRole: "customer" });
  expect(q("accept-offer")).toBeNull();
  await act(async () => { root.unmount(); });
  container.remove();

  negotiationApi.acceptOffer.mockResolvedValue({});
  await mount({ negotiation: OPEN, viewerUserId: "user_counsel", viewerRole: "counsel" });
  await click(q("accept-offer"));
  expect(negotiationApi.acceptOffer).toHaveBeenCalledTimes(1);
  expect(negotiationApi.acceptOffer).toHaveBeenCalledWith("hearing_t12", "offer_1");
  expect(onChanged).toHaveBeenCalledTimes(1);
});

test("a refused accept shows the server's reason and reloads the negotiation", async () => {
  negotiationApi.acceptOffer.mockRejectedValue(stale("This offer is no longer the active one — refresh and try again"));
  await mount({ negotiation: OPEN, viewerUserId: "user_counsel", viewerRole: "counsel" });
  await click(q("accept-offer"));
  expect(toast.error).toHaveBeenCalledWith("This offer is no longer the active one — refresh and try again");
  expect(toast.success).not.toHaveBeenCalled();
  expect(onChanged).toHaveBeenCalledTimes(1);
  expect(q("accept-offer").disabled).toBe(false); // usable again once reloaded
});

test("a refused counter offer shows the server's reason, keeps the dialog and reloads", async () => {
  negotiationApi.proposeOffer.mockRejectedValue(stale("This negotiation changed while you were responding — refresh and try again"));
  await mount({ negotiation: OPEN, viewerUserId: "user_counsel", viewerRole: "counsel" });
  const negotiate = [...document.querySelectorAll("button")].find((b) => /negotiate/i.test(b.textContent));
  await click(negotiate);
  expect(q("offer-note-input").maxLength).toBe(1000);
  await type(q("offer-amount-input"), "2600");
  await click(q("submit-offer-modal"));
  expect(negotiationApi.proposeOffer).toHaveBeenCalledWith("hearing_t12", 2600, undefined);
  expect(toast.error).toHaveBeenCalledWith("This negotiation changed while you were responding — refresh and try again");
  expect(onChanged).toHaveBeenCalledTimes(1);
  expect(q("offer-amount-input")).not.toBeNull();
});

test("an amount of zero or less is never sent", async () => {
  await mount({ negotiation: OPEN, viewerUserId: "user_counsel", viewerRole: "counsel" });
  await click([...document.querySelectorAll("button")].find((b) => /negotiate/i.test(b.textContent)));
  for (const value of ["0", "-500", ""]) {
    await type(q("offer-amount-input"), value);
    await click(q("submit-offer-modal"));
  }
  expect(negotiationApi.proposeOffer).not.toHaveBeenCalled();
  expect(toast.error).toHaveBeenCalledTimes(3);
});

test.each([["customer", "user_client"], ["counsel", "user_counsel"]])(
  "an agreed negotiation shows the agreed fee and no offer actions (%s)", async (viewerRole, viewerUserId) => {
    await mount({ negotiation: AGREED, viewerUserId, viewerRole, hearing: { ...HEARING, commercially_locked: true, fee: 2000 } });
    expect(q("negotiation-agreed-amount").textContent).toContain("2,000");
    for (const id of ["accept-offer", "reject-offer", "submit-offer-modal", "offer-amount-input"]) expect(q(id)).toBeNull();
    expect([...document.querySelectorAll("button")].some((b) => /negotiate|propose|counter/i.test(b.textContent))).toBe(false);
    expect(actions()).toBe(0);
  });
