import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router-dom";

jest.mock("react-router/dom", () => {
  const { TextEncoder, TextDecoder } = require("util");
  Object.assign(global, { TextEncoder, TextDecoder });
  return require("react-router/dist/development/dom-export.js");
}, { virtual: true });

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { act } = React;
const LandingNav = require("./LandingNav").default;

let container;
let root;
let currentLocation;
function LocationProbe() {
  currentLocation = useLocation();
  return null;
}

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

function renderNav(path = "/legal-help") {
  act(() => root.render(
    <MemoryRouter initialEntries={[path]}>
      <LocationProbe />
      <LandingNav showTourTab={false} />
    </MemoryRouter>,
  ));
}

const DESTINATIONS = [
  ["How It Works", "/", "#how"],
  ["Package Plans", "/", "#pricing"],
  ["Counsel / Proxy Counsel", "/", "#services"],
  ["Courts Coverage", "/", "#coverage"],
  ["About Us", "/about", ""],
  ["Contact Us", "/contact", ""],
];

// Desktop links are the first match; the mobile menu renders its own copies.
function linkByText(text, scope = container) {
  return [...scope.querySelectorAll("a")].find((a) => a.textContent.trim() === text);
}

// Returns false when the click was handled client-side (preventDefault),
// i.e. the browser would not do a full page load.
function click(el) {
  let notPrevented;
  act(() => {
    notPrevented = el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
  });
  return notPrevented;
}

test.each(DESTINATIONS)("desktop %s navigates from /legal-help without a page reload", (label, pathname, hash) => {
  renderNav("/legal-help");
  const link = linkByText(label);
  expect(link.getAttribute("href")).toBe(`${pathname}${hash}`);
  expect(click(link)).toBe(false);
  expect(currentLocation.pathname).toBe(pathname);
  expect(currentLocation.hash).toBe(hash);
});

test.each(DESTINATIONS)("mobile %s navigates and closes the menu", (label, pathname, hash) => {
  renderNav("/legal-help");
  act(() => container.querySelector("button.lg\\:hidden").click());
  const mobileMenu = container.querySelector("div.lg\\:hidden.border-t");
  expect(mobileMenu).not.toBeNull();
  expect(click(linkByText(label, mobileMenu))).toBe(false);
  expect(currentLocation.pathname).toBe(pathname);
  expect(currentLocation.hash).toBe(hash);
  expect(container.querySelector("div.lg\\:hidden.border-t")).toBeNull();
});

test("section links also work from the landing page itself", () => {
  renderNav("/");
  click(linkByText("Courts Coverage"));
  expect(currentLocation.pathname).toBe("/");
  expect(currentLocation.hash).toBe("#coverage");
});

test("clicking the same section link again yields a new location, so Landing re-scrolls", () => {
  renderNav("/");
  click(linkByText("How It Works"));
  const firstKey = currentLocation.key;
  click(linkByText("How It Works"));
  expect(currentLocation.hash).toBe("#how");
  expect(currentLocation.key).not.toBe(firstKey);
});
