import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("react-router/dom", () => {
  const { TextEncoder, TextDecoder } = require("util");
  Object.assign(global, { TextEncoder, TextDecoder });
  return require("react-router/dist/development/dom-export.js");
}, { virtual: true });
jest.mock("@/lib/api", () => ({
  api: { post: jest.fn(), get: jest.fn(), patch: jest.fn() },
  getErrorMessage: (_error, fallback) => fallback,
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() } }));
const mockUser = { user_id: "u1", name: "Jay Dee" };
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: mockUser }) }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { act } = React;
const { api } = require("@/lib/api");
const ChatSidebar = require("./ChatSidebar").default;
const InstantLegalHelpChat = require("./InstantLegalHelpChat").default;

// cmdk and Radix need these in jsdom.
global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
Element.prototype.scrollIntoView = jest.fn();

const NOW = new Date().toISOString();
const PINNED = { conversation_id: "c_pin", title: "Seat of arbitration", updated_at: NOW, pinned: true, archived: false };
const RECENT = { conversation_id: "c_new", title: "Cheque bounce notice", updated_at: NOW, pinned: false, archived: false };
const OTHER = { conversation_id: "c_other", title: "Emergency arbitrator", updated_at: NOW, pinned: false, archived: false };
const ARCHIVED = { conversation_id: "c_old", title: "Old question", updated_at: NOW, pinned: false, archived: true };

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

const all = (testId) => [...document.querySelectorAll(`[data-testid="${testId}"]`)];
const $ = (testId) => document.querySelector(`[data-testid="${testId}"]`);
const key = (el, k, extra = {}) => act(() => {
  el.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true, ...extra }));
});
function setValue(el, value) {
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });

function renderSidebar(onUpdateChat = jest.fn()) {
  act(() => root.render(
    <MemoryRouter>
      <ChatSidebar user={mockUser} chats={[PINNED, RECENT]} archivedChats={[ARCHIVED]} onUpdateChat={onUpdateChat}
        onSelect={jest.fn()} onNewChat={jest.fn()} />
    </MemoryRouter>,
  ));
  return onUpdateChat;
}

async function openRowMenu(index) {
  key(all("chat-row-menu")[index], "Enter"); // Radix opens a menu from the keyboard too
  await flush();
}

test("pinned chats sit under a Pinned header above the date groups; Archived (n) opens the archived list", () => {
  renderSidebar();
  const headers = [...container.querySelectorAll('[data-testid="chat-sidebar-list"] .uppercase')].map((h) => h.textContent);
  expect(headers).toEqual(["Pinned", "Today"]);
  expect(all("chat-row").map((r) => r.textContent)).toEqual(["Seat of arbitration", "Cheque bounce notice"]);
  expect($("chat-sidebar-archived").textContent).toBe("Archived (1)");
  act(() => $("chat-sidebar-archived").click());
  expect(all("chat-row").map((r) => r.textContent)).toEqual(["Old question"]);
  act(() => $("chat-sidebar-archived-back").click());
  expect(all("chat-row")).toHaveLength(2);
});

test("the row menu pins and archives through onUpdateChat", async () => {
  const onUpdate = renderSidebar();
  await openRowMenu(0);
  expect($("chat-row-pin").textContent).toBe("Unpin");
  act(() => $("chat-row-pin").click());
  expect(onUpdate).toHaveBeenLastCalledWith("c_pin", { pinned: false });
  await openRowMenu(1);
  act(() => $("chat-row-archive").click());
  expect(onUpdate).toHaveBeenLastCalledWith("c_new", { archived: true });
});

test("Rename edits inline: Enter saves, Esc cancels", async () => {
  const onUpdate = renderSidebar();
  await openRowMenu(1);
  act(() => $("chat-row-rename-item").click());
  await flush();
  let input = $("chat-row-rename");
  expect(input.value).toBe("Cheque bounce notice");
  act(() => setValue(input, "  Section 138 notice "));
  key(input, "Enter");
  expect(onUpdate).toHaveBeenLastCalledWith("c_new", { title: "Section 138 notice" });
  expect($("chat-row-rename")).toBeNull();

  onUpdate.mockClear();
  await openRowMenu(1);
  act(() => $("chat-row-rename-item").click());
  await flush();
  input = $("chat-row-rename");
  act(() => setValue(input, "Discard me"));
  key(input, "Escape");
  expect($("chat-row-rename")).toBeNull();
  expect(onUpdate).not.toHaveBeenCalled();
});

test("Ctrl+K opens a keyboard-only palette: filter, arrows, Enter opens the chat, Esc closes", async () => {
  api.get.mockImplementation((url, opts) => Promise.resolve({
    data: url === "/ai/chats" ? (opts?.params?.archived ? [ARCHIVED] : [PINNED, RECENT, OTHER]) : [],
  }));
  await act(async () => root.render(<MemoryRouter><InstantLegalHelpChat /></MemoryRouter>));
  await flush();

  key(window, "k", { ctrlKey: true });
  await flush();
  const dialog = document.querySelector('[role="dialog"]');
  expect(dialog).not.toBeNull();
  const input = $("chat-palette-input");
  expect(input.placeholder).toBe("Search chats and saved answers");
  expect(document.activeElement).toBe(input); // focus moves into the dialog
  expect(dialog.textContent).toContain("Esc");
  const headings = [...dialog.querySelectorAll("[cmdk-group-heading]")].map((h) => h.textContent);
  expect(headings).toEqual(["Pinned", "Recent"]);
  expect(all("chat-palette-item").map((i) => i.textContent)).not.toContain("Old question"); // archived stay out

  act(() => setValue(input, "arbitra"));
  await flush();
  const visible = all("chat-palette-item").map((i) => i.textContent);
  expect(visible).toEqual(["Seat of arbitration", "Emergency arbitrator"]);

  key(input, "ArrowDown");
  key(input, "Enter");
  await flush();
  expect(api.get).toHaveBeenCalledWith("/ai/history/c_other");
  expect(document.querySelector('[role="dialog"]')).toBeNull();

  key(window, "k", { metaKey: true });
  await flush();
  key($("chat-palette-input"), "Escape");
  await flush();
  expect(document.querySelector('[role="dialog"]')).toBeNull();
});

test("updating a chat PATCHes it and reloads both lists", async () => {
  api.get.mockImplementation((url, opts) => Promise.resolve({
    data: url === "/ai/chats" ? (opts?.params?.archived ? [] : [RECENT]) : [],
  }));
  api.patch.mockResolvedValue({ data: {} });
  await act(async () => root.render(<MemoryRouter><InstantLegalHelpChat /></MemoryRouter>));
  await flush();
  api.get.mockClear();
  await openRowMenu(0);
  act(() => $("chat-row-pin").click());
  await flush();
  expect(api.patch).toHaveBeenCalledWith("/ai/chats/c_new", { pinned: true });
  expect(api.get).toHaveBeenCalledWith("/ai/chats");
  expect(api.get).toHaveBeenCalledWith("/ai/chats", { params: { archived: true } });
});
