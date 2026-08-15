import React from "react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";

/* The "Work Required" checkbox group + its "Other, please describe" note —
   identical markup in both LegalServiceRequestForm (the full multi-step
   intake) and ProxyCounselCaseDetailsForm (the post-payment case-brief
   step), which collect the same work_required field on two different
   screens of the same flow. `compact` matches the smaller heading size the
   case-brief form used (it's a single inline card, not a full form section). */
export default function WorkRequiredField({
  options, value, onToggle, notes, onNotesChange, error, notesError, testIdPrefix = "work-type", compact = false,
}) {
  return (
    <div>
      <div className={cn("font-display font-bold mb-2", compact && "text-sm")}>Work Required *</div>
      <div className="grid sm:grid-cols-2 gap-2">
        {options.map((option) => (
          <label key={option} className="flex items-center gap-2 text-sm font-medium">
            <Checkbox
              checked={value.includes(option)}
              onCheckedChange={() => onToggle(option)}
              data-testid={`${testIdPrefix}-${option.toLowerCase().replace(/\s+/g, "-")}`}
            />
            {option}
          </label>
        ))}
      </div>
      {error && <p className="text-xs text-destructive mt-1">{error}</p>}
      {value.includes("Other") && (
        <div className="mt-2">
          <Label>Describe the other work required</Label>
          <Input value={notes} onChange={(e) => onNotesChange(e.target.value)} />
          {notesError && <p className="text-xs text-destructive mt-1">{notesError}</p>}
        </div>
      )}
    </div>
  );
}
