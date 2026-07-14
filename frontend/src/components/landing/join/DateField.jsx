import React, { useState } from "react";
import { format, parseISO, isValid } from "date-fns";
import { CalendarIcon } from "lucide-react";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { cn, resolveDateBound } from "@/lib/utils";

function FieldLabel({ label, required }) {
  if (!label) return null;
  return (
    <label className="text-sm font-semibold text-foreground block mb-1.5">
      {label}
      {required && <span className="text-red-500 ml-0.5">*</span>}
    </label>
  );
}

/* Calendar-popover date field, shared by every "Join as..." form. Displays
   DD/MM/YYYY but stores/emits the value as an ISO "yyyy-MM-dd" string, same
   as the native `type="date"` TextField it replaces — so RoleForm's
   `max: "today"` validation and draft persistence need no changes. */
export default function DateField({ label, required, value, onChange, min, max }) {
  const [open, setOpen] = useState(false);

  const parsed = value ? parseISO(value) : undefined;
  const selected = parsed && isValid(parsed) ? parsed : undefined;

  const resolvedMin = resolveDateBound(min);
  const resolvedMax = resolveDateBound(max);
  const disabledMatchers = [];
  if (resolvedMin) disabledMatchers.push({ before: parseISO(resolvedMin) });
  if (resolvedMax) disabledMatchers.push({ after: parseISO(resolvedMax) });

  return (
    <div>
      <FieldLabel label={label} required={required} />
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className={cn(
              "flex w-full items-center justify-between rounded-md border border-input bg-white h-10 px-3 text-sm shadow-sm transition-colors",
              !selected && "text-muted-foreground"
            )}
          >
            <span>{selected ? format(selected, "dd/MM/yyyy") : "DD/MM/YYYY"}</span>
            <CalendarIcon className="w-4 h-4 opacity-50 flex-shrink-0 ml-2" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-auto p-0">
          <Calendar
            mode="single"
            selected={selected}
            defaultMonth={selected}
            disabled={disabledMatchers.length ? disabledMatchers : undefined}
            onSelect={(date) => {
              if (!date) return;
              onChange?.(format(date, "yyyy-MM-dd"));
              setOpen(false);
            }}
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}
