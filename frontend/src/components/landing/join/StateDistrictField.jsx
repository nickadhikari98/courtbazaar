import React, { useEffect, useMemo, useState } from "react";
import { ChevronsUpDown, X } from "lucide-react";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import {
  Command, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem,
} from "@/components/ui/command";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { getStates, getDistricts, DEFAULT_STATE } from "@/lib/indiaLocations";
import { cn } from "@/lib/utils";

function FieldLabel({ label, required }) {
  if (!label) return null;
  return (
    <label className="text-sm font-semibold text-foreground block mb-1.5">
      {label}
      {required && <span className="text-red-500 ml-0.5">*</span>}
    </label>
  );
}

/* Searchable multi-select: a Popover trigger opens a checkbox list (cmdk),
   selections render as removable chips beneath it. Used for State/UT and
   District fields wherever a form allows more than one selection. */
function MultiSelectCombobox({
  options, selected, onChange, placeholder, disabled, emptyText = "No results found.",
}) {
  const [open, setOpen] = useState(false);

  const toggle = (opt) => {
    onChange(selected.includes(opt) ? selected.filter((v) => v !== opt) : [...selected, opt]);
  };
  const remove = (opt) => onChange(selected.filter((v) => v !== opt));

  const summary = selected.length === 0
    ? placeholder
    : selected.length === 1
      ? selected[0]
      : `${selected.length} selected`;

  return (
    <div>
      <Popover open={open} onOpenChange={(next) => !disabled && setOpen(next)}>
        <PopoverTrigger asChild>
          <button
            type="button"
            disabled={disabled}
            className={cn(
              "flex w-full items-center justify-between rounded-md border border-input bg-white h-10 px-3 text-sm shadow-sm transition-colors",
              "disabled:cursor-not-allowed disabled:opacity-50",
              selected.length === 0 && "text-muted-foreground"
            )}
          >
            <span className="truncate">{summary}</span>
            <ChevronsUpDown className="w-4 h-4 opacity-50 flex-shrink-0 ml-2" />
          </button>
        </PopoverTrigger>
        <PopoverContent
          align="start"
          className="p-0 w-[var(--radix-popover-trigger-width)]"
        >
          <Command>
            <CommandInput placeholder="Search..." />
            <CommandList>
              <CommandEmpty>{emptyText}</CommandEmpty>
              <CommandGroup>
                {options.map((opt) => {
                  const isSelected = selected.includes(opt);
                  return (
                    <CommandItem
                      key={opt}
                      value={opt}
                      onSelect={() => toggle(opt)}
                      className="gap-2 cursor-pointer"
                    >
                      <Checkbox checked={isSelected} className="pointer-events-none" />
                      <span className="flex-1">{opt}</span>
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {selected.map((opt) => (
            <Badge key={opt} variant="secondary" className="pl-2.5 pr-1 py-0.5 gap-1 font-medium">
              {opt}
              <button
                type="button"
                onClick={() => remove(opt)}
                className="rounded-full hover:bg-black/10 p-0.5"
                aria-label={`Remove ${opt}`}
              >
                <X className="w-3 h-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

/* Shared State/District field, used across every "Join as..." form.
   `type` is "state" or "district" — a district field reads `stateValue`
   (the sibling State field's current value within the same section) to
   compute its live options and prunes selections that no longer belong to it
   when that state changes.

   `multiple` switches both fields from a single Select dropdown to a
   searchable multi-select checkbox list (chips). In multi mode `value` and
   `stateValue` are arrays instead of strings. */
export default function StateDistrictField({
  type, label, required, value, onChange, stateValue, multiple,
}) {
  const states = useMemo(() => getStates(), []);

  const selectedStates = useMemo(() => {
    if (type !== "district") return [];
    if (multiple) return Array.isArray(stateValue) ? stateValue : [];
    return stateValue ? [stateValue] : [];
  }, [type, multiple, stateValue]);

  const districts = useMemo(() => {
    if (type !== "district") return [];
    if (multiple) {
      const set = new Set();
      selectedStates.forEach((s) => getDistricts(s).forEach((d) => set.add(d)));
      return Array.from(set);
    }
    return getDistricts(stateValue);
  }, [type, multiple, stateValue, selectedStates]);

  const districtsKey = districts.join("|");

  // Single-select: clear the chosen district if it no longer belongs to the state.
  useEffect(() => {
    if (type !== "district" || multiple) return;
    if (value && !districts.includes(value)) onChange("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type, multiple, stateValue]);

  // Multi-select: prune any selected districts that no longer belong to any selected state.
  useEffect(() => {
    if (type !== "district" || !multiple) return;
    const current = Array.isArray(value) ? value : [];
    const pruned = current.filter((d) => districts.includes(d));
    if (pruned.length !== current.length) onChange(pruned);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type, multiple, districtsKey]);

  if (type === "state") {
    if (multiple) {
      return (
        <div>
          <FieldLabel label={label} required={required} />
          <MultiSelectCombobox
            options={states}
            selected={Array.isArray(value) ? value : []}
            onChange={onChange}
            placeholder="Select States / UTs"
          />
        </div>
      );
    }
    return (
      <div>
        <FieldLabel label={label} required={required} />
        <Select value={value || DEFAULT_STATE} onValueChange={onChange}>
          <SelectTrigger>
            <SelectValue placeholder="Select a state" />
          </SelectTrigger>
          <SelectContent>
            {states.map((s) => (
              <SelectItem key={s} value={s}>{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  }

  if (multiple) {
    return (
      <div>
        <FieldLabel label={label} required={required} />
        <MultiSelectCombobox
          options={districts}
          selected={Array.isArray(value) ? value : []}
          onChange={onChange}
          placeholder={selectedStates.length ? "Select Districts" : "Select a state first"}
          disabled={selectedStates.length === 0}
        />
      </div>
    );
  }

  return (
    <div>
      <FieldLabel label={label} required={required} />
      <Select value={value || ""} onValueChange={onChange} disabled={!stateValue}>
        <SelectTrigger>
          <SelectValue placeholder={stateValue ? "Select a district" : "Select a state first"} />
        </SelectTrigger>
        <SelectContent>
          {districts.map((d) => (
            <SelectItem key={d} value={d}>{d}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
