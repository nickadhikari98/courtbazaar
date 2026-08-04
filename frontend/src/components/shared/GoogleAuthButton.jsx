import React from "react";
import { Button } from "@/components/ui/button";

/* "Continue with Google" — shared between Login.jsx and Register.jsx.
   Renders nothing when the backend hasn't got GOOGLE_OAUTH_ENABLED set (see
   AuthContext's googleOAuthEnabled, fetched from /config/public) rather than
   showing a button that would 501 on click. */
export default function GoogleAuthButton({ onClick, label = "Continue with Google", enabled = true }) {
  if (!enabled) return null;
  return (
    <Button
      type="button"
      variant="outline"
      onClick={onClick}
      className="w-full h-12 font-bold border-2"
      data-testid="google-auth-btn"
    >
      <svg className="w-4 h-4 mr-2.5" viewBox="0 0 24 24" aria-hidden="true">
        <path fill="#4285F4" d="M23.49 12.27c0-.79-.07-1.54-.2-2.27H12v4.51h6.47c-.28 1.48-1.13 2.73-2.4 3.58v2.98h3.88c2.27-2.09 3.54-5.17 3.54-8.8z" />
        <path fill="#34A853" d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-2.98c-1.08.72-2.45 1.15-4.05 1.15-3.11 0-5.75-2.1-6.69-4.93H1.29v3.09C3.26 21.3 7.31 24 12 24z" />
        <path fill="#FBBC05" d="M5.31 14.33A7.19 7.19 0 0 1 4.93 12c0-.81.14-1.6.38-2.33V6.58H1.29A11.98 11.98 0 0 0 0 12c0 1.93.46 3.76 1.29 5.42l4.02-3.09z" />
        <path fill="#EA4335" d="M12 4.77c1.76 0 3.34.61 4.58 1.79l3.44-3.44C17.94 1.19 15.24 0 12 0 7.31 0 3.26 2.7 1.29 6.58l4.02 3.09C6.25 6.85 8.89 4.77 12 4.77z" />
      </svg>
      {label}
    </Button>
  );
}
