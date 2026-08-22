import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, setToken, getToken } from "../lib/api";

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

  useEffect(() => {
    api.get("/config/public").then(({ data }) => {
      setGoogleOAuthEnabled(!!data.google_oauth_enabled);
      setGoogleClientId(data.google_client_id || null);
    }).catch(() => {});
  }, []);

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
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { checkAuth(); }, [checkAuth]);

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
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
