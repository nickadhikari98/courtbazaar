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
// The stream is covered in chatStream.test.js; here it's a single request.
jest.mock("./chatStream", () => ({
  streamChat: (payload, { idleMs, signal }) => require("@/lib/api").api
    .post("/ai/chat", payload, { timeout: idleMs, signal }).then((r) => r.data),
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

// Every chat request carries a client timeout and an abort signal.
const CHAT_OPTS = expect.objectContaining({ timeout: expect.any(Number), signal: expect.any(AbortSignal) });

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
  expect(api.post).toHaveBeenCalledWith("/ai/chat", { conversation_id: null, message: "I need help with a court service" }, CHAT_OPTS);
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
  expect(api.post).toHaveBeenCalledWith("/ai/chat", { conversation_id: null, message: "What is bail?" }, CHAT_OPTS);
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
  expect(api.post).toHaveBeenCalledWith("/ai/chat", { conversation_id: null, message: "How does ordering work?" }, CHAT_OPTS);
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
  const sources = $("instant-legal-help-citations");
  expect(sources.querySelector("h4").textContent).toBe("Sources");
  const items = sources.querySelectorAll('[data-testid="instant-legal-help-source"]');
  expect(items).toHaveLength(1);
  expect(items[0].textContent).toContain("DIAC Rules");
  expect(items[0].querySelector('[data-testid="instant-legal-help-source-detail"]').textContent).toBe("Rules 33.1, 33.5");
  expect(sources.querySelector("a")).toBeNull(); // no approved URL -> label only
  expect(container.textContent).not.toContain("conclusive_UsingOCR"); // raw filenames never shown
  expect($("instant-legal-help-insufficient")).toBeNull();
});

const CARD = {
  status: "answered",
  summary: "Each party pays 50% (Rule 33.1).",
  points: [{ icon: "rule", title: "Rule 33.1 — Advance on costs", badge: "Rule 33.1", tone: "success", text: "50% each (Rule 33.1).", cite: [1] }],
  follow_up: "Want to know what happens on non-payment?",
  note: "Check the current version.",
};
const CARD_CITATIONS = [{ title: "DIAC Rules", url: null, rules: ["33.1"] }];

test("a structured answer renders as a card above the Sources", async () => {
  api.post.mockResolvedValue({ data: { conversation_id: "c", reply: "## Plain text", citations: CARD_CITATIONS, grounding: "supported", answer: CARD } });
  renderChat();
  await sendMessage("Who pays?");
  const card = $("instant-legal-help-answer-card");
  expect(card.textContent).toContain("Each party pays 50%");
  expect(card.textContent).not.toContain("Plain text");
  const point = card.querySelector('[data-testid="instant-legal-help-answer-point"]');
  expect(point.querySelector("h4").textContent).toBe("Rule 33.1 — Advance on costs");
  expect(point.querySelector('[data-testid="instant-legal-help-cite"]').textContent).toBe("1");
  expect($("instant-legal-help-partial-note")).toBeNull();
  expect($("instant-legal-help-answer-note").textContent).toBe("Check the current version.");
  expect($("instant-legal-help-citations")).not.toBeNull();
});

test("an answered card shows one line, with the full text behind the (i)", async () => {
  const answer = { ...CARD, note: "Based on DIAC Rules · Not legal advice — verify with an advocate.", note_detail: "Rules and their numbering can change." };
  api.post.mockResolvedValue({ data: { conversation_id: "c", reply: "x", citations: CARD_CITATIONS, grounding: "supported", answer } });
  renderChat();
  await sendMessage("Who pays?");
  expect($("instant-legal-help-answer-note").textContent).toBe(answer.note);
  expect(document.body.textContent).not.toContain("numbering can change");
  await act(async () => { $("instant-legal-help-note-info").click(); });
  expect(document.querySelector('[data-testid="instant-legal-help-note-detail"]').textContent).toBe(answer.note_detail);
});

test("a plain document answer shows the same short note, not the long one in its text", async () => {
  api.post.mockResolvedValue({ data: {
    conversation_id: "c", reply: "Answer text.\n\nRules and their numbering can change.", body: "Answer text.",
    note: "Based on DIAC Rules · Not legal advice — verify with an advocate.", note_detail: "Rules and their numbering can change.",
    citations: CARD_CITATIONS, grounding: "supported", answer: null,
  } });
  renderChat();
  await sendMessage("Who pays?");
  expect($("instant-legal-help-answer-note").textContent).toContain("Based on DIAC Rules");
  expect($("instant-legal-help-msg-assistant-1").textContent).not.toContain("numbering can change");
});

test("a source shows the clause when the answer cited one", async () => {
  api.post.mockResolvedValue({ data: {
    conversation_id: "c", reply: "x", grounding: "supported", answer: CARD,
    citations: [{ title: "DIAC Rules", url: null, rules: ["4"], rule_labels: ["4(i)"] }],
  } });
  renderChat();
  await sendMessage("Who pays?");
  expect($("instant-legal-help-source-detail").textContent).toBe("Rule 4(i)");
});

test("a partial answer shows its note at the top of the card", async () => {
  api.post.mockResolvedValue({ data: { conversation_id: "c", reply: "x", citations: CARD_CITATIONS, grounding: "partial", answer: { ...CARD, status: "partial" } } });
  renderChat();
  await sendMessage("Who pays?");
  expect($("instant-legal-help-answer-card").firstChild).toBe($("instant-legal-help-partial-note"));
  expect($("instant-legal-help-partial-note").textContent).toContain("Partial answer");
  expect($("instant-legal-help-answer-note").textContent).toBe("Check the current version.");
});

test("a malformed card falls back to the plain reply", async () => {
  api.post.mockResolvedValue({ data: { conversation_id: "c", reply: "Plain answer.", citations: [], grounding: "supported", answer: { summary: "x", points: "nope" } } });
  renderChat();
  await sendMessage("Who pays?");
  expect($("instant-legal-help-answer-card")).toBeNull();
  expect($("instant-legal-help-msg-assistant-1").textContent).toContain("Plain answer.");
});

test("the status indicator follows the server's steps, ticks them off and counts up", async () => {
  jest.useFakeTimers();
  const ChatStatus = require("./ChatStatus").default;
  const steps = [{ step: "understanding", text: "Understanding your question…" }, { step: "reading", text: "Reading Rule 33.1…" }];
  act(() => { root.render(<ChatStatus steps={steps} />); });
  expect($("instant-legal-help-status-text").textContent).toBe("Reading Rule 33.1…");
  act(() => { jest.advanceTimersByTime(3000); });
  expect($("instant-legal-help-status-timer").textContent).toBe("3s");
  expect($("instant-legal-help-status-steps")).toBeNull(); // collapsed by default
  act(() => { $("instant-legal-help-status-toggle").click(); });
  expect($("instant-legal-help-status-steps").textContent).toBe("Understanding your question…");
  jest.useRealTimers();
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
  expect(link.textContent).toBe("DIAC Rules (opens in a new tab)");
  expect($("instant-legal-help-citations").textContent).toContain("Rule 33.5");
});

test("multiple sources are listed in order, each with only its own verified rules", async () => {
  api.post.mockResolvedValue({ data: {
    conversation_id: "c", reply: "Answer.", grounding: "supported",
    citations: [
      { title: "DIAC Rules", url: null, rules: ["33.5"] },
      { title: "Standard Operating Procedure (SOP)", url: null, rules: [] },
    ],
  } });
  renderChat();
  await sendMessage("q");
  const items = [...container.querySelectorAll('[data-testid="instant-legal-help-source"]')];
  expect(items.map((li) => li.textContent)).toEqual([
    "1DIAC RulesRule 33.5",
    "2Standard Operating Procedure (SOP)",
  ]);
  expect(items[1].querySelector('[data-testid="instant-legal-help-source-detail"]')).toBeNull();
});

test("missing, malformed or unsafe source metadata is dropped, never guessed", async () => {
  api.post.mockResolvedValue({ data: {
    conversation_id: "c", reply: "Answer.", grounding: "supported",
    citations: [
      null, "DIAC Rules", { url: "https://example.org/x.pdf" }, { title: "   " },
      { title: "DIAC Rules", url: "javascript:alert(1)", rules: ["33.5", "<b>9</b>", 7] },
      { title: "DIAC Rules", url: "http://insecure.example.org/a.pdf", rules: ["33.1", "33.5"] },
    ],
  } });
  renderChat();
  await sendMessage("q");
  const items = container.querySelectorAll('[data-testid="instant-legal-help-source"]');
  expect(items).toHaveLength(1); // duplicates merged, junk dropped
  expect(items[0].querySelector("a")).toBeNull(); // javascript: and http: are never links
  expect(items[0].querySelector('[data-testid="instant-legal-help-source-detail"]').textContent).toBe("Rules 33.5, 33.1");
  expect(container.textContent).not.toContain("<b>9</b>");
});

test("each set of rules is its own source, with the document it came from", async () => {
  const doc = "Delhi International Arbitration Centre (DIAC) Rules";
  api.post.mockResolvedValue({ data: {
    conversation_id: "c", reply: "Answer.", grounding: "supported",
    citations: [
      { title: "Delhi International Arbitration Centre (Administrative Costs & Arbitrators' Fees) Rules, 2018", url: null, rules: ["5"], document: doc },
      { title: "Delhi International Arbitration Centre (Arbitration Proceedings) Rules, 2023", url: null, rules: ["33.5"], document: doc },
      { title: doc, url: null, rules: ["4"], document: doc },
    ],
  } });
  renderChat();
  await sendMessage("q");
  const items = [...container.querySelectorAll('[data-testid="instant-legal-help-source"]')];
  expect(items).toHaveLength(3);
  expect(items[0].textContent).toContain("(Administrative Costs & Arbitrators' Fees) Rules, 2018");
  expect(items[0].querySelector('[data-testid="instant-legal-help-source-detail"]').textContent).toBe("Rule 5");
  expect(items[0].querySelector('[data-testid="instant-legal-help-source-document"]').textContent).toBe(`From: ${doc}`);
  expect(items[1].querySelector('[data-testid="instant-legal-help-source-detail"]').textContent).toBe("Rule 33.5");
  // The document-level entry doesn't repeat its own name as "From:".
  expect(items[2].querySelector('[data-testid="instant-legal-help-source-document"]')).toBeNull();
});

test("a missing or non-string document field is simply not shown", async () => {
  api.post.mockResolvedValue({ data: {
    conversation_id: "c", reply: "Answer.", grounding: "supported",
    citations: [{ title: "DIAC Rules", url: null, rules: [], document: { evil: true } }],
  } });
  renderChat();
  await sendMessage("q");
  expect($("instant-legal-help-citations")).not.toBeNull();
  expect(container.querySelector('[data-testid="instant-legal-help-source-document"]')).toBeNull();
});

test("empty headings, number-only headings, empty bullets and stray dividers are never shown", async () => {
  const reply = [
    "---",
    "## Appointment Procedure",
    "## 1. Who appoints",
    "- The Chairperson appoints the Arbitrator (Rule 8.6).",
    "- .",
    "",
    "---",
    "",
    "---",
    "",
    "### 6.",
    "## Next steps",
    "---",
  ].join("\n");
  api.post.mockResolvedValue({ data: { conversation_id: "c", reply, grounding: "partial", citations: [] } });
  renderChat();
  await sendMessage("q");
  const msg = $("instant-legal-help-msg-assistant-1");
  expect([...msg.querySelectorAll("h3, h4")].map((h) => h.textContent)).toEqual(["1. Who appoints"]);
  expect([...msg.querySelectorAll("li")].map((li) => li.textContent)).toEqual(["The Chairperson appoints the Arbitrator (Rule 8.6)."]);
  expect(msg.querySelectorAll("hr")).toHaveLength(0);
  expect($("instant-legal-help-citations")).toBeNull(); // nothing verified -> no Sources section
});

// ---------------------------------------------------------------------------
// Web-search citations (general legal answers)
// ---------------------------------------------------------------------------

const INDIA_CODE = "https://www.indiacode.nic.in/handle/123456789/20099";
const SCI = "https://www.sci.gov.in/judgements";
const webCite = (index, url, title) => ({ kind: "web", index, url, title, domain: "ignored.example" });

test("web citation markers are safe links to the cited page, and Sources show title, domain and URL", async () => {
  api.post.mockResolvedValue({ data: {
    conversation_id: "c",
    reply: "Anticipatory bail is covered by Section 482 of the BNSS [1]. The Supreme Court has explained it [2]. Courts apply it widely [1].",
    citations: [webCite(1, INDIA_CODE, "Bharatiya Nagarik Suraksha Sanhita, 2023"), webCite(2, SCI, "Judgments")],
  } });
  renderChat();
  await sendMessage("What is anticipatory bail?");
  const msg = $("instant-legal-help-msg-assistant-1");
  const markers = [...msg.querySelectorAll('[data-testid="instant-legal-help-cite"]')];
  expect(markers.map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
    ["1", INDIA_CODE], ["2", SCI], ["1", INDIA_CODE], // a repeated citation reuses its number and link
  ]);
  for (const a of markers) {
    expect(a.getAttribute("target")).toBe("_blank");
    expect(a.getAttribute("rel")).toBe("noopener noreferrer");
  }
  expect(markers[0].getAttribute("aria-label")).toBe("Source 1: Bharatiya Nagarik Suraksha Sanhita, 2023 (opens in a new tab)");
  expect(msg.textContent).not.toContain("[1]");
  const items = [...container.querySelectorAll('[data-testid="instant-legal-help-web-source"]')];
  expect(items).toHaveLength(2);
  expect(items[0].querySelector('[data-testid="instant-legal-help-source-link"]').getAttribute("href")).toBe(INDIA_CODE);
  expect(items[0].textContent).toContain("Bharatiya Nagarik Suraksha Sanhita, 2023");
  // The domain shown is read from the URL, never taken from the server's field.
  expect(items[0].querySelector('[data-testid="instant-legal-help-source-domain"]').textContent).toBe("Official website · www.indiacode.nic.in");
  expect(items[0].querySelector('[data-testid="instant-legal-help-source-url"]').textContent).toBe(INDIA_CODE);
  expect(items[1].textContent).toContain("www.sci.gov.in");
  expect(container.querySelectorAll('[data-testid="instant-legal-help-source"]')).toHaveLength(0);
});

test("missing, malformed or unsafe web citations are dropped and their markers stay plain text", async () => {
  api.post.mockResolvedValue({ data: {
    conversation_id: "c",
    reply: "Claim one [1]. Claim two [2]. Claim three [3]. Claim four [4]. Claim five [5].",
    citations: [
      webCite(1, "javascript:alert(1)", "Bad"),
      webCite(2, "http://www.sci.gov.in/x", "Insecure"),
      webCite("3", SCI, "String index"),
      { kind: "web", index: 4, title: "No URL" },
      { kind: "blog", index: 5, url: SCI, title: "Unknown kind" },
      null,
    ],
  } });
  renderChat();
  await sendMessage("q");
  const msg = $("instant-legal-help-msg-assistant-1");
  expect(msg.querySelector('[data-testid="instant-legal-help-cite"]')).toBeNull();
  expect(msg.querySelector("a")).toBeNull();
  expect(msg.textContent).toContain("Claim one [1].");
  expect($("instant-legal-help-citations")).toBeNull(); // no empty Sources section
});

test("a web citation without a title is labelled with its domain", async () => {
  api.post.mockResolvedValue({ data: { conversation_id: "c", reply: "Claim [1].", citations: [webCite(1, SCI, "  ")] } });
  renderChat();
  await sendMessage("q");
  expect($("instant-legal-help-cite").getAttribute("aria-label")).toBe("Source 1: www.sci.gov.in (opens in a new tab)");
  expect($("instant-legal-help-web-source").querySelector('[data-testid="instant-legal-help-source-link"]').textContent)
    .toContain("www.sci.gov.in");
});

test("web and document sources are shown together but kept distinct, with DIAC rules intact", async () => {
  api.post.mockResolvedValue({ data: {
    conversation_id: "c", reply: "Web claim [1]. Under Rule 33.5 the claim may be terminated.", grounding: "supported",
    citations: [
      webCite(1, INDIA_CODE, "Arbitration and Conciliation Act, 1996"),
      { title: "Delhi International Arbitration Centre (Arbitration Proceedings) Rules, 2023", url: null, rules: ["33.5"],
        document: "Delhi International Arbitration Centre (DIAC) Rules" },
    ],
  } });
  renderChat();
  await sendMessage("q");
  const web = $("instant-legal-help-web-source");
  const doc = $("instant-legal-help-source");
  expect(web.textContent).toContain("Official website");
  expect(doc.textContent).not.toContain("Official website");
  expect(doc.querySelector('[data-testid="instant-legal-help-source-detail"]').textContent).toBe("Rule 33.5");
  expect(doc.textContent).toContain("Arbitration Proceedings) Rules, 2023");
  // Numbers never collide: the document comes after the web sources.
  expect(web.textContent.startsWith("1")).toBe(true);
  expect(doc.textContent.startsWith("2")).toBe(true);
  // Only the web marker is linked; the rule number stays text.
  expect(container.querySelectorAll('[data-testid="instant-legal-help-cite"]')).toHaveLength(1);
});

test("a fallback reply shows the message and no Sources section", async () => {
  api.post.mockResolvedValue({ data: {
    conversation_id: "c", degraded: true, grounding: "insufficient", citations: [],
    reply: "I couldn’t find anything in the Delhi International Arbitration Centre (DIAC) Rules that answers this. If you know the rule number, or have the relevant rule or document, share it and I'll check it.",
  } });
  renderChat();
  await sendMessage("q");
  expect($("instant-legal-help-insufficient").textContent).toContain("share it and I'll check it");
  expect($("instant-legal-help-citations")).toBeNull();
  expect($("instant-legal-help-msg-assistant-1").querySelector("h3, h4")).toBeNull();
});

test("a non-array citations field shows no Sources section", async () => {
  api.post.mockResolvedValue({ data: { conversation_id: "c", reply: "Answer.", citations: { title: "DIAC Rules" } } });
  renderChat();
  await sendMessage("q");
  expect($("instant-legal-help-citations")).toBeNull();
  expect($("instant-legal-help-msg-assistant-1").textContent).toBe("Answer.");
});

test.each([
  ["an empty body", {}],
  ["a non-string reply", { reply: { text: "x" } }],
  ["a blank reply", { reply: "   " }],
  ["a null body", null],
])("%s falls back to the generic error text instead of crashing", async (_label, data) => {
  api.post.mockResolvedValue({ data });
  renderChat();
  await sendMessage("q");
  expect($("instant-legal-help-msg-assistant-1").textContent).toContain("Sorry — I'm having trouble responding right now.");
  expect($("instant-legal-help-citations")).toBeNull();
});

test("a long structured answer renders sections, steps, sub-points and dividers", async () => {
  const reply = [
    "Here is how it works.",
    "",
    "## Filing",
    "1. Prepare the documents",
    "  - Signed copy",
    "  - ID proof",
    "2. Upload them",
    "",
    "---",
    "",
    "## After filing",
    "A very long reference like https://example.org/" + "a".repeat(300) + " stays readable text.",
  ].join("\n");
  api.post.mockResolvedValue({ data: { conversation_id: "c", reply, grounding: "supported", citations: [] } });
  renderChat();
  await sendMessage("q");
  const msg = $("instant-legal-help-msg-assistant-1");
  const headings = [...msg.querySelectorAll("h3")];
  expect(headings.map((h) => h.textContent)).toEqual(["Filing", "After filing"]);
  expect(headings[0].className).toContain("border-t"); // separated from the intro paragraph
  const steps = msg.querySelectorAll("ol > li");
  expect(steps).toHaveLength(2);
  expect([...steps[0].querySelectorAll("ul li")].map((li) => li.textContent)).toEqual(["Signed copy", "ID proof"]);
  expect(msg.querySelector("hr")).not.toBeNull();
  expect(msg.querySelector("a")).toBeNull(); // model-written URLs are never links
  expect($("chat-markdown").className).toContain("[overflow-wrap:anywhere]"); // long tokens wrap on phones
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

function deferred() {
  let resolve; let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

test("Send shows the thinking indicator before the reply, blocks a second send, then shows the answer", async () => {
  const d = deferred();
  api.post.mockReturnValue(d.promise);
  renderChat();
  await sendMessage("Hello");
  const loading = $("instant-legal-help-loading");
  expect(loading).not.toBeNull();
  expect(loading.textContent).toContain("Understanding your question…");
  expect($("instant-legal-help-msg-user-0").textContent).toBe("Hello");
  expect($("instant-legal-help-send").disabled).toBe(true);
  // A second Enter while waiting is ignored.
  const input = $("instant-legal-help-input");
  await act(async () => setValue(input, "Again"));
  await act(async () => input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
  expect(api.post).toHaveBeenCalledTimes(1);
  await act(async () => d.resolve({ data: {
    conversation_id: "c", reply: "## Answer\n\n1. Step one",
    citations: [{ title: "Delhi High Court Rules", url: null, rules: ["3"] }],
  } }));
  await flush();
  expect($("instant-legal-help-loading")).toBeNull();
  expect($("instant-legal-help-msg-assistant-1").textContent).toContain("Step one");
  expect($("instant-legal-help-msg-assistant-1").textContent).toContain("Delhi High Court Rules");
  expect(container.textContent).not.toContain("Understanding your question…");
});

test("Enter shows the thinking indicator immediately", async () => {
  api.post.mockReturnValue(new Promise(() => {}));
  renderChat();
  const input = $("instant-legal-help-input");
  await act(async () => setValue(input, "What is bail?"));
  await act(async () => input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
  expect($("instant-legal-help-loading").textContent).toContain("Understanding your question…");
});

test("an API error clears the indicator and Try again resends the same question", async () => {
  api.post
    .mockRejectedValueOnce({ response: { status: 500 } })
    .mockResolvedValueOnce({ data: { conversation_id: "c", reply: "Recovered." } });
  renderChat();
  await sendMessage("What is bail?");
  expect($("instant-legal-help-loading")).toBeNull();
  expect(container.textContent).toContain("having trouble responding");
  await act(async () => $("instant-legal-help-retry").click());
  await flush();
  expect(api.post).toHaveBeenLastCalledWith("/ai/chat", { conversation_id: null, message: "What is bail?" }, CHAT_OPTS);
  // The failed exchange is replaced, not duplicated.
  expect(container.querySelectorAll('[data-testid^="instant-legal-help-msg-user-"]')).toHaveLength(1);
  expect(container.textContent).not.toContain("having trouble responding");
  expect(container.textContent).toContain("Recovered.");
  expect($("instant-legal-help-retry")).toBeNull();
});

test("a timeout clears the indicator and offers a retry", async () => {
  api.post.mockRejectedValueOnce({ code: "ECONNABORTED" });
  renderChat();
  await sendMessage("Hello");
  expect($("instant-legal-help-loading")).toBeNull();
  expect(container.textContent).toContain("taking longer than expected");
  expect($("instant-legal-help-retry")).not.toBeNull();
  expect($("instant-legal-help-input").value).toBe("");
  expect($("instant-legal-help-msg-user-0").textContent).toBe("Hello");
});

// jsdom has no layout: give the message log a scroll range and each question
// a position, and record where the log is asked to scroll.
function fakeLogLayout({ reduceMotion = false } = {}) {
  const log = $("instant-legal-help-messages");
  Object.defineProperty(log, "scrollHeight", { configurable: true, get: () => 2000 });
  Object.defineProperty(log, "clientHeight", { configurable: true, get: () => 500 });
  log.scrollTo = jest.fn();
  const offsetTop = jest.spyOn(HTMLElement.prototype, "offsetTop", "get").mockImplementation(function offset() {
    const id = this.dataset?.testid || "";
    return id.startsWith("instant-legal-help-msg-user-") ? 300 + 400 * Number(id.split("-").pop()) : 0;
  });
  const matchMedia = window.matchMedia;
  window.matchMedia = jest.fn(() => ({ matches: reduceMotion }));
  return {
    log,
    restore: () => { offsetTop.mockRestore(); window.matchMedia = matchMedia; },
  };
}

test("submitting scrolls the log to the question and Thinking…; the reply scrolls to its question, not to the end", async () => {
  const d = deferred();
  api.post.mockReturnValue(d.promise);
  renderChat();
  const { log, restore } = fakeLogLayout();
  try {
    await sendMessage("What is bail?");
    expect(log.scrollTo).toHaveBeenLastCalledWith({ top: 1500, behavior: "smooth" }); // bottom: question + indicator
    await act(async () => d.resolve({ data: { conversation_id: "c", reply: "A long answer." } }));
    await flush();
    // The reply opens at its question (offsetTop 300, 16px breathing room), so
    // the answer is read from the top and its Sources are reached by scrolling.
    expect(log.scrollTo).toHaveBeenLastCalledWith({ top: 284, behavior: "smooth" });
  } finally {
    restore();
  }
});

test("scrolling is instant when reduced motion is preferred, and never past the end", async () => {
  api.post.mockResolvedValue({ data: { conversation_id: "c", reply: "ok" } });
  renderChat();
  const { log, restore } = fakeLogLayout({ reduceMotion: true });
  try {
    await sendMessage("one");
    await sendMessage("two");
    await sendMessage("three");
    await sendMessage("four"); // its question sits at 300 + 400*6 = 2700, past the 1500 scroll range
    expect(log.scrollTo).toHaveBeenLastCalledWith({ top: 1500, behavior: "auto" });
  } finally {
    restore();
  }
});

test("only the message log scrolls: the page is a flex column and the chat fills it", () => {
  renderApp(["/legal-help"]);
  const panel = $("instant-legal-help-panel");
  expect(panel.parentElement.tagName).toBe("MAIN");
  expect(panel.parentElement.className).toEqual(expect.stringContaining("flex-col"));
  expect(panel.parentElement.className).toEqual(expect.stringContaining("min-h-0"));
  expect(panel.className).toEqual(expect.stringContaining("flex-1"));
  expect($("instant-legal-help-messages").className).toEqual(expect.stringContaining("overflow-y-auto"));
  expect(panel.querySelectorAll(".overflow-y-auto")).toHaveLength(2); // the log, and the composer textarea
});

test("New chat cancels the in-flight request and leaves no stale indicator", async () => {
  const d = deferred();
  api.post.mockReturnValue(d.promise);
  renderChat();
  await sendMessage("Hello");
  const { signal } = api.post.mock.calls[0][2];
  await act(async () => $("instant-legal-help-new-chat").click());
  expect(signal.aborted).toBe(true);
  expect($("instant-legal-help-loading")).toBeNull();
  await act(async () => d.reject({ code: "ERR_CANCELED" }));
  await flush();
  expect($("instant-legal-help-empty")).not.toBeNull();
  expect(container.textContent).not.toContain("having trouble");
});

test("leaving the page aborts the in-flight request", async () => {
  api.post.mockReturnValue(new Promise(() => {}));
  renderChat();
  await sendMessage("Hello");
  const { signal } = api.post.mock.calls[0][2];
  act(() => root.unmount());
  expect(signal.aborted).toBe(true);
  root = createRoot(container); // afterEach unmounts again
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
  expect(api.post).toHaveBeenCalledWith("/ai/chat", { conversation_id: null, message: "line one" }, CHAT_OPTS);
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
  }, CHAT_OPTS);
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
  expect(api.post).toHaveBeenLastCalledWith("/ai/chat", { conversation_id: null, message: "Try again" }, CHAT_OPTS);
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
  expect(api.post).toHaveBeenLastCalledWith("/ai/chat", { conversation_id: null, message: "Again" }, CHAT_OPTS);
});
