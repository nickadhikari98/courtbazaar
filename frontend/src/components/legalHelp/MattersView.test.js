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
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() } }));
const mockUser = { user_id: "u1", name: "Jay Dee" };
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: mockUser }) }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { act } = React;
const { api } = require("@/lib/api");
const InstantLegalHelpChat = require("./InstantLegalHelpChat").default;

global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
global.IntersectionObserver = class { observe() {} disconnect() {} };
Element.prototype.scrollIntoView = jest.fn();

const NOW = new Date().toISOString();
const MATTER = { matter_id: "m1", name: "Sharma v. Rao", custom_instructions: "", chat_count: 1, updated_at: NOW };
const IN_MATTER = { conversation_id: "c1", title: "Interim relief", updated_at: NOW, pinned: false, archived: false, matter_id: "m1" };
const LOOSE = { conversation_id: "c2", title: "Cheque bounce", updated_at: NOW, pinned: false, archived: false, matter_id: null };

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

const $ = (id) => document.querySelector(`[data-testid="${id}"]`);
const all = (id) => [...document.querySelectorAll(`[data-testid="${id}"]`)];
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
const key = (el, k) => act(() => { el.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true })); });
function setValue(el, value) {
  const proto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}
const dialogButton = (label) => [...document.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent.trim() === label);

function mockApi({ matters = [MATTER], matterChats = [IN_MATTER] } = {}) {
  api.get.mockImplementation((url, opts) => Promise.resolve({
    data: url === "/ai/matters" ? matters
      : url === "/ai/chats" ? (opts?.params?.archived ? [] : opts?.params?.matter_id ? matterChats : [IN_MATTER, LOOSE])
        : url.startsWith("/ai/history") ? [{ role: "user", content: "Hi" }, { role: "assistant", content: "Hello." }] : [],
  }));
  api.put.mockResolvedValue({ data: {} });
  api.patch.mockResolvedValue({ data: {} });
  api.post.mockResolvedValue({ data: { matter_id: "m2", name: "New one", custom_instructions: "", chat_count: 0 } });
  api.delete.mockResolvedValue({ data: { ok: true, ungrouped: 1 } });
}
async function render(path = "/legal-help") {
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}><InstantLegalHelpChat /></MemoryRouter>));
  await flush();
}

test("the sidebar lists matters with chat counts, an empty state and + New matter", async () => {
  mockApi({ matters: [] });
  await render();
  expect($("chat-sidebar-no-matters").textContent).toBe("No matters yet.");
  act(() => root.unmount());
  root = createRoot(container);
  mockApi();
  await render();
  expect(all("chat-sidebar-matter").map((m) => m.textContent)).toEqual(["Sharma v. Rao1"]);
  act(() => $("chat-sidebar-new-matter").click());
  await flush();
  act(() => setValue($("name-dialog-input"), "New one"));
  await act(async () => $("name-dialog-save").click());
  await flush();
  expect(api.post).toHaveBeenCalledWith("/ai/matters", { name: "New one" });
});

test("a matter view: instructions with Edit, its chats, rename in place, and delete says the chats stay", async () => {
  mockApi();
  await render("/legal-help/matters/m1");
  expect($("matter-name").textContent).toBe("Sharma v. Rao");
  expect($("matter-instructions").textContent).toContain("Applies to all chats in this matter");
  expect($("matter-instructions-text").textContent).toBe("No instructions yet.");
  expect(all("recents-row-open")[0].textContent.startsWith("Interim relief")).toBe(true);

  act(() => $("matter-instructions-edit").click());
  act(() => setValue($("matter-instructions-input"), "Keep answers short."));
  await act(async () => $("matter-instructions-save").click());
  await flush();
  expect(api.patch).toHaveBeenCalledWith("/ai/matters/m1", { custom_instructions: "Keep answers short." });
  expect($("matter-instructions-input")).toBeNull();

  key($("matter-menu"), "Enter");
  await flush();
  act(() => $("matter-rename-item").click());
  await flush();
  act(() => setValue($("matter-rename"), "Sharma v. Rao (2026)"));
  key($("matter-rename"), "Enter");
  await flush();
  expect(api.patch).toHaveBeenLastCalledWith("/ai/matters/m1", { name: "Sharma v. Rao (2026)" });

  key($("matter-menu"), "Enter");
  await flush();
  act(() => $("matter-delete-item").click());
  await flush();
  expect(document.querySelector('[role="dialog"]').textContent).toContain("Its chats are kept and go back to your chat list.");
  await act(async () => dialogButton("Delete matter").click());
  await flush();
  expect(api.delete).toHaveBeenCalledWith("/ai/matters/m1");
  expect($("matter-view")).toBeNull();
});

test("a matter with no chats says so", async () => {
  mockApi({ matterChats: [] });
  await render("/legal-help/matters/m1");
  expect($("matter-empty")).not.toBeNull();
});

test("Move to matter from a chat row (existing or new matter); the header shows an open chat's matter", async () => {
  mockApi();
  await render();
  const looseMenu = () => all("chat-row").find((r) => r.textContent.startsWith("Cheque bounce")).querySelector('[data-testid="chat-row-menu"]');
  key(looseMenu(), "Enter");
  await flush();
  act(() => $("chat-row-move").click());
  await flush();
  expect($("move-dialog-remove")).toBeNull(); // not in a matter yet
  await act(async () => all("move-dialog-matter")[0].click());
  await flush();
  expect(api.put).toHaveBeenCalledWith("/ai/chats/c2/matter", { matter_id: "m1" });

  key(looseMenu(), "Enter");
  await flush();
  act(() => $("chat-row-move").click());
  await flush();
  act(() => $("move-dialog-new").click());
  await flush();
  act(() => setValue($("name-dialog-input"), "New one"));
  await act(async () => $("name-dialog-save").click());
  await flush();
  expect(api.post).toHaveBeenCalledWith("/ai/matters", { name: "New one" });
  expect(api.put).toHaveBeenLastCalledWith("/ai/chats/c2/matter", { matter_id: "m2" });

  act(() => all("chat-row").find((r) => r.textContent.startsWith("Interim relief")).querySelector("button").click());
  await flush();
  expect($("chat-title").textContent).toBe("Interim relief");
  expect($("chat-title-matter").textContent).toBe("Sharma v. Rao");
});
