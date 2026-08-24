import React, { useEffect, useRef } from "react";
import { API_BASE } from "@/lib/api";

const GSI_SCRIPT_SRC = "https://accounts.google.com/gsi/client";

let gsiScriptPromise = null;
function loadGsiScript() {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (!gsiScriptPromise) {
    gsiScriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = GSI_SCRIPT_SRC;
      script.async = true;
      script.defer = true;
      script.onload = resolve;
      script.onerror = () => { gsiScriptPromise = null; reject(new Error("Failed to load Google Identity Services")); };
      document.head.appendChild(script);
    });
  }
  return gsiScriptPromise;
}

/* "Continue with Google" — shared between Login.jsx and Register.jsx.
   Renders Google's own Sign In With Google button directly (Google Identity
   Services, client-side), so the only branding a user ever sees on Google's
   own "Choose an account" screen is this app's own OAuth consent screen (see
   .env.example's GOOGLE_CLIENT_ID), never a third party's domain.

   ux_mode: "redirect" (not GIS's default "popup") — the popup mode's own
   window.open call got silently blocked by Chrome on a real click (GIS logs
   "Failed to open popup window ... Maybe blocked by the browser" when this
   happens), a known reliability gap with that mode. Redirect mode instead
   does a real top-level POST navigation straight to the backend's
   /auth/google/callback (see server.py), which verifies the credential and
   redirects back to /auth/google/complete with a session token — no popup
   to block, still no broker in between.

   `role` rides along as a query param on login_uri itself, since redirect
   mode is a real page navigation with no JS callback left to hand a role to
   (Register.jsx's role picker needs this for brand-new accounts).

   Renders nothing when the backend hasn't got a Client ID configured (see
   AuthContext's googleClientId, fetched from /config/public). */
export default function GoogleAuthButton({ clientId, role, enabled = true }) {
  const containerRef = useRef(null);
  const loginUri = `${API_BASE}/auth/google/callback${role ? `?role=${encodeURIComponent(role)}` : ""}`;

  useEffect(() => {
    if (!enabled || !clientId || !containerRef.current) return;
    let cancelled = false;
    loadGsiScript().then(() => {
      if (cancelled || !containerRef.current) return;
      window.google.accounts.id.initialize({
        client_id: clientId,
        ux_mode: "redirect",
        login_uri: loginUri,
      });
      window.google.accounts.id.renderButton(containerRef.current, {
        type: "standard",
        theme: "outline",
        size: "large",
        text: "continue_with",
        shape: "rectangular",
        logo_alignment: "center",
        width: Math.min(containerRef.current.clientWidth || 320, 400),
      });
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [enabled, clientId, loginUri]);

  if (!enabled || !clientId) return null;
  return <div ref={containerRef} className="w-full flex justify-center" data-testid="google-auth-btn" />;
}
