import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("react-router/dom", () => {
  const { TextEncoder, TextDecoder } = require("util");
  Object.assign(global, { TextEncoder, TextDecoder });
  return require("react-router/dist/development/dom-export.js");
}, { virtual: true });
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  api: { get: jest.fn(() => new Promise(() => {})), post: jest.fn() },
}));
jest.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ user: { user_id: "u1", name: "Jay Dee", role: "client", capabilities: ["can_hire_proxy_counsel"] }, logout: jest.fn() }),
}));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { act } = React;
const AppLayout = require("./AppLayout").default;

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
});

const $ = (testId) => container.querySelector(`[data-testid="${testId}"]`);

test("Instant Legal Help is a highlighted card right under Home, above Services, and stays a tinted square on the rail", () => {
  act(() => root.render(<MemoryRouter initialEntries={["/dashboard"]}><AppLayout><div /></AppLayout></MemoryRouter>));
  const card = $("nav-instant-legal-help");
  expect(card.getAttribute("href")).toBe("/legal-help");
  expect(card.textContent).toBe("Instant Legal HelpAsk a legal question");
  expect(card.className).toContain("bg-accent/5");
  expect(card.className).toContain("border-accent/50");
  expect(card.className).not.toContain("ring-1"); // not the current page

  // Order: Home, the card, then the Services heading; never inside Services.
  const nav = card.parentElement;
  const children = [...nav.children];
  expect(children.indexOf($("nav-home"))).toBe(children.indexOf(card) - 1);
  expect(children[children.indexOf(card) + 1].textContent).toBe("Services");
  expect(nav.querySelectorAll('[href="/legal-help"]')).toHaveLength(1);

  act(() => $("toggle-sidebar-btn").click()); // collapse to the 64px rail
  const square = $("nav-instant-legal-help");
  // It started expanded (the hint line above), so the toggle lands on the rail.
  expect(square.className).toContain("h-10");
  expect(square.textContent).toBe("");
  expect(square.getAttribute("title")).toBe("Instant Legal Help");
  expect(square.className).toContain("bg-accent/5");
});
