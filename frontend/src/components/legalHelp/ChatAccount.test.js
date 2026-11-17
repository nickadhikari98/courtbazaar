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

async function openMenuItem(testId) {
  key($("chat-sidebar-user"), "Enter");
  await flush();
  act(() => $(testId).click());
  await flush();
}
// Inside a container hidden below 768px (the pane, while the phone shows the nav).
const hiddenOnPhones = (el) => el.closest('[class*="max-md:hidden"]');
const tab = async (name) => { key($(`settings-tab-${name}`), "Enter"); await flush(); };

test("Settings is a centred modal (nav first on mobile); Account saves only after a change", async () => {
  mockAuth.user = USER;
  mockGets(FREE_USAGE);
  api.put.mockResolvedValue({ data: {} });
  await render();
  key($("chat-sidebar-user"), "Enter");
  await flush();
  const menu = [...document.querySelectorAll('[role="menuitem"]')].map((i) => i.textContent);
  expect(menu).toEqual([expect.stringMatching(/^Settings(Ctrl\+,|⌘,)$/), "Usage", "Language", "Get help", "Log out"]);
  expect($("chat-user-email").textContent).toBe("jay@example.com");
  act(() => $("chat-user-settings").click());
  await flush();

  const dialog = $("settings-dialog");
  expect(dialog.getAttribute("role")).toBe("dialog");
  expect(dialog.className).toContain("max-w-[900px]");
  expect(dialog.className).toContain("h-[80vh]");
  expect(dialog.className).toContain("max-md:h-[100dvh]"); // full-screen sheet on phones
  expect([...dialog.querySelectorAll('[role="tab"]')].map((t) => t.textContent))
    .toEqual(["Account", "Usage", "Appearance", "Language", "Notifications", "Privacy"]);
  // Opened from "Settings": on a phone the nav is the first screen.
  expect(hiddenOnPhones($("settings-back"))).not.toBeNull();

  expect($("settings-save").disabled).toBe(true);
  expect($("settings-email").readOnly).toBe(true);
  act(() => setValue($("settings-name"), "Jaydeep G"));
  expect($("settings-save").disabled).toBe(false);
  await act(async () => $("settings-save").click());
  await flush();
  expect(api.put).toHaveBeenCalledWith("/auth/profile", { name: "Jaydeep G" });

  await tab("notifications");
  expect($("settings-notif-whatsapp")).toBeNull(); // Email and SMS only
  act(() => $("settings-notif-sms").click());
  await flush();
  // WhatsApp has no toggle but keeps its saved value (the endpoint replaces the whole set).
  expect(api.put).toHaveBeenLastCalledWith("/notifications/prefs", { email: true, sms: true, whatsapp: true });

  act(() => $("settings-close").click());
  await flush();
  expect($("settings-dialog")).toBeNull();
  key(window, ","); // plain comma does nothing
  act(() => { window.dispatchEvent(new KeyboardEvent("keydown", { key: ",", ctrlKey: true, bubbles: true })); });
  await flush();
  expect($("settings-dialog")).not.toBeNull();
});

test("Usage opens on its pane with the endpoint's numbers and an Upgrade action for free users", async () => {
  mockAuth.user = USER;
  mockGets(FREE_USAGE);
  await render();
  await openMenuItem("chat-user-usage");
  const pane = $("settings-usage");
  expect(pane.textContent).toContain("PlanFree");
  expect(pane.textContent).toContain("Requests today12 / 30");
  expect(pane.textContent).toContain("Tokens today900 (no daily limit)");
  expect(pane.textContent).toMatch(/Resets at\d/);
  expect($("settings-upgrade").getAttribute("href")).toBe("/subscription");
  expect(hiddenOnPhones($("settings-back"))).toBeNull(); // straight to the pane on phones too
});

test("Language and transcript width are this user's preferences; the language goes out with each message", async () => {
  mockAuth.user = USER;
  mockGets(FREE_USAGE);
  api.post.mockResolvedValue({ data: { conversation_id: "c", reply: "Answer." } });
  await render();
  await openMenuItem("chat-user-language");
  act(() => $("settings-language-hi").click());
  await flush();
  expect(JSON.parse(localStorage.getItem("cb_chat_prefs:u1"))).toEqual({ width: "narrow", language: "hi" });
  await tab("appearance");
  act(() => $("settings-width-wide").click());
  await flush();
  act(() => $("settings-close").click());
  await flush();
  expect($("instant-legal-help-transcript").className).toContain("max-w-5xl");
  await send("Hello");
  expect(api.post).toHaveBeenLastCalledWith("/ai/chat", expect.objectContaining({ message: "Hello", language: "hi" }));
  localStorage.clear();
});

test("Privacy: Delete all chats asks first, then clears the list; account deletion points to support", async () => {
  mockAuth.user = USER;
  api.get.mockImplementation((url, opts) => Promise.resolve({
    data: url === "/ai/usage" ? FREE_USAGE
      : url === "/ai/chats" ? (opts?.params?.archived ? [] : [{ conversation_id: "c1", title: "Old chat", updated_at: new Date().toISOString() }])
        : [],
  }));
  api.delete.mockResolvedValue({ data: { deleted: 1 } });
  await render();
  expect(document.querySelectorAll('[data-testid="chat-row"]')).toHaveLength(1);
  await openMenuItem("chat-user-settings");
  await tab("privacy");
  expect($("settings-account-deletion").textContent).toBe("To delete your CourtBazaar account, write to support.");
  act(() => $("settings-delete-chats").click());
  await flush();
  expect(api.delete).not.toHaveBeenCalled();
  const confirm = [...document.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent.trim() === "Delete all");
  await act(async () => confirm.click());
  await flush();
  expect(api.delete).toHaveBeenCalledWith("/ai/chats");
  expect(document.querySelectorAll('[data-testid="chat-row"]')).toHaveLength(0);
});

test("preferences load from the account and save back to it; the browser copy is the fallback", async () => {
  mockAuth.user = USER;
  api.get.mockImplementation((url) => Promise.resolve({
    data: url === "/ai/usage" ? FREE_USAGE
      : url === "/ai/preferences" ? { answer_language: "hinglish", transcript_width: "wide", theme: "system" } : [],
  }));
  api.patch.mockResolvedValue({ data: {} });
  await render();
  expect(api.get).toHaveBeenCalledWith("/ai/preferences");
  expect($("instant-legal-help-transcript").className).toContain("max-w-5xl"); // from the account
  await openMenuItem("chat-user-language");
  expect($("settings-language-hinglish").getAttribute("aria-checked")).toBe("true");
  act(() => $("settings-language-en").click());
  await flush();
  expect(api.patch).toHaveBeenCalledWith("/ai/preferences", { answer_language: "en" });
  expect(JSON.parse(localStorage.getItem("cb_chat_prefs:u1")).language).toBe("en");
  localStorage.clear();
});

test("Account: display name and work type save through PUT /auth/profile; the photo uploads with its rules shown", async () => {
  mockAuth.user = { ...USER, display_name: "", work_type: "Advocate" };
  mockGets(FREE_USAGE);
  api.put.mockResolvedValue({ data: {} });
  api.post.mockResolvedValue({ data: { avatar_url: "https://signed.example/a.png" } });
  await render();
  await openMenuItem("chat-user-settings");
  expect(document.body.textContent).toContain("PNG, JPEG, or WebP, up to 10MB");
  expect($("settings-work-type").textContent).toBe("Advocate");
  expect($("settings-save").disabled).toBe(true);
  act(() => setValue($("settings-display-name"), "JD"));
  await act(async () => $("settings-save").click());
  await flush();
  expect(api.put).toHaveBeenCalledWith("/auth/profile", { display_name: "JD" }); // only what changed

  const input = $("settings-photo-input");
  const { toast } = require("sonner");
  Object.defineProperty(input, "files", { configurable: true, value: [new File(["x"], "me.gif", { type: "image/gif" })] });
  await act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
  expect(toast.error).toHaveBeenCalledWith("Profile photos must be PNG, JPEG, or WebP.");
  expect(api.post).not.toHaveBeenCalledWith("/auth/profile/avatar", expect.anything());
  Object.defineProperty(input, "files", { configurable: true, value: [new File(["x"], "me.webp", { type: "image/webp" })] });
  await act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
  await flush();
  expect(api.post).toHaveBeenCalledWith("/auth/profile/avatar", expect.any(FormData));
  expect(mockAuth.refresh).toHaveBeenCalled();
});

test("the welcome heading greets by the display name", async () => {
  mockAuth.user = { ...USER, display_name: "JD" };
  mockGets(FREE_USAGE);
  await render();
  expect($("instant-legal-help-empty").textContent).toContain("How can I help today, JD?");
});
