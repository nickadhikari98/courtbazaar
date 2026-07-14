import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { RefreshCw } from "lucide-react";
import { SingleSelectCombobox, MultiSelectCombobox } from "./Combobox";
import { getStates, getCourtsByState } from "@/lib/referenceDataApi";

function FieldLabel({ label, required }) {
  if (!label) return null;
  return (
    <label className="text-sm font-semibold text-foreground block mb-1.5">
      {label}
      {required && <span className="text-red-500 ml-0.5">*</span>}
    </label>
  );
}

// Defensive: never trust a response shape blindly — a failed/odd request
// (proxy error page, empty body, etc.) shouldn't crash the field.
function asArray(data) {
  return Array.isArray(data) ? data : [];
}

/* State-then-courts cascading multi-select, backed by live backend data
   (GET /states, GET /courts?state_id=). The chosen State is local UI state
   only, used to filter which courts are offered — the field's persisted
   `value` is just the array of selected court name strings, consistent with
   every other multi-select field in this form system. */
export default function CourtOfPracticeField({ label, required, value, onChange }) {
  // Defensive against stale drafts saved before this field stored an array
  // (e.g. an in-progress localStorage draft from an older build) — never
  // trust the incoming value's shape blindly.
  const safeValue = Array.isArray(value) ? value : [];

  const [states, setStates] = useState([]);
  const [loadingStates, setLoadingStates] = useState(true);
  const [statesError, setStatesError] = useState(false);

  const [stateId, setStateId] = useState("");
  const [courts, setCourts] = useState([]);
  const [loadingCourts, setLoadingCourts] = useState(false);
  const [courtsError, setCourtsError] = useState(false);

  const loadStates = useCallback(() => {
    setLoadingStates(true);
    setStatesError(false);
    getStates()
      .then((data) => setStates(asArray(data)))
      .catch(() => {
        setStatesError(true);
        toast.error("Couldn't load the list of states. Please try again.");
      })
      .finally(() => setLoadingStates(false));
  }, []);

  useEffect(() => { loadStates(); }, [loadStates]);

  const loadCourts = useCallback((id) => {
    if (!id) { setCourts([]); return; }
    setLoadingCourts(true);
    setCourtsError(false);
    getCourtsByState(id)
      .then((data) => setCourts(asArray(data)))
      .catch(() => {
        setCourtsError(true);
        setCourts([]);
        toast.error("Couldn't load courts for that state. Please try again.");
      })
      .finally(() => setLoadingCourts(false));
  }, []);

  useEffect(() => { loadCourts(stateId); }, [stateId, loadCourts]);

  // Prune selected courts that no longer belong to the currently loaded list
  // once courts have actually loaded for a chosen state (avoids wiping the
  // selection while a fetch is still in flight).
  useEffect(() => {
    if (!stateId || loadingCourts) return;
    const names = new Set(courts.map((c) => c.name));
    const pruned = safeValue.filter((v) => names.has(v));
    if (pruned.length !== safeValue.length) onChange?.(pruned);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courts, loadingCourts]);

  const selectedStateName = states.find((s) => s.state_id === stateId)?.name || "";
  const noCourtsForState = stateId && !loadingCourts && !courtsError && courts.length === 0;

  let courtsPlaceholder = "Select courts";
  if (!stateId) courtsPlaceholder = "Select a state first";
  else if (loadingCourts) courtsPlaceholder = "Loading courts…";
  else if (courtsError) courtsPlaceholder = "Couldn't load courts";
  else if (noCourtsForState) courtsPlaceholder = "No courts available for this state";

  return (
    <div className="space-y-3">
      <FieldLabel label={label} required={required} />
      <div>
        <label className="text-xs font-medium text-muted-foreground block mb-1.5">State</label>
        {statesError ? (
          <button
            type="button"
            onClick={loadStates}
            className="flex items-center gap-1.5 text-sm text-red-600 hover:text-red-700 font-medium"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Couldn't load states — tap to retry
          </button>
        ) : (
          <SingleSelectCombobox
            options={states.map((s) => s.name)}
            value={selectedStateName}
            onChange={(name) => setStateId(states.find((s) => s.name === name)?.state_id || "")}
            placeholder={loadingStates ? "Loading states…" : "Select a state"}
            disabled={loadingStates}
          />
        )}
      </div>
      <div>
        <label className="text-xs font-medium text-muted-foreground block mb-1.5">Courts</label>
        <MultiSelectCombobox
          options={courts.map((c) => c.name)}
          selected={safeValue}
          onChange={onChange}
          placeholder={courtsPlaceholder}
          disabled={!stateId || loadingCourts || courtsError || noCourtsForState}
          emptyText="No courts match your search."
        />
        {courtsError && (
          <button
            type="button"
            onClick={() => loadCourts(stateId)}
            className="flex items-center gap-1.5 text-sm text-red-600 hover:text-red-700 font-medium mt-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Retry loading courts
          </button>
        )}
      </div>
    </div>
  );
}
