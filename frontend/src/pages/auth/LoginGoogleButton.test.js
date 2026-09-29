/* Google sign-in visibility on the Login page. The "Or continue with" /
   Continue with Google section renders only once AuthContext has learned
   from /config/public that Google OAuth is enabled. That fetch ran once at
   app start and swallowed any failure, so a single failed request (backend
   restarting, a network blip) hid Google sign-in for the rest of the session.
   Real AuthProvider + Login; only the API module is mocked. */
import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Routes, Route, useNavigate } from "react-router-dom";

// react-router v7 publishes "react-router/dom" only through package.json
// "exports", which CRA's jest resolver doesn't read — same shim as
// PracticeRespond.test.js.
jest.mock("react-router/dom", () => {
  const { TextEncoder, TextDecoder } = require("util");
  Object.assign(global, { TextEncoder, TextDecoder });
  return require("react-router/dist/development/dom-export.js");
}, { virtual: true });
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn(), warning: jest.fn() } }));
jest.mock("@/lib/api", () => ({
  api: { get: jest.fn(), post: jest.fn() },
  API_BASE: "http://backend.test/api",
  getToken: () => null,
  setToken: jest.fn(),
  getErrorMessage: (e, fallback) => fallback,
}));

const { act } = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { api } = require("@/lib/api");
const { AuthProvider } = require("@/context/AuthContext");
const Login = require("@/pages/auth/Login").default;

const ENABLED = { data: { google_oauth_enabled: true, google_client_id: "test-client-id.apps.googleusercontent.com" } };
const DISABLED = { data: { google_oauth_enabled: false, google_client_id: null } };
const networkError = () => Promise.reject(Object.assign(new Error("Network Error"), { code: "ERR_NETWORK" }));

let container, root;

function Elsewhere() {
  global.__navigate = useNavigate(); // lets a test move to /login inside the same app session
  return <div>elsewhere</div>;
}

function configResponses(...responses) {
  // /config/public answers from the list in order (last one repeats);
  // nothing else is expected to be fetched on the Login page.
  let i = 0;
  api.get.mockImplementation((url) => {
    if (url !== "/config/public") return Promise.reject(new Error(`unexpected GET ${url}`));
    const r = responses[Math.min(i++, responses.length - 1)];
    return typeof r === "function" ? r() : Promise.resolve(r);
  });
}

async function render(path = "/login") {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <AuthProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/elsewhere" element={<Elsewhere />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    );
  });
}

const flush = () => act(async () => { await Promise.resolve(); });
const advance = (ms) => act(async () => { jest.advanceTimersByTime(ms); await Promise.resolve(); });
const googleShown = () => /or continue with/i.test(container.textContent);
const configCalls = () => api.get.mock.calls.filter(([u]) => u === "/config/public").length;

beforeEach(() => {
  jest.useFakeTimers();
  api.get.mockReset();
  document.head.querySelectorAll('script[src*="accounts.google.com"]').forEach((s) => s.remove());
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  jest.useRealTimers();
});

test("Google sign-in shows when the backend reports it enabled", async () => {
  configResponses(ENABLED);
  await render();
  await flush();
  expect(googleShown()).toBe(true);
  // GoogleAuthButton starts loading Google's own button script.
  expect(document.head.querySelector('script[src="https://accounts.google.com/gsi/client"]')).not.toBeNull();
});

test("a failed /config/public at startup is retried, so Google sign-in comes back", async () => {
  // Startup fetch and Login's own on-open check both fail; the backend is
  // back for the next (timed) retry.
  configResponses(networkError, networkError, ENABLED);
  await render();
  await flush();
  expect(googleShown()).toBe(false);
  await advance(1000);
  await flush();
  expect(googleShown()).toBe(true);
});

test("opening /login re-checks the config if Google sign-in isn't known to be enabled", async () => {
  configResponses(networkError); // backend down for longer than every startup retry...
  await render("/elsewhere");
  for (let i = 0; i < 8; i++) { await advance(15000); await flush(); } // each retry is scheduled after the previous one fails
  const callsWhileDown = configCalls();
  expect(googleShown()).toBe(false);
  configResponses(ENABLED);      // ...then it recovers, and the user navigates to /login in the same session
  await act(async () => { global.__navigate("/login"); });
  await flush();
  expect(googleShown()).toBe(true);
  expect(callsWhileDown).toBe(4); // 1 attempt + 3 bounded retries — no endless polling
});

test("stays hidden when the backend reports Google OAuth disabled (e.g. local dev)", async () => {
  configResponses(DISABLED);
  await render();
  await advance(60000);
  expect(googleShown()).toBe(false);
});

test("email/password sign-in is always rendered", async () => {
  configResponses(networkError);
  await render();
  await flush();
  expect(container.querySelector('input[type="email"]')).not.toBeNull();
  expect(container.querySelector('input[type="password"]')).not.toBeNull();
  expect([...container.querySelectorAll("button")].some((b) => /sign in/i.test(b.textContent))).toBe(true);
});
