import React, { useState } from "react";
import { Check, ChevronsUpDown, X } from "lucide-react";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import {
  Command, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem,
} from "@/components/ui/command";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/* Searchable single-select: a Popover trigger opens a filterable list (cmdk),
   closes on pick. Optional `other` support mirrors RadioField/CheckboxGroupField's
   convention — `options` includes "Other" as a literal entry, and selecting it
   reveals a "Please specify" input alongside. */
export function SingleSelectCombobox({
  options, value, onChange, placeholder = "Select an option", disabled, emptyText = "No results found.",
  other, otherValue, onOtherChange,
}) {
  const [open, setOpen] = useState(false);
  const isOtherSelected = other && value === "Other";

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
              !value && "text-muted-foreground"
            )}
          >
            <span className="truncate">{value || placeholder}</span>
            <ChevronsUpDown className="w-4 h-4 opacity-50 flex-shrink-0 ml-2" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="start" className="p-0 w-[var(--radix-popover-trigger-width)]">
          <Command>
            <CommandInput placeholder="Search..." />
            <CommandList>
              <CommandEmpty>{emptyText}</CommandEmpty>
              <CommandGroup>
                {options.map((opt) => (
                  <CommandItem
                    key={opt}
                    value={opt}
                    onSelect={() => { onChange?.(opt); setOpen(false); }}
                    className="gap-2 cursor-pointer"
                  >
                    <Check className={cn("w-4 h-4", value === opt ? "opacity-100" : "opacity-0")} />
                    <span className="flex-1">{opt}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {other && (
        <Input
          placeholder="Please specify"
          className="h-9 text-sm mt-2"
          value={otherValue ?? ""}
          onChange={(e) => onOtherChange?.(e.target.value)}
          disabled={!isOtherSelected}
        />
      )}
    </div>
  );
}

/* Searchable multi-select: same Popover+cmdk scaffolding, checkbox list,
   selections render as removable chips beneath it. */
export function MultiSelectCombobox({
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
