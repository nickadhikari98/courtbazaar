import React, { useEffect, useState } from "react";
import { Toaster as Sonner } from "sonner";

/**
 * Wraps the `sonner` package so toast styling is themed through the same
 * ui/ path as every other primitive, instead of every page importing
 * `sonner` directly (see DESIGN_SYSTEM_AUDIT.md §2.I). `toast(...)` itself
 * still comes straight from the `sonner` package — only the <Toaster/>
 * mount point moves here.
 */
// Toasts follow a `dark` class on <body> (set only by the Instant Legal Help chat).
function useBodyDark() {
  const [dark, setDark] = useState(() => typeof document !== "undefined" && document.body.classList.contains("dark"));
  useEffect(() => {
    const observer = new MutationObserver(() => setDark(document.body.classList.contains("dark")));
    observer.observe(document.body, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
  return dark;
}

export function Toaster(props) {
  const dark = useBodyDark();
  return <Sonner position="top-right" richColors theme={dark ? "dark" : "light"} {...props} />;
}
