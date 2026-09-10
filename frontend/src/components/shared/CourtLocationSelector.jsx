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
   seeded district court already carries a `district` field — see
   backend/court_seed.py) rather than a separate district API.

   High Courts are a second, parallel path rather than a 4th cascade level:
   a state's High Court (and its benches) isn't seated in any district at
   all — court_seed_expanded.py's build_court_data() only ever stamps
   `district` onto type:"district" court docs — so it can't be reached by
   narrowing District→Court like every other court here. `courtType` picks
   which path is active; switching it clears whatever was already selected
   under the other one rather than merging them (a request is either
   addressed to a district court or a High Court, never both). */
const CLEAR_DISTRICT = "__any_district__";

export default function CourtLocationSelector({ value, onChange }) {
  const { state_id, district, court_id } = value || {};
  const [states, setStates] = useState([]);
  const [courts, setCourts] = useState([]);
  const [courtType, setCourtType] = useState("district"); // "district" | "high_court" | "arbitration"

  useEffect(() => { getStates().then(setStates).catch(() => setStates([])); }, []);

  useEffect(() => {
    if (!state_id) { setCourts([]); return; }
    getCourtsByState(state_id).then(setCourts).catch(() => setCourts([]));
  }, [state_id]);

  const districtCourts = useMemo(() => courts.filter((c) => c.type === "district"), [courts]);
  const districts = useMemo(
    () => Array.from(new Set(districtCourts.map((c) => c.district).filter(Boolean))).sort(),
    [districtCourts],
  );
  const courtsInDistrict = useMemo(
    () => (district ? districtCourts.filter((c) => c.district === district) : districtCourts),
    [districtCourts, district],
  );
  const highCourts = useMemo(() => courts.filter((c) => c.type === "high_court"), [courts]);
  const arbitrationCentres = useMemo(() => courts.filter((c) => c.type === "arbitration"), [courts]);

  const selectState = (v) => {
    onChange({ state_id: v, state_name: states.find((s) => s.state_id === v)?.name, district: "", court_id: "", court_name: "", court_type: courtType });
  };

  const switchCourtType = (type) => {
    if (type === courtType) return;
    setCourtType(type);
    onChange({ state_id, state_name: value?.state_name, district: "", court_id: "", court_name: "", court_type: type });
  };

  return (
    <div className="space-y-3">
      <div className="inline-flex rounded-lg border border-border p-0.5 bg-secondary/40">
        {[["district", "District Court"], ["high_court", "High Court"], ["arbitration", "Arbitration Centre"]].map(([key, label]) => (
          <button
            key={key} type="button" onClick={() => switchCourtType(key)}
            className={`px-3 py-1.5 text-xs font-bold rounded-md transition-colors ${
              courtType === key ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
            }`}
            data-testid={`location-court-type-${key}`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Literal class strings, not a template-interpolated column count —
          Tailwind's build-time scanner only picks up classes it can see as
          whole strings in source, so `sm:grid-cols-${n}` would silently
          never generate the CSS for either count. */}
      <div className={courtType === "district" ? "grid sm:grid-cols-3 gap-3" : "grid sm:grid-cols-2 gap-3"}>
        <div>
          <Label>State *</Label>
          <Select value={state_id || undefined} onValueChange={selectState}>
            <SelectTrigger data-testid="location-state"><SelectValue placeholder="Select state" /></SelectTrigger>
            <SelectContent>
              {states.map((s) => <SelectItem key={s.state_id} value={s.state_id}>{s.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        {courtType === "district" ? (
          <>
            <div>
              <Label>District *</Label>
              <Select
                // Always a defined value (never `undefined`) — Radix's Select
                // falls out of controlled mode the instant its value prop
                // goes undefined, and then keeps showing whatever it last
                // displayed instead of clearing: picking "Any district" would
                // update `district` to "" but the trigger stayed stuck on the
                // old district. Sentinel value + always-rendered item keeps it
                // controlled through every state, clear included.
                value={district || CLEAR_DISTRICT}
                onValueChange={(v) => onChange({ state_id, state_name: value?.state_name, district: v === CLEAR_DISTRICT ? "" : v, court_id: "", court_name: "", court_type: courtType })}
                disabled={!state_id}
              >
                <SelectTrigger data-testid="location-district"><SelectValue placeholder={state_id ? "Select district" : "Select a state first"} /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={CLEAR_DISTRICT}>Any district</SelectItem>
                  {districts.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Court *</Label>
              <Select
                value={court_id || undefined}
                onValueChange={(v) => onChange({ state_id, state_name: value?.state_name, district, court_id: v, court_name: courts.find((c) => c.court_id === v)?.name, court_type: courtType })}
                disabled={!state_id}
              >
                <SelectTrigger data-testid="location-court"><SelectValue placeholder={state_id ? "Select court" : "Select a state first"} /></SelectTrigger>
                <SelectContent>
                  {courtsInDistrict.map((c) => <SelectItem key={c.court_id} value={c.court_id}>{c.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </>
        ) : courtType === "high_court" ? (
          <div>
            <Label>High Court *</Label>
            <Select
              value={court_id || undefined}
              // No `district` on a High Court selection — leaving it blank
              // (rather than e.g. the bench's city) is deliberate: the
              // recommendations/matching queries intersect a district-based
              // court set with court_id (see counsel_matching.list_and_recommend),
              // and no court doc actually carries this city as its
              // `district` value, so setting one here would silently zero
              // out that intersection instead of just being unused.
              onValueChange={(v) => onChange({
                state_id, state_name: value?.state_name, district: "",
                court_id: v, court_name: highCourts.find((c) => c.court_id === v)?.name,
                court_type: "high_court",
              })}
              disabled={!state_id}
            >
              <SelectTrigger data-testid="location-high-court">
                <SelectValue placeholder={state_id ? (highCourts.length ? "Select High Court" : "No High Court seated in this state") : "Select a state first"} />
              </SelectTrigger>
              <SelectContent>
                {highCourts.map((c) => <SelectItem key={c.court_id} value={c.court_id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        ) : (
          <div>
            <Label>Arbitration Centre *</Label>
            <Select
              value={court_id || undefined}
              // Same reasoning as the High Court branch above: no `district`
              // on an arbitration-centre selection.
              onValueChange={(v) => onChange({
                state_id, state_name: value?.state_name, district: "",
                court_id: v, court_name: arbitrationCentres.find((c) => c.court_id === v)?.name,
                court_type: "arbitration",
              })}
              disabled={!state_id}
            >
              <SelectTrigger data-testid="location-arbitration">
                <SelectValue placeholder={state_id ? (arbitrationCentres.length ? "Select Arbitration Centre" : "No arbitration centre seated in this state") : "Select a state first"} />
              </SelectTrigger>
              <SelectContent>
                {arbitrationCentres.map((c) => <SelectItem key={c.court_id} value={c.court_id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>
    </div>
  );
}
