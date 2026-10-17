import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";

jest.mock("react-router/dom", () => {
  const { TextEncoder, TextDecoder } = require("util");
  Object.assign(global, { TextEncoder, TextDecoder });
  return require("react-router/dist/development/dom-export.js");
}, { virtual: true });
jest.mock("@/lib/api", () => ({
  api: { post: jest.fn() },
  getErrorMessage: (_error, fallback) => fallback,
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() } }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { act } = React;
const { api } = require("@/lib/api");
const HeroSection = require("@/components/landing/HeroSection").default;
const LegalHelp = require("@/pages/marketing/LegalHelp").default;
const InstantLegalHelpChat = require("./InstantLegalHelpChat").default;

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
  jest.clearAllMocks();
});

const $ = (testId) => container.querySelector(`[data-testid="${testId}"]`);
const flush = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

function setValue(el, value) {
  const proto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

function renderApp(initialEntries = ["/"]) {
  act(() => root.render(
    <MemoryRouter initialEntries={initialEntries}>
      <LocationProbe />
      <Routes>
        <Route path="/" element={<HeroSection />} />
        <Route path="/legal-help" element={<LegalHelp />} />
      </Routes>
    </MemoryRouter>,
  ));
}

function renderChat(props = {}) {
  act(() => root.render(<InstantLegalHelpChat {...props} />));
}

async function sendMessage(text) {
  await act(async () => setValue($("instant-legal-help-input"), text));
  await act(async () => $("instant-legal-help-send").click());
  await flush();
}

// ---------------------------------------------------------------------------
// Landing page: Explore Services removed, launcher opens the full page
// ---------------------------------------------------------------------------

test("hero no longer shows Explore Services, and keeps the chat launcher", () => {
  renderApp();
  expect(container.textContent).not.toContain("Explore Services");
  expect(container.querySelector('a[href="/register"]')).toBeNull();
  expect($("instant-legal-help-launcher").textContent).toBe("Chat with Instant Legal Help →");
  expect($("instant-legal-help-trigger-input").placeholder).toBe("Describe your situation, legal issue, or service need...");
  // No small panel on the landing page any more.
  expect($("instant-legal-help-panel")).toBeNull();
});

test("launcher opens the dedicated chat page and sends the typed text exactly once", async () => {
  api.post.mockResolvedValue({ data: { conversation_id: "conv_test", reply: "How can I help?" } });
  renderApp();
  await act(async () => setValue($("instant-legal-help-trigger-input"), "I need help with a court service"));
  await act(async () => $("instant-legal-help-launcher").click());
  await flush();
  expect(currentLocation.pathname).toBe("/legal-help");
  expect(currentLocation.search).toBe(""); // never in the URL
  expect($("instant-legal-help-panel")).not.toBeNull();
  expect(api.post).toHaveBeenCalledTimes(1);
  expect(api.post).toHaveBeenCalledWith("/ai/chat", { conversation_id: null, message: "I need help with a court service" });
  expect(container.textContent).toContain("How can I help?");
  // Cleared from history so a refresh doesn't resend it.
  expect(currentLocation.state).toBeNull();
});

test("launcher with nothing typed opens an empty chat without calling the API", async () => {
  renderApp();
  await act(async () => $("instant-legal-help-launcher").click());
  await flush();
  expect(currentLocation.pathname).toBe("/legal-help");
  expect($("instant-legal-help-empty")).not.toBeNull();
  expect(api.post).not.toHaveBeenCalled();
});

test("Enter in the launcher input opens the chat page too", async () => {
  api.post.mockResolvedValue({ data: { conversation_id: "conv_test", reply: "Hi." } });
  renderApp();
  const input = $("instant-legal-help-trigger-input");
  await act(async () => setValue(input, "What is bail?"));
  await act(async () => input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
  await flush();
  expect(currentLocation.pathname).toBe("/legal-help");
  expect(api.post).toHaveBeenCalledWith("/ai/chat", { conversation_id: null, message: "What is bail?" });
});

// ---------------------------------------------------------------------------
// Chat behaviour (API contract unchanged)
// ---------------------------------------------------------------------------

test("chat sends a message and displays only the reply without a source footer", async () => {
  api.post.mockResolvedValue({ data: {
    conversation_id: "conv_test", reply: "Choose a service, upload documents, then review your order.",
    sources: ["courtbazaar-product-guide.md"],
  } });
  renderChat();
  await sendMessage("How does ordering work?");
  expect(api.post).toHaveBeenCalledWith("/ai/chat", { conversation_id: null, message: "How does ordering work?" });
  expect(container.textContent).not.toContain("courtbazaar-product-guide.md");
  expect(container.textContent).not.toContain("Sources:");
  expect($("instant-legal-help-msg-user-0").textContent).toBe("How does ordering work?");
  expect($("instant-legal-help-msg-assistant-1").textContent)
    .toBe("Choose a service, upload documents, then review your order.");
});

test("assistant reply keeps safe structure and cleans entity/escape artifacts", async () => {
  api.post.mockResolvedValue({ data: { conversation_id: "c", reply: "**Step 1** &amp;#x20;file\n- upload \\- now" } });
  renderChat();
  await sendMessage("steps?");
  const msg = $("instant-legal-help-msg-assistant-1");
  expect(msg.querySelector("strong").textContent).toBe("Step 1");
  expect(msg.querySelector("p").textContent).toBe("Step 1 file");
  expect([...msg.querySelectorAll("li")].map((li) => li.textContent)).toEqual(["upload - now"]);
  expect(msg.textContent).not.toMatch(/\*\*|&amp;|&#x20;|\\-/);
});

const DIAC_ANSWER = [
  "If the Claimant doesn't pay its share, Rule 33 applies.",
  "",
  "## The Claimant's share",
  "Unless the Centre directs otherwise, 50% is payable by the Claimant.",
  "",
  "## Termination",
  "- The Centre may terminate the arbitration (Rule 33.5).",
  "- This is without prejudice to reintroducing the Claim.",
].join("\n");

test("a document answer renders headings, lists and server-built source chips", async () => {
  api.post.mockResolvedValue({ data: {
    conversation_id: "c", reply: DIAC_ANSWER, sources: ["DIAC Rules conclusive_UsingOCR.pdf"],
    citations: [{ title: "DIAC Rules", url: null, rules: ["33.1", "33.5"] }], grounding: "supported",
  } });
  renderChat();
  await sendMessage("Tell me about DIAC rules if the claimant does not pay the Arbitral fee.");
  const msg = $("instant-legal-help-msg-assistant-1");
  expect([...msg.querySelectorAll("h3")].map((h) => h.textContent)).toEqual(["The Claimant's share", "Termination"]);
  expect(msg.querySelectorAll("ul li")).toHaveLength(2);
  expect(msg.textContent).not.toContain("##");
  const chips = $("instant-legal-help-citations");
  expect(chips.textContent).toContain("DIAC Rules · Rules 33.1, 33.5");
  expect(chips.querySelector("a")).toBeNull(); // no approved URL -> label only
  expect(container.textContent).not.toContain("conclusive_UsingOCR"); // raw filenames never shown
  expect($("instant-legal-help-insufficient")).toBeNull();
});

test("a citation with an approved URL is a safe external link", async () => {
  api.post.mockResolvedValue({ data: {
    conversation_id: "c", reply: "Answer.", grounding: "supported",
    citations: [{ title: "DIAC Rules", url: "https://example.org/diac-rules.pdf", rules: ["33.5"] }],
  } });
  renderChat();
  await sendMessage("q");
  const link = $("instant-legal-help-citations").querySelector("a");
  expect(link.getAttribute("href")).toBe("https://example.org/diac-rules.pdf");
  expect(link.getAttribute("target")).toBe("_blank");
  expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  expect(link.textContent).toBe("DIAC Rules · Rule 33.5");
});

test("insufficient evidence is shown as its own state, not as an error", async () => {
  api.post.mockResolvedValue({ data: {
    conversation_id: "c", degraded: true, grounding: "insufficient", citations: [],
    reply: "I couldn’t find that information in the available documents.",
  } });
  renderChat();
  await sendMessage("What do the DIAC rules say about appeals to the Supreme Court?");
  const notice = $("instant-legal-help-insufficient");
  expect(notice).not.toBeNull();
  expect(notice.textContent).toContain("Not covered by the available documents");
  expect(notice.textContent).toContain("I couldn’t find that information");
  expect($("instant-legal-help-citations")).toBeNull();
});

test("markup or links inside a reply are shown as text, never rendered", async () => {
  api.post.mockResolvedValue({ data: {
    conversation_id: "c",
    reply: "<img src=x onerror=alert(1)> <script>alert(2)</script> see [here](javascript:alert(3))",
  } });
  renderChat();
  await sendMessage("q");
  const msg = $("instant-legal-help-msg-assistant-1");
  expect(msg.querySelector("img, script, a")).toBeNull();
  expect(msg.textContent).toContain("<script>alert(2)</script>");
});

test("shows a loading indicator while waiting and blocks a second send", async () => {
  let resolve;
  api.post.mockReturnValue(new Promise((r) => { resolve = r; }));
  renderChat();
  await sendMessage("Hello");
  expect($("instant-legal-help-loading")).not.toBeNull();
  expect($("instant-legal-help-send").disabled).toBe(true);
  await act(async () => resolve({ data: { conversation_id: "c", reply: "Hi there" } }));
  await flush();
  expect($("instant-legal-help-loading")).toBeNull();
  expect(container.textContent).toContain("Hi there");
});

test("Enter sends, Shift+Enter does not", async () => {
  api.post.mockResolvedValue({ data: { conversation_id: "c", reply: "ok" } });
  renderChat();
  const input = $("instant-legal-help-input");
  await act(async () => setValue(input, "line one"));
  await act(async () => input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", shiftKey: true, bubbles: true })));
  expect(api.post).not.toHaveBeenCalled();
  await act(async () => input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
  await flush();
  expect(api.post).toHaveBeenCalledWith("/ai/chat", { conversation_id: null, message: "line one" });
});

test("the conversation token issued with the first reply is sent back to continue the chat", async () => {
  api.post
    .mockResolvedValueOnce({ data: { conversation_id: "conv_anon", conversation_token: "secret-token", reply: "First." } })
    .mockResolvedValueOnce({ data: { conversation_id: "conv_anon", reply: "Second." } });
  renderChat();
  await sendMessage("What is bail?");
  await sendMessage("And anticipatory bail?");
  expect(api.post).toHaveBeenLastCalledWith("/ai/chat", {
    conversation_id: "conv_anon", conversation_token: "secret-token", message: "And anticipatory bail?",
  });
});

test("a conversation the backend won't continue (404) is dropped and the next message starts fresh", async () => {
  api.post
    .mockResolvedValueOnce({ data: { conversation_id: "conv_anon", conversation_token: "secret-token", reply: "First." } })
    .mockRejectedValueOnce({ response: { status: 404 } })
    .mockResolvedValueOnce({ data: { conversation_id: "conv_new", conversation_token: "new-token", reply: "Fresh." } });
  renderChat();
  await sendMessage("What is bail?");
  await sendMessage("Continue");
  expect(container.textContent).toContain("This chat session is no longer available.");
  await sendMessage("Try again");
  expect(api.post).toHaveBeenLastCalledWith("/ai/chat", { conversation_id: null, message: "Try again" });
});

test("service unavailable (503) shows the unavailable message", async () => {
  api.post.mockRejectedValueOnce({ response: { status: 503 } });
  renderChat();
  await sendMessage("Hello");
  expect(container.textContent).toContain("Instant Legal Help isn't available right now.");
});

test("New chat clears the conversation and starts a fresh one", async () => {
  api.post
    .mockResolvedValueOnce({ data: { conversation_id: "conv_1", conversation_token: "t1", reply: "First." } })
    .mockResolvedValueOnce({ data: { conversation_id: "conv_2", reply: "Second." } });
  renderChat();
  expect($("instant-legal-help-new-chat").disabled).toBe(true);
  await sendMessage("Hello");
  await act(async () => $("instant-legal-help-new-chat").click());
  expect(container.textContent).not.toContain("First.");
  expect($("instant-legal-help-empty")).not.toBeNull();
  await sendMessage("Again");
  expect(api.post).toHaveBeenLastCalledWith("/ai/chat", { conversation_id: null, message: "Again" });
});
