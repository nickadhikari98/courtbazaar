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
jest.mock("./chatStream", () => ({
  streamChat: (payload) => require("@/lib/api").api.post("/ai/chat", payload).then((r) => r.data),
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() } }));
jest.mock("@/components/legal/SupportTicketModal", () => () => null);
const mockAuth = { user: null, logout: jest.fn(), refresh: jest.fn() };
jest.mock("@/context/AuthContext", () => ({ useAuth: () => mockAuth }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { act } = React;
const { api } = require("@/lib/api");
const InstantLegalHelpChat = require("./InstantLegalHelpChat").default;
const { default: ChatDraft, normalizeDraft, DOWNLOAD_FAILED, NO_HINDI_PDF } = require("./ChatDraft");

global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
Element.prototype.scrollIntoView = jest.fn();

const DRAFT = {
  draft_id: "draft_abc",
  type: "section_21_notice",
  title: "Notice invoking arbitration under Section 21",
  disclaimer: "Draft for review by a qualified advocate. This is not legal advice.",
  file_stem: "notice-invoking-arbitration-section-21_2026-11-19",
  pdf: true,
  note: null,
  blocks: [
    { style: "title", text: "Notice invoking arbitration under Section 21", fill: true },
    { style: "para", text: "From: [Claimant name], [Claimant address]", fill: true },
    { style: "para", text: "Date: [Date of notice]", fill: true },
    { style: "heading", text: "Legal basis", fill: false },
    { style: "para", text: "Proceedings commence on receipt of the request [see note] (Section 21).", fill: false },
    { style: "para", text: "For [Claimant name]", fill: true },
    { style: "heading", text: "Provisions relied on", fill: false },
    { style: "para", text: "Arbitration and Conciliation Act, 1996: Section 21", fill: false },
  ],
};

let container;
let root;
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  mockAuth.user = { user_id: "u1", name: "Jay Dee", email: "jay@example.com" };
  api.get.mockImplementation(() => Promise.resolve({ data: [] }));
  global.URL.createObjectURL = jest.fn(() => "blob:x");
  global.URL.revokeObjectURL = jest.fn();
  jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.body.innerHTML = "";
  jest.restoreAllMocks();
  jest.clearAllMocks();
});

const $ = (testId) => document.querySelector(`[data-testid="${testId}"]`);
const $$ = (testId) => [...document.querySelectorAll(`[data-testid="${testId}"]`)];
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
function setValue(el, value) {
  const proto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}
async function renderDraft(draft = DRAFT) {
  await act(async () => root.render(<ChatDraft draft={normalizeDraft(draft)} />));
}
const field = (name) => [...document.querySelectorAll("label")].filter((l) => l.textContent === name)
  .map((l) => document.getElementById(l.htmlFor));
const draftText = () => $("chat-draft-text").textContent;

test("the chat shows a draft reply as a read-only document with one labelled field per blank", async () => {
  api.post.mockResolvedValue({ data: { conversation_id: "c1", reply: "plain", draft: DRAFT, citations: [] } });
  await act(async () => root.render(<MemoryRouter><InstantLegalHelpChat /></MemoryRouter>));
  await flush();
  await act(async () => setValue($("instant-legal-help-input"), "Draft a Section 21 notice"));
  await act(async () => $("instant-legal-help-send").click());
  await flush();
  expect($("chat-draft-disclaimer").textContent).toBe(DRAFT.disclaimer);
  // The repeated [Claimant name] is one field.
  expect([...$("chat-draft-panel").querySelectorAll("label")].map((l) => l.textContent))
    .toEqual(["Claimant name", "Claimant address", "Date of notice"]);
  expect($("chat-draft-text").querySelector("input, textarea, [contenteditable]")).toBeNull();
  // A bracket in the legal basis is plain text, not a blank.
  expect(draftText()).toContain("[see note] (Section 21)");
  expect($$("chat-draft-empty").map((el) => el.textContent))
    .toEqual(["[Claimant name]", "[Claimant address]", "[Date of notice]", "[Claimant name]"]);
});

test("a filled blank shows its value everywhere in accent; empty ones stay as [placeholders] in danger", async () => {
  await renderDraft();
  expect($("chat-draft-empty-count").textContent).toBe("3 of 3 blanks still empty.");
  await act(async () => setValue(field("Claimant name")[0], "Asha Rao"));
  const filled = $$("chat-draft-filled");
  expect(filled.map((el) => el.textContent)).toEqual(["Asha Rao", "Asha Rao"]);
  filled.forEach((el) => expect(el.className).toMatch(/text-\[hsl\(32_95%_35%\)\] dark:text-accent/));
  $$("chat-draft-empty").forEach((el) => expect(el.className).toMatch(/text-destructive/));
  expect(draftText()).toContain("From: Asha Rao, [Claimant address]");
  expect(draftText()).toContain("For Asha Rao");
  expect($("chat-draft-empty-count").textContent).toBe("2 of 3 blanks still empty.");
  await act(async () => setValue(field("Claimant address")[0], "Pune"));
  await act(async () => setValue(field("Date of notice")[0], "1 Dec 2026"));
  expect($("chat-draft-empty-count").textContent).toBe("All blanks filled.");
});

test("whitespace is not a value: the blank stays a placeholder", async () => {
  await renderDraft();
  await act(async () => setValue(field("Date of notice")[0], "   "));
  expect(draftText()).toContain("Date: [Date of notice]");
});

test.each([["docx", "chat-draft-docx"], ["pdf", "chat-draft-pdf"]])(
  "the %s button downloads with blanks still empty, sending only filled values, no confirmation", async (fmt, testId) => {
    api.post.mockResolvedValue({ data: new Blob(["x"]) });
    window.confirm = jest.fn();
    await renderDraft();
    await act(async () => setValue(field("Claimant name")[0], " Asha Rao "));
    await act(async () => setValue(field("Date of notice")[0], "   "));
    expect($(testId).disabled).toBe(false);
    await act(async () => $(testId).click());
    await flush();
    expect(api.post).toHaveBeenCalledWith(`/ai/drafts/draft_abc/${fmt}`, { values: { "Claimant name": "Asha Rao" } },
      { responseType: "blob" });
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
    expect(window.confirm).not.toHaveBeenCalled();
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect($("chat-draft-error")).toBeNull();
  });

test("a failed download shows an error and the buttons come back", async () => {
  api.post.mockRejectedValue(new Error("boom"));
  await renderDraft();
  await act(async () => $("chat-draft-docx").click());
  await flush();
  expect($("chat-draft-error").textContent).toBe(DOWNLOAD_FAILED);
  expect($("chat-draft-docx").disabled).toBe(false);
});

test("a PDF the server refuses (409) shows the Word-file message, not a generic failure", async () => {
  api.post.mockRejectedValue({ response: { status: 409 } });
  await renderDraft();
  await act(async () => setValue(field("Claimant name")[0], "आशा राव"));
  await act(async () => $("chat-draft-pdf").click());
  await flush();
  expect($("chat-draft-error").textContent).toBe(NO_HINDI_PDF);
});

test("a Hindi draft keeps the Word download and explains why PDF is off", async () => {
  await renderDraft({ ...DRAFT, pdf: false });
  expect($("chat-draft-pdf").disabled).toBe(true);
  expect($("chat-draft-docx").disabled).toBe(false);
  expect($("chat-draft").textContent).toContain(NO_HINDI_PDF);
});

test("panel sits right on desktop and below on phones; fields and buttons are full width; tokens only", async () => {
  await renderDraft();
  const grid = $("chat-draft-text").parentElement.className;
  expect(grid).toMatch(/lg:grid-cols-\[minmax\(0,1fr\)_15rem\]/);
  expect(grid).not.toMatch(/(^| )grid( |$)/); // stacked (draft, then panel) below lg
  for (const el of [field("Date of notice")[0], $("chat-draft-docx"), $("chat-draft-pdf")]) {
    expect(el.className).toMatch(/(^| )w-full( |$)/);
  }
  expect($("chat-draft").outerHTML).not.toMatch(/(bg|text|border)-(white|black|gray|slate|red|amber)/);
});

test("a malformed draft is ignored", () => {
  expect(normalizeDraft({ blocks: [] })).toBeNull();
  expect(normalizeDraft({ draft_id: "d", blocks: [{ style: "script", text: "x" }] }).blocks).toEqual([]);
});
