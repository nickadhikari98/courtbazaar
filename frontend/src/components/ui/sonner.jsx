import React from "react";
import { Toaster as Sonner } from "sonner";

/**
 * Wraps the `sonner` package so toast styling is themed through the same
 * ui/ path as every other primitive, instead of every page importing
 * `sonner` directly (see DESIGN_SYSTEM_AUDIT.md §2.I). `toast(...)` itself
 * still comes straight from the `sonner` package — only the <Toaster/>
 * mount point moves here.
 */
export function Toaster(props) {
  return <Sonner position="top-right" richColors {...props} />;
}
