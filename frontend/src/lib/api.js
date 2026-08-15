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
    // /auth/login's 401s (bad password, deactivated account, ...) describe
    // the credentials just typed into the login form, not the validity of
    // whatever token is currently sitting in localStorage — that token
    // wasn't even what auth'd this request (login doesn't check it) and may
    // belong to a completely unrelated, still-valid session in another tab
    // (localStorage is shared across same-origin tabs). Clearing it here
    // would silently log that other tab out.
    const isLoginRequest = err.config?.url?.includes("/auth/login");
    if (err?.response?.status === 401 && !isLoginRequest) {
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

/* Normalizes an axios error's response body into one human-readable string.
   FastAPI's hand-raised HTTPExceptions return `detail` as a plain string,
   but its automatic Pydantic validation errors (422) return `detail` as an
   array of {msg, loc, ...} objects instead — rendering that array directly
   (e.g. via toast.error(err.response.data.detail)) shows "[object Object]"
   rather than the actual message. Reusable at any api.js call site, not
   just the one that first needed it. */
export const getErrorMessage = (err, fallback = "Something went wrong") => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    const messages = detail.map((d) => (typeof d === "string" ? d : d?.msg)).filter(Boolean);
    if (messages.length) return messages.join(" ");
  }
  return fallback;
};

/* Downloads a file from an authenticated backend route (CSV/JSON exports,
   templates, ...) by fetching it as a blob and triggering a save via a
   throwaway <a> — axios's JSON-oriented client doesn't suit a binary
   response like this. Every export button (reconciliation, settlements,
   bulk-import template, DPDP data) hand-rolled this same fetch+blob+anchor
   sequence; `path` (starting with "/", api-relative) and `filename` are the
   only things that actually varied between them. */
export const downloadFile = async (path, filename) => {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};
