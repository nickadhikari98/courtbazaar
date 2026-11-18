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

global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
Element.prototype.scrollIntoView = jest.fn();

const USER = { user_id: "u1", name: "Jay Dee", email: "jay@example.com" };
const UPLOAD = { upload_id: "upl_1", file_name: "lease.pdf", kind: "pdf", pages: 2, chars: 140, expires_at: "2026-12-18T00:00:00+00:00" };

let container;
let root;
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  mockAuth.user = USER;
  api.get.mockImplementation(() => Promise.resolve({ data: [] }));
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.body.innerHTML = "";
  jest.clearAllMocks();
});

const $ = (testId) => document.querySelector(`[data-testid="${testId}"]`);
const $$ = (testId) => [...document.querySelectorAll(`[data-testid="${testId}"]`)];
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
async function render() {
  await act(async () => root.render(<MemoryRouter><InstantLegalHelpChat /></MemoryRouter>));
  await flush();
}
async function pick(name, size = 1000) {
  await pickMany([[name, size]]);
}
async function pickMany(specs) {
  const files = specs.map(([name, size = 1000]) => {
    const file = new File(["x"], name);
    Object.defineProperty(file, "size", { value: size });
    return file;
  });
  const input = $("instant-legal-help-file-input");
  Object.defineProperty(input, "files", { value: files, configurable: true });
  await act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
  await flush();
}
const uploadCalls = () => api.post.mock.calls.filter(([url]) => /\/uploads$/.test(url));

test("a guest gets an inline sign-in message and nothing is uploaded", async () => {
  mockAuth.user = null;
  await render();
  await act(async () => $("instant-legal-help-attach").click());
  expect($("chat-upload-error").textContent).toMatch(/logged-in users only/);
  expect(api.post).not.toHaveBeenCalled();
});

test("wrong type and too-large files are refused inline before upload", async () => {
  await render();
  await pick("notes.txt");
  expect($("chat-upload-failed").textContent).toMatch(/notes\.txt.*Only PDF and Word/);
  await pick("big.pdf", 11 * 1024 * 1024);
  expect($$("chat-upload-failed").map((el) => el.textContent)).toEqual([
    expect.stringMatching(/notes\.txt/), expect.stringMatching(/big\.pdf.*too large/)]);
  expect(api.post).not.toHaveBeenCalled();
});

test("attaching in a new chat creates the chat, uploads, offers quick actions, and the sent message carries the chip", async () => {
  api.post.mockImplementation((url) => {
    if (url === "/ai/chats") return Promise.resolve({ data: { conversation_id: "conv_1" } });
    if (url === "/ai/chats/conv_1/uploads") return Promise.resolve({ data: UPLOAD });
    return Promise.resolve({ data: { conversation_id: "conv_1", reply: "Summary (lease.pdf, page 1)." } });
  });
  await render();
  await pick("lease.pdf");
  expect(api.post.mock.calls[0][0]).toBe("/ai/chats");
  const [, form, opts] = uploadCalls()[0];
  expect(form.get("file").name).toBe("lease.pdf");
  expect(typeof opts.onUploadProgress).toBe("function");
  expect($$("chat-upload-file").map((el) => el.textContent)).toEqual(["lease.pdf"]);
  expect($("chat-upload-retention").textContent).toMatch(/Kept for 30 days/);
  expect($$("instant-legal-help-suggestion-0").map((el) => el.textContent)).toEqual(["Summarise this document"]);
  expect($("instant-legal-help-suggestion-2").textContent).toBe("Check it against the rules");

  await act(async () => $("instant-legal-help-suggestion-0").click());
  await flush();
  const chat = api.post.mock.calls.find(([url]) => url === "/ai/chat")[1];
  expect(chat).toMatchObject({ conversation_id: "conv_1", message: "Summarise this document", upload_ids: ["upl_1"] });
  expect($("instant-legal-help-msg-file").textContent).toBe("lease.pdf");
  expect($("chat-upload-quick-actions")).toBeNull(); // asked about already
});

test("a scanned PDF shows the server's message inline; removing a file deletes it", async () => {
  api.post.mockImplementation((url) => {
    if (url === "/ai/chats") return Promise.resolve({ data: { conversation_id: "conv_2" } });
    if (url.endsWith("/uploads") && !uploadCalls().slice(0, -1).length) {
      return Promise.reject({ response: { status: 422, data: { detail: "This PDF looks scanned: it has no readable text layer." } } });
    }
    return Promise.resolve({ data: UPLOAD });
  });
  api.delete.mockResolvedValue({ data: { ok: true } });
  await render();
  await pick("scan.pdf");
  expect($("chat-upload-failed").textContent).toMatch(/scan\.pdf.*looks scanned/);
  expect($("chat-upload-file")).toBeNull();

  await pick("lease.pdf");
  expect($("chat-upload-failed").textContent).toMatch(/scan\.pdf/); // the failed file keeps its own row
  expect($("chat-upload-error")).toBeNull();
  await act(async () => $("chat-upload-remove").click());
  await flush();
  expect(api.delete).toHaveBeenCalledWith("/ai/chats/conv_2/uploads/upl_1");
  expect($("chat-upload-file")).toBeNull();
});

test("of three files picked together, the one the server rejects shows its reason by name and gets no chip", async () => {
  const rejected = "Document-2_ServiceWorkflows(Updated).docx";
  api.post.mockImplementation((url, form) => {
    if (url === "/ai/chats") return Promise.resolve({ data: { conversation_id: "conv_3" } });
    const name = form.get("file").name;
    if (name === rejected) {
      return Promise.reject({ response: { status: 422, data: { detail: [{ type: "value_error", loc: ["body", "file"] }] } } });
    }
    return Promise.resolve({ data: { ...UPLOAD, upload_id: `upl_${name}`, file_name: name } });
  });
  await render();
  await pickMany([["a.pdf"], [rejected], ["c.docx"]]);
  expect(uploadCalls()).toHaveLength(3); // one request per file
  expect($$("chat-upload-file").map((el) => el.textContent)).toEqual(["a.pdf", "c.docx"]);
  expect($$("chat-upload-failed")).toHaveLength(1);
  const failed = $("chat-upload-failed");
  expect(failed.getAttribute("role")).toBe("alert");
  expect(failed.querySelector('[data-testid="chat-upload-failed-name"]').textContent).toBe(rejected);
  expect(failed.textContent).toMatch(/couldn't read this file/);
  expect(failed.textContent).not.toMatch(/value_error|body/); // never the raw validation list

  await act(async () => failed.querySelector("button").click());
  expect($("chat-upload-failed")).toBeNull();
});
