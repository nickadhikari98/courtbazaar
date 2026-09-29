import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("react-router/dom", () => {
  const { TextEncoder, TextDecoder } = require("util");
  Object.assign(global, { TextEncoder, TextDecoder });
  return require("react-router/dist/development/dom-export.js");
}, { virtual: true });
jest.mock("@/lib/api", () => ({
  api: { post: jest.fn() },
  getErrorMessage: (_error, fallback) => fallback,
}));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || jest.fn();
const { act } = React;
const { api } = require("@/lib/api");
const HeroSection = require("./HeroSection").default;

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
  jest.clearAllMocks();
});

test("landing page exposes the chatbot trigger and opens/closes its panel", () => {
  act(() => root.render(<MemoryRouter><HeroSection /></MemoryRouter>));
  expect(container.querySelector('[data-testid="instant-legal-help-launcher"]')).not.toBeNull();
  expect(container.querySelector('[data-testid="instant-legal-help-launcher"]').textContent).toBe("Chat with Instant Legal Help →");
  expect(container.querySelector('[data-testid="instant-legal-help-trigger-input"]').placeholder)
    .toBe("Describe your situation, legal issue, or service need...");
  expect(container.querySelector('[data-testid="instant-legal-help-panel"]')).toBeNull();
  act(() => container.querySelector('[data-testid="instant-legal-help-launcher"]').click());
  expect(container.querySelector('[data-testid="instant-legal-help-panel"]')).not.toBeNull();
  act(() => container.querySelector('[data-testid="instant-legal-help-close"]').click());
  expect(container.querySelector('[data-testid="instant-legal-help-panel"]')).toBeNull();
});

test("typed launcher text is sent when the chat opens", async () => {
  api.post.mockResolvedValue({ data: { conversation_id: "conv_test", reply: "How can I help?" } });
  act(() => root.render(<MemoryRouter><HeroSection /></MemoryRouter>));
  const input = container.querySelector('[data-testid="instant-legal-help-trigger-input"]');
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    setter.call(input, "I need help with a court service");
    input.dispatchEvent(new Event("input", { bubbles: true }));
    container.querySelector('[data-testid="instant-legal-help-launcher"]').click();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(api.post).toHaveBeenCalledWith("/ai/chat", {
    conversation_id: null,
    message: "I need help with a court service",
  });
});

test("chat sends a message and displays only the reply without a source footer", async () => {
  api.post.mockResolvedValue({ data: {
    conversation_id: "conv_test", reply: "Choose a service, upload documents, then review your order.",
    sources: ["courtbazaar-product-guide.md"],
  } });
  act(() => root.render(<MemoryRouter><HeroSection /></MemoryRouter>));
  act(() => container.querySelector('[data-testid="instant-legal-help-launcher"]').click());
  const input = container.querySelector('[data-testid="instant-legal-help-input"]');
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    setter.call(input, "How does ordering work?");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => container.querySelector('[data-testid="instant-legal-help-send"]').click());
  expect(api.post).toHaveBeenCalledWith("/ai/chat", { conversation_id: null, message: "How does ordering work?" });
  expect(container.textContent).toContain("Choose a service, upload documents");
  expect(container.textContent).not.toContain("courtbazaar-product-guide.md");
  expect(container.textContent).not.toContain("Sources:");
  expect(container.querySelector('[data-testid="instant-legal-help-sources"]')).toBeNull();
  expect(container.querySelector('[data-testid="instant-legal-help-msg-assistant-1"]').textContent)
    .toBe("Choose a service, upload documents, then review your order.");
});
