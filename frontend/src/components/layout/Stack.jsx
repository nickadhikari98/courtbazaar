import React from "react";
import { cn } from "@/lib/utils";

const GAP = { "2xs": "gap-1", xs: "gap-2", sm: "gap-3", md: "gap-4", lg: "gap-6", xl: "gap-8" };

/** Vertical flex with a consistent gap from the spacing scale (PRODUCT_DESIGN_SYSTEM.md §4.2). */
export default function Stack({ gap = "md", className, children, ...props }) {
  return (
    <div className={cn("flex flex-col", GAP[gap] || gap, className)} {...props}>
      {children}
    </div>
  );
}
