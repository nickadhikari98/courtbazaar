import React from "react";
import { cn } from "@/lib/utils";

/* The plain "Loading…" placeholder, hand-duplicated across page/section
   loading states with 2-3 drifting className variants (centered+muted here,
   plain there). Table-row loading already has its own primitive
   (ui/table.jsx's TableLoading) — this is for the non-table case. */
export default function Loading({ text = "Loading…", size = "md", className = "" }) {
  const sizePad = { sm: "py-6 text-sm", md: "py-10" };
  return (
    <div className={cn("text-center text-muted-foreground", sizePad[size] || sizePad.md, className)}>
      {text}
    </div>
  );
}
