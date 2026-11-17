import { drainEvents, streamChat } from "./chatStream";

jest.mock("@/lib/api", () => ({ API_BASE: "/api", getToken: () => null, setToken: jest.fn() }));

const { TextEncoder, TextDecoder } = require("util");
Object.assign(global, { TextEncoder, TextDecoder });

function fakeStream(chunks) {
  const encoder = new TextEncoder();
  const queue = [...chunks];
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: async () => (queue.length ? { done: false, value: encoder.encode(queue.shift()) } : { done: true }),
      }),
    },
  };
}
const frame = (event) => `data: ${JSON.stringify(event)}\n\n`;
const call = (onStatus = jest.fn()) => streamChat({ message: "x" }, {
  idleMs: 1000, signal: new AbortController().signal, onStatus,
});

afterEach(() => { delete global.fetch; });

test("drainEvents keeps an incomplete frame for the next chunk", () => {
  const first = drainEvents(`${frame({ type: "status" })}data: {"type":`);
  expect(first.events).toEqual([{ type: "status" }]);
  expect(drainEvents(`${first.rest}"answer"}\n\n`).events).toEqual([{ type: "answer" }]);
});

test("drainEvents skips a malformed frame", () => {
  expect(drainEvents("data: {nope\n\n").events).toEqual([]);
});

test("reports each status and resolves with the answer", async () => {
  const onStatus = jest.fn();
  global.fetch = jest.fn().mockResolvedValue(fakeStream([
    frame({ type: "status", step: "searching", text: "Searching…" }),
    frame({ type: "status", step: "writing", text: "Writing…" }) + frame({ type: "answer", data: { reply: "Hi" } }),
  ]));
  await expect(call(onStatus)).resolves.toEqual({ reply: "Hi" });
  expect(onStatus.mock.calls.map(([e]) => e.step)).toEqual(["searching", "writing"]);
});

test("an error event carries its HTTP status", async () => {
  global.fetch = jest.fn().mockResolvedValue(fakeStream([frame({ type: "error", status: 404, text: "Gone" })]));
  await expect(call()).rejects.toMatchObject({ response: { status: 404 } });
});

test("a stream that ends without an answer is a dropped connection", async () => {
  global.fetch = jest.fn().mockResolvedValue(fakeStream([frame({ type: "status", step: "writing", text: "x" })]));
  await expect(call()).rejects.toEqual({ code: "ECONNABORTED" });
});

test("a network failure is a dropped connection", async () => {
  global.fetch = jest.fn().mockRejectedValue(new TypeError("Failed to fetch"));
  await expect(call()).rejects.toEqual({ code: "ECONNABORTED" });
});

test("silence past the idle limit times out", async () => {
  global.fetch = jest.fn((_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(new Error("aborted")));
  }));
  const pending = streamChat({ message: "x" }, { idleMs: 10, signal: new AbortController().signal, onStatus: jest.fn() });
  await expect(pending).rejects.toEqual({ code: "ECONNABORTED" });
});

test("a non-OK response keeps its status", async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 429, json: async () => ({ detail: "Slow down" }) });
  await expect(call()).rejects.toMatchObject({ response: { status: 429, data: { detail: "Slow down" } } });
});
