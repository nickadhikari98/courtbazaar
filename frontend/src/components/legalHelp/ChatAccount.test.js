import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("react-router/dom", () => {
  const { TextEncoder, TextDecoder } = require("util");
  Object.assign(global, { TextEncoder, TextDecoder });
  return require("react-router/dist/development/dom-export.js");
}, { virtual: true });
jest.mock("@/lib/api", () => ({
  api: { post: jest.fn(), get: jest.fn(), put: jest.fn(), patch: jest.fn(), delete: jest.fn() },
  getErrorMessage: (_error, fallback) => fallback,
}));
jest.mock("./chatStream", () => ({
  streamChat: (payload) => require("@/lib/api").api.post("/ai/chat", payload).then((r) => r.data),
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() } }));
jest.mock("@/components/legal/SupportTicketModal", () => ({ open }) => (open ? <div data-testid="support-modal" /> : null));
const mockAuth = { user: null, logout: jest.fn(), refresh: jest.fn() };
jest.mock("@/context/AuthContext", () => ({ useAuth: () => mockAuth }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { act } = React;
const { api } = require("@/lib/api");
const InstantLegalHelpChat = require("./InstantLegalHelpChat").default;
const { formatUsage } = require("./usage");

global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
Element.prototype.scrollIntoView = jest.fn();

const RESETS = "2026-11-18T00:00:00+00:00";
const FREE_USAGE = { plan: "free", messages_used: 12, messages_limit: 30, tokens_used: 900, tokens_limit: null, resets_at: RESETS };
const USER = { user_id: "u1", name: "Jay Dee", email: "jay@example.com", notif_prefs: { email: true, sms: false, whatsapp: true } };

let container;
let root;
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  mockAuth.user = null;
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.body.innerHTML = "";
});

const $ = (testId) => document.querySelector(`[data-testid="${testId}"]`);
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
const key = (el, k) => act(() => { el.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true })); });
function setValue(el, value) {
  const proto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

function mockGets(usage) {
  api.get.mockImplementation((url) => Promise.resolve({ data: url === "/ai/usage" ? usage : [] }));
}
async function render() {
  await act(async () => root.render(<MemoryRouter><InstantLegalHelpChat /></MemoryRouter>));
  await flush();
}
async function send(text) {
  await act(async () => setValue($("instant-legal-help-input"), text));
  await act(async () => $("instant-legal-help-send").click());
  await flush();
}

test("formatUsage only uses numbers the endpoint returned", () => {
  expect(formatUsage(null)).toBeNull();
  expect(formatUsage({ plan: "free" })).toBeNull(); // no numbers: nothing to show
  expect(formatUsage([])).toBeNull();
  const free = formatUsage(FREE_USAGE);
  expect(free.pill).toBe("18 left");
  expect(free.detail).toMatch(/^12 of 30 questions used today\. Resets at /);
  const paid = formatUsage({ plan: "paid", messages_used: 400, messages_limit: null, tokens_used: 5000, tokens_limit: 200000, resets_at: RESETS });
  expect(paid.pill).toBe("Unlimited");
  expect([paid.used, paid.limit]).toEqual([5000, 200000]);
});

test("the header pill and sidebar block read GET /ai/usage, and show nothing without it", async () => {
  mockGets(FREE_USAGE);
  await render();
  expect(api.get).toHaveBeenCalledWith("/ai/usage");
  expect($("chat-usage-pill").textContent).toMatch(/^18 left · resets /);
  expect($("chat-sidebar-usage").textContent).toMatch(/^Today's questions12 \/ 30Resets at /);

  act(() => root.unmount());
  root = createRoot(container);
  api.get.mockImplementation(() => Promise.reject(new Error("down")));
  await render();
  expect($("chat-usage-pill")).toBeNull();
  expect($("chat-sidebar-usage")).toBeNull();
});

test("a 429 shows the limit card: guests are asked to sign up, free users get the upgrade path", async () => {
  mockGets({ ...FREE_USAGE, plan: "guest", messages_used: 5, messages_limit: 5 });
  api.post.mockRejectedValueOnce({ response: { status: 429, data: { detail: "You've used today's 5 free questions. Sign up to continue.", reason: "guest" } } });
  await render();
  await send("one more");
  expect($("instant-legal-help-limit").textContent).toContain("5 free questions");
  expect($("instant-legal-help-limit-action").getAttribute("href")).toBe("/register");
  expect($("instant-legal-help-limit-action").textContent).toBe("Sign up to continue");
  expect(container.textContent).not.toContain("having trouble");

  act(() => root.unmount());
  root = createRoot(container);
  mockAuth.user = USER;
  api.post.mockRejectedValueOnce({ response: { status: 429, data: { detail: "You've used today's 30 questions.", reason: "free" } } });
  await render();
  await send("again");
  expect($("instant-legal-help-limit-action").getAttribute("href")).toBe("/subscription");
  expect($("instant-legal-help-limit-action").textContent).toBe("Upgrade");
});

test("the user row opens a menu with the email, Settings, Get help and Log out", async () => {
  mockAuth.user = USER;
  mockGets(FREE_USAGE);
  await render();
  expect($("chat-sidebar-user").textContent).toContain("JD · Free");
  key($("chat-sidebar-user"), "Enter");
  await flush();
  expect($("chat-user-email").textContent).toBe("jay@example.com");
  act(() => $("chat-user-help").click());
  await flush();
  expect($("support-modal")).not.toBeNull();

  key($("chat-sidebar-user"), "Enter");
  await flush();
  act(() => $("chat-user-logout").click());
  expect(mockAuth.logout).toHaveBeenCalled();
});

test("Settings: full-screen panes; Account saves the name through PUT /auth/profile, email is read-only; notifications use PUT /notifications/prefs", async () => {
  mockAuth.user = USER;
  mockGets(FREE_USAGE);
  api.put.mockResolvedValue({ data: {} });
  await render();
  key($("chat-sidebar-user"), "Enter");
  await flush();
  act(() => $("chat-user-settings").click());
  await flush();

  const dialog = $("settings-dialog");
  expect(dialog.getAttribute("role")).toBe("dialog");
  const tabs = [...dialog.querySelectorAll('[role="tab"]')].map((t) => t.textContent);
  expect(tabs).toEqual(["Account", "Plan and usage", "Appearance", "Language", "Notifications", "Privacy"]);
  expect($("settings-email").readOnly).toBe(true);
  expect($("settings-email").value).toBe("jay@example.com");

  act(() => setValue($("settings-name"), "Jaydeep G"));
  await act(async () => $("settings-save").click());
  await flush();
  expect(api.put).toHaveBeenCalledWith("/auth/profile", { name: "Jaydeep G" });
  expect(mockAuth.refresh).toHaveBeenCalled();

  act(() => $("settings-tab-plan").dispatchEvent(new MouseEvent("mousedown", { bubbles: true })));
  key($("settings-tab-plan"), "Enter");
  await flush();
  expect($("settings-plan").textContent).toContain("Current plan: Free");
  expect($("settings-plan").textContent).toContain("12 of 30 questions used today.");

  key($("settings-tab-notifications"), "Enter");
  await flush();
  act(() => $("settings-notif-sms").click());
  await flush();
  expect(api.put).toHaveBeenLastCalledWith("/notifications/prefs", { email: true, sms: true, whatsapp: true });

  act(() => $("settings-close").click());
  await flush();
  expect($("settings-dialog")).toBeNull();
});
