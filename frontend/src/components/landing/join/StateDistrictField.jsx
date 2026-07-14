import React, { useEffect, useMemo } from "react";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { getStates, getDistricts, DEFAULT_STATE } from "@/lib/indiaLocations";
import { MultiSelectCombobox } from "./Combobox";

function FieldLabel({ label, required }) {
  if (!label) return null;
  return (
    <label className="text-sm font-semibold text-foreground block mb-1.5">
      {label}
      {required && <span className="text-red-500 ml-0.5">*</span>}
    </label>
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
