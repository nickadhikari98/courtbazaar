import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("react-router/dom", () => {
  const { TextEncoder, TextDecoder } = require("util");
  Object.assign(global, { TextEncoder, TextDecoder });
  return require("react-router/dist/development/dom-export.js");
}, { virtual: true });
jest.mock("@/lib/api", () => ({
  api: { post: jest.fn(), get: jest.fn(), patch: jest.fn(), delete: jest.fn() },
  getErrorMessage: (_error, fallback) => fallback,
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() } }));
const mockUser = { user_id: "u1", name: "Jay Dee" };
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: mockUser }) }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { act } = React;
const { api } = require("@/lib/api");
const ChatSidebar = require("./ChatSidebar").default;
const { shortList } = require("./ChatSidebar");
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
  expect(headers).toEqual(["Pinned", "Recents"]); // date headers live in the palette
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
  expect(headings).toEqual(["Pinned", "Today"]);
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

async function renderChatWith(list) {
  api.get.mockImplementation((url, opts) => Promise.resolve({
    data: url === "/ai/chats" ? (opts?.params?.archived ? [] : list)
      : [{ role: "user", content: "Hi" }, { role: "assistant", content: "Hello there." }],
  }));
  await act(async () => root.render(<MemoryRouter><InstantLegalHelpChat /></MemoryRouter>));
  await flush();
}
const rowTitles = () => all("chat-row").map((r) => r.textContent);
async function chooseDelete(index) {
  await openRowMenu(index);
  act(() => $("chat-row-delete").click());
  await flush();
}

test("Delete asks first: Cancel keeps the chat, Delete removes it without a reload and leaves the open chat", async () => {
  await renderChatWith([RECENT, OTHER]);
  act(() => all("chat-row")[1].querySelector("button").click()); // open "Emergency arbitrator"
  await flush();
  expect(document.body.textContent).toContain("Hello there.");

  await chooseDelete(0);
  const dialog = document.querySelector('[role="dialog"]');
  expect(dialog.textContent).toContain("Delete chat?");
  expect(dialog.textContent).toContain("This chat will be permanently deleted. This can't be undone.");
  const button = (label) => [...document.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent.trim() === label);
  act(() => button("Cancel").click());
  await flush();
  expect(api.delete).not.toHaveBeenCalled();
  expect(rowTitles()).toEqual(["Cheque bounce notice", "Emergency arbitrator"]);

  api.delete.mockResolvedValue({ data: { ok: true } });
  api.get.mockClear();
  await chooseDelete(1); // the open chat
  await act(async () => button("Delete").click());
  await flush();
  expect(api.delete).toHaveBeenCalledWith("/ai/chats/c_other");
  expect(rowTitles()).toEqual(["Cheque bounce notice"]);
  expect(api.get).not.toHaveBeenCalledWith("/ai/chats"); // removed in place, no reload
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  expect($("instant-legal-help-empty")).not.toBeNull(); // the open chat was deleted: a new empty chat
});

test("a failed delete shows an error toast and keeps the chat", async () => {
  const { toast } = require("sonner");
  await renderChatWith([RECENT]);
  api.delete.mockRejectedValue(new Error("boom"));
  await chooseDelete(0);
  const del = [...document.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent.trim() === "Delete");
  await act(async () => del.click());
  await flush();
  expect(toast.error).toHaveBeenCalledWith("Couldn't delete that chat. Please try again.");
  expect(rowTitles()).toEqual(["Cheque bounce notice"]);
});

test("the header search button opens the same palette with the field focused; guests get New chat but no search", async () => {
  api.get.mockImplementation((url, opts) => Promise.resolve({
    data: url === "/ai/chats" ? (opts?.params?.archived ? [] : [PINNED, RECENT]) : [],
  }));
  await act(async () => root.render(<MemoryRouter><InstantLegalHelpChat /></MemoryRouter>));
  await flush();
  const search = $("chat-header-search");
  expect(search.getAttribute("aria-label")).toBe("Search chats");
  expect($("chat-header-new").getAttribute("aria-label")).toBe("New chat");
  for (const b of [search, $("chat-header-new"), $("chat-sidebar-open")]) {
    expect(b.className).toContain("h-10 w-10"); // 40x40 touch targets
  }
  act(() => search.click());
  await flush();
  expect(document.querySelector('[role="dialog"]')).not.toBeNull();
  expect(document.activeElement).toBe($("chat-palette-input"));
  // Below 768px it is a full-screen sheet with a back arrow.
  expect($("chat-palette").className).toContain("max-md:h-[100dvh]");
  act(() => $("chat-palette-back").click());
  await flush();
  expect(document.querySelector('[role="dialog"]')).toBeNull();
});

const chat = (n, extra = {}) => ({ conversation_id: `c${n}`, title: `Chat ${n}`, updated_at: NOW, pinned: false, archived: false, ...extra });

test("shortList keeps the first five and the open chat", () => {
  const list = [1, 2, 3, 4, 5, 6, 7].map((n) => chat(n));
  expect(shortList(list, "c2").shown.map((c) => c.conversation_id)).toEqual(["c1", "c2", "c3", "c4", "c5"]);
  expect(shortList(list, "c7").shown.map((c) => c.conversation_id)).toEqual(["c1", "c2", "c3", "c4", "c5", "c7"]);
  expect(shortList(list, null).cut).toBe(true);
  expect(shortList(list.slice(0, 5), null).cut).toBe(false);
});

test("the sidebar shows at most 5 pinned and 5 recents, keeps the open chat, and View all opens the full palette", async () => {
  const pinned = [1, 2, 3, 4, 5, 6].map((n) => chat(n, { pinned: true }));
  const recents = [7, 8, 9, 10, 11, 12, 13].map((n) => chat(n));
  api.get.mockImplementation((url, opts) => Promise.resolve({
    data: url === "/ai/chats" ? (opts?.params?.archived ? [ARCHIVED] : [...pinned, ...recents])
      : [{ role: "user", content: "Hi" }, { role: "assistant", content: "Hello." }],
  }));
  await act(async () => root.render(<MemoryRouter><InstantLegalHelpChat /></MemoryRouter>));
  await flush();
  expect(rowTitles()).toEqual(["Chat 1", "Chat 2", "Chat 3", "Chat 4", "Chat 5", "Chat 7", "Chat 8", "Chat 9", "Chat 10", "Chat 11"]);
  expect(all("chat-row-menu")).toHaveLength(10); // every row keeps its menu
  expect($("chat-sidebar-archived").textContent).toBe("Archived (1)");

  // Open "Chat 13" from the palette: it then stays in the sidebar although it's 7th.
  act(() => $("chat-sidebar-view-all").click());
  await flush();
  expect($("chat-palette-input").value).toBe("");
  expect(all("chat-palette-item")).toHaveLength(13);
  const target = all("chat-palette-item").find((i) => i.textContent === "Chat 13");
  act(() => target.click());
  await flush();
  expect(rowTitles()).toContain("Chat 13");
  expect(rowTitles()).toHaveLength(11);
});
