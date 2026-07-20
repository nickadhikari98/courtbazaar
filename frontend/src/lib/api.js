import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("cb_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      const hadToken = !!localStorage.getItem("cb_token");
      const detail = err.response?.data?.detail;
      if (hadToken) {
        localStorage.removeItem("cb_token");
        // A deactivated/deleted account (see server.py's get_current_user) is
        // the one 401 case that needs an explicit explanation + a forced,
        // full-page redirect (not client-side navigate — there's no router
        // instance reachable from an axios interceptor, and a hard reload
        // also guarantees any in-memory user state is wiped, not just the
        // token) rather than just silently rejecting the failed request.
        if (typeof detail === "string" && detail.toLowerCase().includes("deactivated") && window.location.pathname !== "/login") {
          sessionStorage.setItem("cb_auth_message", detail);
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(err);
  }
);

export const setToken = (token) => {
  if (token) localStorage.setItem("cb_token", token);
  else localStorage.removeItem("cb_token");
};

export const getToken = () => localStorage.getItem("cb_token");

export const formatINR = (n) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(n || 0);
