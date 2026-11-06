import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { flushSync } from "react-dom";
import { api, setToken, getToken, adoptToken } from "../lib/api";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  // Whether the server has Google OAuth configured at all (GOOGLE_OAUTH_ENABLED
  // + a real GOOGLE_CLIENT_ID) — starts false so "Continue with Google"
  // doesn't flash on then off in environments where it isn't set, e.g. local
  // dev. googleClientId feeds GoogleAuthButton's own Google Identity
  // Services init directly — see server.py's /config/public.
  const [googleOAuthEnabled, setGoogleOAuthEnabled] = useState(false);
  const [googleClientId, setGoogleClientId] = useState(null);

  const loadPublicConfig = useCallback(async () => {
    const { data } = await api.get("/config/public");
    setGoogleOAuthEnabled(!!data.google_oauth_enabled);
    setGoogleClientId(data.google_client_id || null);
  }, []);

  // This used to be fetched exactly once, with any failure swallowed — so a
  // single failed request at app start (backend restarting, a network blip)
  // hid "Continue with Google" for the rest of the session. Retry a few
  // times with backoff; Login/Register also re-check via refreshPublicConfig
  // when they open, in case the backend was down for longer than that.
  useEffect(() => {
    let cancelled = false;
    let timer = null;
    const retryDelaysMs = [1000, 3000, 10000];
    const attempt = (i) => {
      loadPublicConfig().catch(() => {
        if (!cancelled && i < retryDelaysMs.length) timer = setTimeout(() => attempt(i + 1), retryDelaysMs[i]);
      });
    };
    attempt(0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [loadPublicConfig]);

  const refreshPublicConfig = useCallback(() => loadPublicConfig().catch(() => {}), [loadPublicConfig]);

  const checkAuth = useCallback(async () => {
    const tok = getToken();
    if (!tok) {
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch {
      // No user data either way. A 401 means the token is bad and api.js has
      // already dropped it (only if it's still the shared one). A network
      // error or 5xx (e.g. a deploy restart) must not delete the shared login:
      // that would sign every other tab out too. Reloading retries.
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { checkAuth(); }, [checkAuth]);

  // Cross-tab sync. A login/logout in another tab rewrites the shared
  // cb_token; this tab keeps using its own pinned token (api.js) until /auth/me
  // confirms who the new one belongs to, then adopts it. A different account
  // (or a logout) bumps sessionKey, remounting the app below so no page keeps
  // the previous account's data on screen. The same account re-logging in
  // just swaps the token quietly. `storage` never fires in the tab that wrote
  // the value, and adoptToken doesn't write, so this can't loop.
  const [sessionKey, setSessionKey] = useState(0);
  const userIdRef = useRef(null);
  userIdRef.current = user?.user_id || null;

  useEffect(() => {
    let seq = 0;
    const onStorage = async (e) => {
      if (e.key !== "cb_token" && e.key !== null) return; // null = localStorage.clear()
      const next = localStorage.getItem("cb_token");
      if (next === getToken()) return;
      const mine = ++seq;
      let nextUser = null;
      if (next) {
        try {
          ({ data: nextUser } = await api.get("/auth/me", { headers: { Authorization: `Bearer ${next}` } }));
        } catch {
          nextUser = null; // unusable token: treat as logged out rather than keep the old identity
        }
      }
      // Superseded while /auth/me was in flight (another tab, or this tab's own
      // login/logout). A failed check may itself have cleared the shared token
      // (api.js 401 handling) — that still means "signed out", not superseded.
      const now = localStorage.getItem("cb_token");
      if (mine !== seq || (nextUser ? now !== next : now !== null && now !== next)) return;
      const nextId = nextUser?.user_id || null;
      // Token first, then render synchronously: no click or timer can run in
      // between, so the old account's UI is never live while requests carry
      // the new token. flushSync also runs the new tree's effects, which is
      // why the token must already be adopted before it.
      adoptToken(nextUser ? next : null);
      flushSync(() => {
        if (nextId !== userIdRef.current) setSessionKey((k) => k + 1);
        setUser(nextUser);
        setLoading(false);
      });
      userIdRef.current = nextId;
    };
    window.addEventListener("storage", onStorage);
    return () => { seq = Infinity; window.removeEventListener("storage", onStorage); };
  }, []);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    setToken(data.token);
    setUser(data.user);
    return data.user;
  };

  const register = async (payload) => {
    const { data } = await api.post("/auth/register", payload);
    setToken(data.token);
    setUser(data.user);
    return data.user;
  };

  const otpRequest = async (phone) => {
    const { data } = await api.post("/auth/otp/request", { phone });
    return data;
  };

  const otpVerify = async (phone, otp, name, role) => {
    const { data } = await api.post("/auth/otp/verify", { phone, otp, name, role });
    setToken(data.token);
    setUser(data.user);
    return data.user;
  };

  // GoogleAuthButton's redirect-mode flow lands the browser back on
  // /auth/google/complete with a ready-made session token in the URL
  // fragment — server.py's /auth/google/callback already verified the
  // credential against Google and issued this before redirecting, so this
  // is just "adopt the token", the same shape as login()/register() above
  // minus the network round-trip to get it.
  const completeGoogleLogin = async (token) => {
    setToken(token);
    const { data } = await api.get("/auth/me");
    setUser(data);
    return data;
  };

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch {}
    setToken(null);
    setUser(null);
  };

  const refresh = async () => {
    const { data } = await api.get("/auth/me");
    setUser(data);
    return data;
  };

  // `active_roles`/`capabilities` come from the backend's get_current_user
  // capability computation (server.py) — active_roles is the legacy-compatible
  // projection (includes the base `role` plus every professional profile type
  // the account has gained), capabilities is the forward-looking permission
  // check new dashboard code should prefer.
  const hasRole = (role) => !!user && (user.role === role || !!user.active_roles?.includes(role));
  const hasCapability = (capability) => !!user?.capabilities?.includes(capability);

  return (
    <AuthContext.Provider value={{
      user, loading, login, register, otpRequest, otpVerify, completeGoogleLogin,
      logout, refresh, checkAuth, hasRole, hasCapability, googleOAuthEnabled, googleClientId,
      refreshPublicConfig,
    }}>
      <React.Fragment key={sessionKey}>{children}</React.Fragment>
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
