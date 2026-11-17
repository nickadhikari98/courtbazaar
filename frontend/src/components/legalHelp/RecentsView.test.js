import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("react-router/dom", () => {
  const { TextEncoder, TextDecoder } = require("util");
  Object.assign(global, { TextEncoder, TextDecoder });
  return require("react-router/dist/development/dom-export.js");
}, { virtual: true });
jest.mock("@/lib/api", () => ({
  api: { get: jest.fn(), post: jest.fn() },
  getErrorMessage: (_error, fallback) => fallback,
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() } }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { act } = React;
const { api } = require("@/lib/api");
const RecentsView = require("./RecentsView").default;
const { relativeTime } = require("./RecentsView");

global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
let observers = [];
global.IntersectionObserver = class {
  constructor(cb) { this.cb = cb; observers.push(this); }
  observe() {} disconnect() { observers = observers.filter((o) => o !== this); }
};

let container;
let root;
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  observers = [];
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
const iso = (msAgo) => new Date(Date.now() - msAgo).toISOString();
const chat = (n, extra = {}) => ({ conversation_id: `c${n}`, title: `Chat ${n}`, updated_at: iso(n * 60000), pinned: false, archived: false, ...extra });

async function render(props = {}) {
  const handlers = { onOpen: jest.fn(), onNewChat: jest.fn(), onSearch: jest.fn(), onUpdate: jest.fn(), onDelete: jest.fn(), onBulkDone: jest.fn(), ...props };
  await act(async () => root.render(<MemoryRouter><RecentsView refreshKey={0} {...handlers} /></MemoryRouter>));
  await flush();
  return handlers;
}

test("relativeTime reads like 2 minutes ago, 4 days ago, then Nov 5", () => {
  const now = new Date(2026, 10, 17, 12, 0);
  expect(relativeTime(new Date(2026, 10, 17, 11, 58).toISOString(), now)).toBe("2 minutes ago");
  expect(relativeTime(new Date(2026, 10, 13, 12, 0).toISOString(), now)).toBe("4 days ago");
  expect(relativeTime(new Date(2026, 10, 5, 9, 0).toISOString(), now)).toBe("Nov 5");
  expect(relativeTime(new Date(2025, 10, 5, 9, 0).toISOString(), now)).toBe("Nov 5, 2025");
  expect(relativeTime("not a date", now)).toBe("");
});

test("Active and Archived tabs, pinned first with a badge, a skeleton while loading and an empty state", async () => {
  let resolve;
  api.get.mockImplementationOnce(() => new Promise((r) => { resolve = r; }));
  const h = await render();
  expect($("recents-loading")).not.toBeNull();
  await act(async () => resolve({ data: [chat(2), chat(1, { pinned: true })] }));
  await flush();
  expect(api.get).toHaveBeenCalledWith("/ai/chats", { params: { archived: false, limit: 30, offset: 0 } });
  const rows = all("recents-row-open");
  expect(rows[0].textContent).toBe("Chat 1Pinned1 minute ago");
  expect(rows[1].textContent).toBe("Chat 22 minutes ago");
  expect(all("chat-row-menu")).toHaveLength(2); // same ... menu as the sidebar
  act(() => rows[1].click());
  expect(h.onOpen).toHaveBeenCalledWith("c2");
  act(() => $("recents-search").click());
  expect(h.onSearch).toHaveBeenCalled();

  api.get.mockResolvedValueOnce({ data: [] });
  key($("recents-tab-archived"), "Enter");
  act(() => $("recents-tab-archived").dispatchEvent(new MouseEvent("mousedown", { bubbles: true })));
  await flush();
  expect(api.get).toHaveBeenLastCalledWith("/ai/chats", { params: { archived: true, limit: 30, offset: 0 } });
  expect($("recents-empty").textContent).toBe("No archived chats.");
});

test("scrolling to the end loads the next page", async () => {
  const page1 = Array.from({ length: 30 }, (_, i) => chat(i + 1));
  api.get.mockResolvedValueOnce({ data: page1 }).mockResolvedValueOnce({ data: [chat(31)] });
  await render();
  expect($("recents-more")).not.toBeNull();
  await act(async () => observers[observers.length - 1].cb([{ isIntersecting: true }]));
  await flush();
  expect(api.get).toHaveBeenLastCalledWith("/ai/chats", { params: { archived: false, limit: 30, offset: 30 } });
  expect(all("recents-row")).toHaveLength(31);
  expect($("recents-more")).toBeNull(); // a short page is the end
});

test("Select: checkboxes, a count, Archive in one request, Delete only after confirming", async () => {
  api.get.mockResolvedValue({ data: [chat(1), chat(2), chat(3)] });
  api.post.mockResolvedValue({ data: { changed: 2 } });
  const h = await render();
  act(() => $("recents-select").click());
  const checks = all("recents-row-check");
  expect(checks).toHaveLength(3);
  act(() => checks[0].click());
  act(() => all("recents-row-open")[2].click()); // in select mode a row click toggles too
  expect($("recents-count").textContent).toBe("2 selected");
  expect(h.onOpen).not.toHaveBeenCalled();

  await act(async () => $("recents-bulk-archive").click());
  await flush();
  expect(api.post).toHaveBeenCalledWith("/ai/chats/bulk", { action: "archive", ids: ["c1", "c3"] });
  expect(h.onBulkDone).toHaveBeenCalledWith("archive", ["c1", "c3"]);
  expect($("recents-actions")).toBeNull(); // select mode ends

  act(() => $("recents-select").click());
  act(() => all("recents-row-check")[1].click());
  act(() => $("recents-bulk-delete").click());
  await flush();
  expect(api.post).toHaveBeenCalledTimes(1); // nothing until confirmed
  const del = [...document.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent.trim() === "Delete");
  await act(async () => del.click());
  await flush();
  expect(api.post).toHaveBeenLastCalledWith("/ai/chats/bulk", { action: "delete", ids: ["c2"] });
});
