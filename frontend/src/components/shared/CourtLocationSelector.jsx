import React, { useEffect, useMemo, useState } from "react";
import { Label } from "@/components/ui/label";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { getStates, getCourtsByState } from "@/lib/referenceDataApi";

/* Reusable State → District → Court cascade for any legal-service request
   form. `court_id` is the one canonical, long-term location identifier
   (consumed directly by hearings.py etc.) — State/District exist here only
   to narrow the Court dropdown during selection; a form storing them
   alongside court_id (e.g. request_details.common) should treat them as
   display/audit convenience, not as independent identifiers to keep in
   sync. District values come from the selected state's own courts (every
   seeded court already carries a `district` field — see
   backend/court_seed.py) rather than a separate district API. */
export default function CourtLocationSelector({ value, onChange }) {
  const { state_id, district, court_id } = value || {};
  const [states, setStates] = useState([]);
  const [courts, setCourts] = useState([]);

  useEffect(() => { getStates().then(setStates).catch(() => setStates([])); }, []);

  useEffect(() => {
    if (!state_id) { setCourts([]); return; }
    getCourtsByState(state_id).then(setCourts).catch(() => setCourts([]));
  }, [state_id]);

  const districts = useMemo(
    () => Array.from(new Set(courts.map((c) => c.district).filter(Boolean))).sort(),
    [courts],
  );
  const courtsInDistrict = useMemo(
    () => (district ? courts.filter((c) => c.district === district) : courts),
    [courts, district],
  );

  return (
    <div className="grid sm:grid-cols-3 gap-3">
      <div>
        <Label>State *</Label>
        <Select
          value={state_id || undefined}
          onValueChange={(v) => onChange({ state_id: v, state_name: states.find((s) => s.state_id === v)?.name, district: "", court_id: "", court_name: "" })}
        >
          <SelectTrigger data-testid="location-state"><SelectValue placeholder="Select state" /></SelectTrigger>
          <SelectContent>
            {states.map((s) => <SelectItem key={s.state_id} value={s.state_id}>{s.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label>District *</Label>
        <Select
          value={district || undefined}
          onValueChange={(v) => onChange({ state_id, state_name: value?.state_name, district: v, court_id: "", court_name: "" })}
          disabled={!state_id}
        >
          <SelectTrigger data-testid="location-district"><SelectValue placeholder={state_id ? "Select district" : "Select a state first"} /></SelectTrigger>
          <SelectContent>
            {districts.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label>Court *</Label>
        <Select
          value={court_id || undefined}
          onValueChange={(v) => onChange({ state_id, state_name: value?.state_name, district, court_id: v, court_name: courts.find((c) => c.court_id === v)?.name })}
          disabled={!state_id}
        >
          <SelectTrigger data-testid="location-court"><SelectValue placeholder={state_id ? "Select court" : "Select a state first"} /></SelectTrigger>
          <SelectContent>
            {courtsInDistrict.map((c) => <SelectItem key={c.court_id} value={c.court_id}>{c.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
