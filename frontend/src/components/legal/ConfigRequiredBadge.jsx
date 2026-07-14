import React from "react";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

/* Visible flag for a fact that isn't confirmed yet (an address, an email, a
   certification, a date) — deliberately never hidden and never replaced with
   a guessed value, so nothing inaccurate ships to production silently. */
export default function ConfigRequiredBadge({ className, label = "Configuration Required" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 bg-amber-50 text-amber-800 border border-amber-300 text-[11px] font-bold uppercase tracking-wide px-2.5 py-1 rounded-full",
        className
      )}
    >
      <AlertTriangle className="w-3 h-3" strokeWidth={2.5} />
      {label}
    </span>
  );
}
