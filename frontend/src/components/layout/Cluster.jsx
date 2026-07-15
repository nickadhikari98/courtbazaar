import React from "react";
import { cn } from "@/lib/utils";

const GAP = { "2xs": "gap-1", xs: "gap-2", sm: "gap-3", md: "gap-4", lg: "gap-6", xl: "gap-8" };

/** Horizontal flex with a consistent gap from the spacing scale (PRODUCT_DESIGN_SYSTEM.md §4.2).
 * `align` must be a valid Tailwind `items-*` suffix ("center" | "start" | "end" | "baseline" | "stretch") —
 * it's interpolated directly into the class name, so an invalid value silently produces no effect. */
export default function Cluster({ gap = "md", align = "center", className, children, ...props }) {
  return (
    <div className={cn("flex flex-row", `items-${align}`, GAP[gap] || gap, className)} {...props}>
      {children}
    </div>
  );
}
