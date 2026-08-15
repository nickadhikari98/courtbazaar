import React from "react";
import { cn } from "@/lib/utils";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { PRIORITY_OPTIONS } from "@/config/serviceRequestFields";

/* Priority radio group — identical in LegalServiceRequestForm and
   ProxyCounselCaseDetailsForm; `required` only controls whether the "*" and
   error text show (both forms pre-fill "Normal", so this never blocks
   submit either way). `compact` matches the case-brief form's smaller
   heading size. */
export default function PriorityField({ value, onChange, error, required = false, compact = false }) {
  return (
    <div>
      <div className={cn("font-display font-bold mb-2", compact && "text-sm")}>Priority{required && " *"}</div>
      <RadioGroup value={value} onValueChange={onChange} className="flex flex-wrap gap-4">
        {PRIORITY_OPTIONS.map((p) => (
          <label key={p} className="flex items-center gap-2 text-sm font-medium">
            <RadioGroupItem value={p} /> {p}
          </label>
        ))}
      </RadioGroup>
      {error && <p className="text-xs text-destructive mt-1">{error}</p>}
    </div>
  );
}
