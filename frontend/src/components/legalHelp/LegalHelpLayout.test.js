import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("react-router/dom", () => {
  const { TextEncoder, TextDecoder } = require("util");
  Object.assign(global, { TextEncoder, TextDecoder });
  return require("react-router/dist/development/dom-export.js");
}, { virtual: true });
jest.mock("@/lib/api", () => ({
  api: { post: jest.fn(), get: jest.fn(() => Promise.resolve({ data: [] })) },
  getErrorMessage: (_error, fallback) => fallback,
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() } }));
let mockUser = null;
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: mockUser }) }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { act } = React;
const LegalHelp = require("@/pages/marketing/LegalHelp").default;

let container;
let root;
beforeEach(() => {
  // CRA resets mock implementations before each test.
  require("@/lib/api").api.get.mockImplementation((url) => Promise.resolve({
    data: url === "/ai/usage"
      ? { plan: "guest", messages_used: 1, messages_limit: 5, tokens_used: 10, tokens_limit: null, resets_at: "2026-11-18T00:00:00+05:30" }
      : [],
  }));
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  mockUser = null;
});

const $ = (testId) => container.querySelector(`[data-testid="${testId}"]`);
// The site footer (below the fold, guests only) keeps its own logo, as on every marketing page.
const logos = () => [...container.querySelectorAll('img[alt*="CourtBazaar"]')].filter((el) => !el.closest("footer"));

async function render() {
  await act(async () => root.render(<MemoryRouter initialEntries={["/legal-help"]}><LegalHelp /></MemoryRouter>));
}

test("guests keep the site nav and footer; the sidebar sits below the nav with no logo of its own", async () => {
  await render();
  expect(container.querySelector("nav.landing-nav")).not.toBeNull();
  expect(container.querySelector("footer")).not.toBeNull();
  expect($("chat-sidebar-logo")).toBeNull();
  expect($("chat-sidebar-back")).toBeNull();
  expect($("chat-sidebar-login")).not.toBeNull();
  expect($("chat-sidebar-usage")).not.toBeNull();
  // Guests have no saved chats: the phone bar carries only Chat and New, centred.
  expect([...$("chat-bottom-nav").querySelectorAll("button")].map((b) => b.textContent)).toEqual(["Chat", "New"]);
  expect($("chat-bottom-nav").firstChild.className).toContain("justify-center");
  const sidebar = $("chat-sidebar");
  // Below the sticky nav (z-40) on every width, so its Services menu opens on top.
  expect(sidebar.className).toContain("md:z-auto");
  expect(sidebar.className).toContain("top-[65px]");
  expect(sidebar.className).toContain("z-30");
  expect($("legal-help-main").className).toContain("h-[calc(100dvh-65px)]");
  expect(logos()).toHaveLength(1);
});

test("signed-in users get the full-screen app: no site nav or footer, one logo in the sidebar, Back to dashboard", async () => {
  mockUser = { user_id: "u1", name: "Jay Dee" };
  await render();
  expect(container.querySelector("nav.landing-nav")).toBeNull();
  expect(container.querySelector("footer")).toBeNull();
  const logo = $("chat-sidebar-logo");
  expect(logo).not.toBeNull();
  expect(logo.querySelector("a").getAttribute("href")).toBe("/");
  expect($("chat-sidebar-back").getAttribute("href")).toBe("/dashboard");
  expect($("chat-sidebar-back").textContent).toBe("Back to dashboard");
  // The back link sits above the user row.
  const back = $("chat-sidebar-back");
  expect(back.compareDocumentPosition($("chat-sidebar-user")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect($("chat-sidebar").className).toContain("inset-y-0");
  expect($("chat-sidebar").className).toContain("md:z-auto");
  expect(logos()).toHaveLength(1);
});
