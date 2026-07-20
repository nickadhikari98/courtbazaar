import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, setToken, getToken } from "../lib/api";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    const tok = getToken();
    if (!tok) {
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch (e) {
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // If returning from OAuth callback, skip the /me check
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    if (window.location.hash?.includes("session_id=")) {
      setLoading(false);
      return;
    }
    checkAuth();
  }, [checkAuth]);

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

  const googleLogin = (role = "advocate") => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + `/auth/callback?role=${role}`;
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const exchangeGoogleSession = async (sessionId, role) => {
    const { data } = await api.post("/auth/google/session", { session_id: sessionId, role });
    setToken(data.token);
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch (e) {}
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
      user, loading, login, register, otpRequest, otpVerify, googleLogin,
      exchangeGoogleSession, logout, refresh, checkAuth, hasRole, hasCapability,
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
