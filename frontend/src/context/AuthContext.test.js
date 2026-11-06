import React from "react";
import { createRoot } from "react-dom/client";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { api, setToken, getToken } from "@/lib/api";

const { act } = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// Fake backend: /auth/me answers for whichever token the request carried.
// `sent` records the token on every request, so tests can assert identity.
const USERS = {
  tokA: { user_id: "user_a", name: "Proxy Counsel A", capabilities: ["can_practice_proxy_counsel"] },
  tokA2: { user_id: "user_a", name: "Proxy Counsel A", capabilities: ["can_practice_proxy_counsel"] },
  tokB: { user_id: "user_b", name: "Client B", capabilities: ["can_hire_proxy_counsel"] },
  tokC: { user_id: "user_c", name: "Admin C", capabilities: ["is_admin"] },
};
let sent;
let delays; // token -> promise to wait on before answering /auth/me
const unauthorized = (config) => {
  const err = new Error("401");
  err.config = config;
  err.response = { status: 401, data: { detail: "Not authenticated" } };
  return err;
};
const tokenOf = (config) => String(config.headers?.Authorization || "").replace(/^Bearer /, "") || null;
api.defaults.adapter = async (config) => {
  const token = tokenOf(config);
  sent.push({ url: config.url, token });
  if (delays[token]) await delays[token];
  if (config.url === "/config/public") return { data: {}, status: 200, headers: {}, config };
  if (config.url === "/auth/login") return { data: { token: "tokB", user: USERS.tokB }, status: 200, headers: {}, config };
  // A valid login whose /auth/me hits a deploy restart / outage, not a bad token.
  if (token === "tokServerDown") throw Object.assign(new Error("503"), { config, response: { status: 503, data: {} } });
  if (token === "tokNetworkDown") throw Object.assign(new Error("Network Error"), { config });
  if (!USERS[token]) throw unauthorized(config);
  return { data: USERS[token], status: 200, headers: {}, config };
};

// Simulates another tab writing the shared token: jsdom (like browsers) does
// not fire `storage` in the writing window, so dispatch it as the other tabs see it.
const otherTabWrites = async (token) => {
  if (token) localStorage.setItem("cb_token", token);
  else localStorage.removeItem("cb_token");
  await act(async () => {
    window.dispatchEvent(new StorageEvent("storage", { key: "cb_token", newValue: token }));
  });
  await flush();
};
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });

let mounts;
function Probe() {
  const { user, loading } = useAuth();
  React.useEffect(() => { mounts += 1; }, []);
  return <div data-testid="who">{loading ? "loading" : user ? user.name : "signed out"}</div>;
}

let container;
let root;
const who = () => container.querySelector("[data-testid=who]").textContent;
const renderAs = async (token) => {
  setToken(token);
  await act(async () => { root.render(<AuthProvider><Probe /></AuthProvider>); });
  await flush();
};

beforeEach(() => {
  sent = [];
  delays = {};
  mounts = 0;
  localStorage.clear();
  setToken(null);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

test("a login in another tab never changes the token this tab's requests carry", async () => {
  setToken("tokA");
  localStorage.setItem("cb_token", "tokB"); // other tab logged in; no sync yet
  await api.get("/practice/profile").catch(() => {});
  expect(sent.at(-1).token).toBe("tokA");
});

test("account switch in another tab: this tab shows the new user, remounts, and sends the new token", async () => {
  await renderAs("tokA");
  expect(who()).toBe("Proxy Counsel A");
  expect(mounts).toBe(1);

  await otherTabWrites("tokB");
  expect(who()).toBe("Client B");
  expect(mounts).toBe(2); // old account's page state discarded
  expect(getToken()).toBe("tokB");
  sent = [];
  await api.get("/practice/profile").catch(() => {});
  expect(sent[0].token).toBe("tokB");
});

test("while the new token is being verified, requests still go out as the tab's own user", async () => {
  await renderAs("tokA");
  let release;
  delays.tokB = new Promise((r) => { release = r; });
  localStorage.setItem("cb_token", "tokB");
  act(() => { window.dispatchEvent(new StorageEvent("storage", { key: "cb_token", newValue: "tokB" })); });

  await api.get("/practice/profile").catch(() => {});
  expect(sent.at(-1)).toEqual({ url: "/practice/profile", token: "tokA" });
  expect(who()).toBe("Proxy Counsel A");

  release();
  await flush();
  expect(who()).toBe("Client B");
});

test("the same user logging in again in another tab swaps the token without a remount", async () => {
  await renderAs("tokA");
  await otherTabWrites("tokA2");
  expect(who()).toBe("Proxy Counsel A");
  expect(mounts).toBe(1);
  expect(getToken()).toBe("tokA2");
});

test("logout in another tab signs this tab out and stops sending the old token", async () => {
  await renderAs("tokA");
  await otherTabWrites(null);
  expect(who()).toBe("signed out");
  expect(mounts).toBe(2);
  sent = [];
  await api.get("/practice/profile").catch(() => {});
  expect(sent[0].token).toBeNull();
});

test("an unusable token from another tab signs this tab out instead of keeping the old identity", async () => {
  await renderAs("tokA");
  await otherTabWrites("garbage");
  expect(who()).toBe("signed out");
  expect(getToken()).toBeNull();
});

test("rapid switches settle on the latest account even if an older check answers last", async () => {
  await renderAs("tokA");
  let releaseB;
  delays.tokB = new Promise((r) => { releaseB = r; });
  localStorage.setItem("cb_token", "tokB");
  act(() => { window.dispatchEvent(new StorageEvent("storage", { key: "cb_token", newValue: "tokB" })); });
  await otherTabWrites("tokC");
  expect(who()).toBe("Admin C");

  releaseB(); // B's /auth/me answers late — must not win
  await flush();
  expect(who()).toBe("Admin C");
  expect(getToken()).toBe("tokC");
});

test("a 401 for this tab's stale token does not wipe a newer login another tab stored", async () => {
  setToken("expired");
  localStorage.setItem("cb_token", "tokB");
  await api.get("/practice/profile").catch(() => {});
  expect(localStorage.getItem("cb_token")).toBe("tokB");
  expect(getToken()).toBeNull();
});

test("a 401 for the shared token still clears it, as before", async () => {
  setToken("expired");
  await api.get("/practice/profile").catch(() => {});
  expect(localStorage.getItem("cb_token")).toBeNull();
});

test("this tab's own login is unchanged: no remount, token shared with other tabs", async () => {
  let auth;
  function Grab() { auth = useAuth(); return null; }
  setToken(null);
  await act(async () => { root.render(<AuthProvider><Probe /><Grab /></AuthProvider>); });
  await flush();
  expect(who()).toBe("signed out");

  await act(async () => { await auth.login("b@example.com", "x"); });
  expect(who()).toBe("Client B");
  expect(mounts).toBe(1);
  expect(localStorage.getItem("cb_token")).toBe("tokB");
  expect(getToken()).toBe("tokB");
});

// B1: the old account's UI must already be gone at the moment this tab's
// token switches. Run outside act() on purpose: act() flushes renders itself
// and would hide a render React merely scheduled for a later task.
test("when the token switches, the old account's UI is already unmounted and the new UI fetches with the new token", async () => {
  function FetchOnMount() {
    React.useEffect(() => { api.get("/practice/profile").catch(() => {}); }, []);
    return null;
  }
  setToken("tokA");
  await act(async () => { root.render(<AuthProvider><Probe /><FetchOnMount /></AuthProvider>); });
  await flush();
  expect(who()).toBe("Proxy Counsel A");

  globalThis.IS_REACT_ACT_ENVIRONMENT = false;
  try {
    sent = [];
    localStorage.setItem("cb_token", "tokB");
    window.dispatchEvent(new StorageEvent("storage", { key: "cb_token", newValue: "tokB" }));
    // Microtasks only: resolves the /auth/me check but never runs a later task,
    // which is where a merely-scheduled React render would happen.
    for (let i = 0; i < 100 && getToken() !== "tokB"; i += 1) await Promise.resolve();
    expect(getToken()).toBe("tokB");
    expect(who()).toBe("Client B");
    expect(mounts).toBe(2);
    await new Promise((r) => setTimeout(r, 0)); // let axios dispatch the new tree's request
    expect(sent.filter((r) => r.url === "/practice/profile").map((r) => r.token)).toEqual(["tokB"]);
  } finally {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  }
});

// B2: only a 401 may delete the shared login.
test.each([
  ["a 503 (deploy restart)", "tokServerDown"],
  ["a network error", "tokNetworkDown"],
])("%s on startup shows this tab signed out but keeps the shared login for other tabs", async (_label, token) => {
  await renderAs(token);
  expect(who()).toBe("signed out");
  expect(localStorage.getItem("cb_token")).toBe(token);
  expect(getToken()).toBe(token);
});

test("a 401 on startup still clears the shared login", async () => {
  await renderAs("expired");
  expect(who()).toBe("signed out");
  expect(localStorage.getItem("cb_token")).toBeNull();
  expect(getToken()).toBeNull();
});

test("a 401 on startup does not clear a newer login another tab stored meanwhile", async () => {
  let release;
  delays.expired = new Promise((r) => { release = r; });
  setToken("expired");
  await act(async () => { root.render(<AuthProvider><Probe /></AuthProvider>); });
  localStorage.setItem("cb_token", "tokB"); // other tab logs in while /auth/me is in flight
  release();
  await flush();
  expect(localStorage.getItem("cb_token")).toBe("tokB");
});
