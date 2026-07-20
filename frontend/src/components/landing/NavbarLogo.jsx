import React from "react";
import Logo from "@/components/shared/Logo";

/* Thin wrapper kept for backward compatibility — LandingNav.jsx and any
   other existing import of NavbarLogo needs no change. The canonical
   implementation now lives in components/shared/Logo.jsx, shared with the
   rest of the app (sidebar, auth pages, loading screens). */
export default function NavbarLogo({ to = "/", className = "" }) {
  return <Logo to={to} size="lg" className={className} />;
}
