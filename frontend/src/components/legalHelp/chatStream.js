import { API_BASE, getToken, setToken } from "@/lib/api";

/* Client for POST /ai/chat/stream (ai_chat.stream_chat_events). fetch, not
   EventSource, because the chat is a POST, and not axios, which can't read a
   response as it arrives. Failures are thrown in the shape of an axios error,
   so the chat's existing error handling applies unchanged. */

const DROPPED = { code: "ECONNABORTED" };

/* Splits complete SSE frames off a text buffer. Exported for tests. */
export function drainEvents(buffer) {
  const frames = buffer.split("\n\n");
  const rest = frames.pop();
  const events = [];
  for (const frame of frames) {
    const data = frame.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).join("");
    if (!data) continue;
    try {
      events.push(JSON.parse(data));
    } catch {
      // A malformed frame is skipped; a missing answer is still caught at end of stream.
    }
  }
  return { events, rest };
}

export async function streamChat(payload, { idleMs, signal, onStatus }) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal.addEventListener("abort", abort);
  let idle;
  let timedOut = false;
  const resetIdle = () => {
    clearTimeout(idle);
    idle = setTimeout(() => { timedOut = true; abort(); }, idleMs);
  };
  const token = getToken();
  try {
    resetIdle();
    const res = await fetch(`${API_BASE}/ai/chat/stream`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (!res.ok) {
      if (res.status === 401 && token) setToken(null); // as the api client does for a stale token
      throw { response: { status: res.status, data: await res.json().catch(() => ({})) } }; // eslint-disable-line no-throw-literal
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) throw DROPPED; // closed without an answer
      resetIdle();
      const { events, rest } = drainEvents(buffer + decoder.decode(value, { stream: true }));
      buffer = rest;
      for (const event of events) {
        if (event.type === "status") onStatus(event);
        else if (event.type === "answer") return event.data;
        else if (event.type === "error") {
          throw { response: { status: event.status || 500, data: { detail: event.text } } }; // eslint-disable-line no-throw-literal
        }
      }
    }
  } catch (err) {
    if (err?.response) throw err;
    if (timedOut) throw DROPPED;
    if (signal.aborted) throw err; // "New chat" or leaving the page: not a failure
    throw DROPPED; // network dropped mid-stream
  } finally {
    clearTimeout(idle);
    signal.removeEventListener("abort", abort);
  }
}
