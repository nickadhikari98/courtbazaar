import React, { useEffect, useMemo, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Star, MapPin, Languages as LanguagesIcon, Gavel, RefreshCw, Users, Sparkles, ChevronDown, SlidersHorizontal, X } from "lucide-react";
import { formatINR } from "@/lib/api";
import { getStates, getCourtsByState } from "@/lib/referenceDataApi";
import { useAdvocateRecommendations } from "@/lib/advocateRecommendationsApi";

const initialsOf = (name) => (name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();

/* Step 1/2 of the recommendation flow: State -> City (District), both
   mandatory. Deliberately its own State/City-only cascade rather than
   reusing CourtLocationSelector wholesale — that component bundles Court
   into the same mandatory step, but here Court is an optional Step 3
   filter (see FiltersBar) that only appears once a location is chosen.
   Reuses the same reference-data API calls CourtLocationSelector uses
   (getStates/getCourtsByState), and "City" is the existing `district`
   field on a court — every seeded court already carries one (see
   backend/court_seed.py) — not a new schema field. */
function LocationStep({ location, states, districts, onChange }) {
  return (
    <Card className="dashboard-card border-none mb-4" data-testid="advocate-location-step">
      <CardContent className="p-4">
        <div className="cb-overline mb-2">Location</div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="text-2xs">State *</Label>
            <Select
              value={location.state_id || undefined}
              onValueChange={(v) => {
                const matchedState = states.find((s) => s.state_id === v);
                onChange({ state_id: v, state_name: matchedState?.name, district: "" });
              }}
            >
              <SelectTrigger className="mt-1" data-testid="advocate-location-state"><SelectValue placeholder="Select state" /></SelectTrigger>
              <SelectContent>
                {states.map((s) => <SelectItem key={s.state_id} value={s.state_id}>{s.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-2xs">City *</Label>
            <Select
              value={location.district || undefined}
              onValueChange={(v) => {
                onChange({ ...location, district: v });
              }}
              disabled={!location.state_id}
            >
              <SelectTrigger className="mt-1" data-testid="advocate-location-district"><SelectValue placeholder={location.state_id ? "Select city" : "Select a state first"} /></SelectTrigger>
              <SelectContent>
                {districts.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/* Step 3 — optional, only shown once Step 1/2's location is set. Every
   field here is an existing proxy_counsel_profiles field the
   recommendation endpoint already queries on (see
   counsel_matching.list_and_recommend) — no field is new. Court is scoped
   to `courtsInDistrict` (the already-selected city's own courts), reusing
   the same court list LocationStep fetched rather than a second API call.
   Purely controlled: this component holds no filter state of its own. */
function FiltersBar({ filters, onFiltersChange, courtsInDistrict }) {
  const set = (patch) => onFiltersChange({ ...filters, ...patch });
  const hasActiveFilters = Object.values(filters || {}).some((v) => v !== undefined && v !== "" && v !== false);

  return (
    <Card className="dashboard-card border-none mb-4" data-testid="advocate-filters">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-1.5 cb-overline"><SlidersHorizontal className="w-3.5 h-3.5" /> Filters (optional)</div>
          {hasActiveFilters && (
            <button type="button" onClick={() => onFiltersChange({})} className="text-2xs font-semibold text-muted-foreground hover:text-foreground flex items-center gap-1">
              <X className="w-3 h-3" /> Clear
            </button>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="text-2xs">Court</Label>
            <Select value={filters.court_id || undefined} onValueChange={(v) => set({ court_id: v })}>
              <SelectTrigger className="h-8 text-sm mt-1" data-testid="filter-court"><SelectValue placeholder="Any court" /></SelectTrigger>
              <SelectContent>
                {courtsInDistrict.map((c) => <SelectItem key={c.court_id} value={c.court_id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-2xs">Specialization</Label>
            <Input
              value={filters.specialization || ""} placeholder="e.g. Criminal" className="h-8 text-sm mt-1"
              onChange={(e) => set({ specialization: e.target.value || undefined })}
              data-testid="filter-specialization"
            />
          </div>
          <div>
            <Label className="text-2xs">Min. Experience (yrs)</Label>
            <Input
              type="number" min="0" value={filters.min_experience_years ?? ""} className="h-8 text-sm mt-1"
              onChange={(e) => set({ min_experience_years: e.target.value ? Number(e.target.value) : undefined })}
              data-testid="filter-min-experience"
            />
          </div>
          <div>
            <Label className="text-2xs">Min. Rating</Label>
            <Input
              type="number" min="0" max="5" step="0.1" value={filters.min_rating ?? ""} className="h-8 text-sm mt-1"
              onChange={(e) => set({ min_rating: e.target.value ? Number(e.target.value) : undefined })}
              data-testid="filter-min-rating"
            />
          </div>
          <div className="flex gap-2 col-span-2">
            <div className="flex-1">
              <Label className="text-2xs">Fee Min (₹)</Label>
              <Input
                type="number" min="0" value={filters.fee_min ?? ""} className="h-8 text-sm mt-1"
                onChange={(e) => set({ fee_min: e.target.value ? Number(e.target.value) : undefined })}
                data-testid="filter-fee-min"
              />
            </div>
            <div className="flex-1">
              <Label className="text-2xs">Fee Max (₹)</Label>
              <Input
                type="number" min="0" value={filters.fee_max ?? ""} className="h-8 text-sm mt-1"
                onChange={(e) => set({ fee_max: e.target.value ? Number(e.target.value) : undefined })}
                data-testid="filter-fee-max"
              />
            </div>
          </div>
        </div>
        <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer select-none mt-3">
          <Checkbox
            checked={!!filters.available_only}
            onCheckedChange={(v) => set({ available_only: v || undefined })}
            data-testid="filter-available-only"
          />
          Available now only
        </label>
      </CardContent>
    </Card>
  );
}

/* Proxy Counsel Page — AI Recommendations + Filters, as its own
   independent module (founder follow-up request): State -> City ->
   fetch eligible counsels -> optional filters -> AI ranking (reusing
   counsel_matching.score_candidates via GET /recommendations/advocates,
   see lib/advocateRecommendationsApi.js) -> ranked results. Deliberately
   does NOT take a hearing-request `context`/location prop from its parent
   page — it owns its own location + filter state and calls
   useAdvocateRecommendations itself, so it works the same way regardless
   of what (if anything) a Hire Proxy Counsel request form on the same page
   is doing. `selectedAdvocateId`/`onSelect`/`onClear` are the only link
   back to the parent — purely "the user picked someone", not a data
   dependency in the other direction. */
export default function AvailableAdvocatesPanel({ selectedAdvocateId, onSelect, onClear }) {
  const [location, setLocation] = useState({ state_id: "", state_name: "", district: "" });
  const [filters, setFilters] = useState({});
  const [states, setStates] = useState([]);
  const [courts, setCourts] = useState([]);
  const [profileAdvocate, setProfileAdvocate] = useState(null);
  // Mobile-only collapse (§ Mobile Experience) — desktop (lg:) always shows
  // the full panel via the `lg:block` override below, this state never
  // applies there.
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    getStates()
      .then((s) => setStates(s))
      .catch(() => setStates([]));
  }, []);
  useEffect(() => {
    if (!location.state_id) { setCourts([]); return; }
    getCourtsByState(location.state_id)
      .then((c) => setCourts(c))
      .catch(() => setCourts([]));
  }, [location.state_id]);

  const districts = useMemo(
    () => Array.from(new Set(courts.map((c) => c.district).filter(Boolean))).sort(),
    [courts],
  );
  const courtsInDistrict = useMemo(
    () => (location.district ? courts.filter((c) => c.district === location.district) : []),
    [courts, location.district],
  );

  const changeLocation = (next) => {
    setLocation(next);
    setFilters((f) => ({ ...f, court_id: undefined })); // a court from the previous city no longer applies
  };

  const hasLocation = !!(location.state_id && location.district);
  const recommendations = useAdvocateRecommendations(
    hasLocation ? { state_id: location.state_id, district: location.district, ...filters } : {},
  );
  const { status, advocates = [], metadata, refetch } = recommendations;

  const title = "Proxy Counsel Recommendations";
  const mobileHeaderLabel = status === "ready" ? `${title} (${advocates.length})` : title;

  return (
    <div>
      <div className="hidden lg:block">
        <div className="cb-overline text-accent">Advocates</div>
        <h2 className="font-display font-bold text-xl tracking-tight mt-1 mb-3">{title}</h2>
      </div>

      {/* Mobile-only collapsible header — desktop behavior is unchanged
          (the content below is always visible at lg: and up). */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="lg:hidden w-full flex items-center justify-between bento-card p-3.5 mb-3"
        data-testid="advocates-panel-toggle"
        aria-expanded={expanded}
      >
        <span className="font-display font-bold text-sm">{mobileHeaderLabel}</span>
        <ChevronDown className={`w-4 h-4 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`} />
      </button>

      <div className={`${expanded ? "block" : "hidden"} lg:block`}>

      <LocationStep location={location} states={states} districts={districts} onChange={changeLocation} />

      {!hasLocation && (
        <Card className="border-dashed border-2" data-testid="advocates-idle">
          <CardContent className="p-6">
            <MapPin className="w-8 h-8 mx-auto text-muted-foreground mb-2" strokeWidth={1.5} />
            <p className="text-sm font-semibold text-center">Select a state and city to see recommended proxy counsels.</p>
          </CardContent>
        </Card>
      )}

      {hasLocation && <FiltersBar filters={filters} onFiltersChange={setFilters} courtsInDistrict={courtsInDistrict} />}

      {hasLocation && metadata?.total_candidates != null && (
        <p className="text-2xs text-muted-foreground mb-3">
          Showing {metadata.returned ?? advocates.length} of {metadata.total_candidates} candidates
          {metadata.generated_at ? ` · updated ${new Date(metadata.generated_at).toLocaleTimeString("en-IN")}` : ""}
        </p>
      )}

      {hasLocation && status === "loading" && (
        <div className="space-y-3">{[1, 2, 3].map((i) => <div key={i} className="h-40 shimmer rounded-xl"></div>)}</div>
      )}

      {hasLocation && status === "error" && (
        <Card className="border-dashed border-2" data-testid="advocates-error">
          <CardContent className="p-8 text-center">
            <p className="text-sm text-muted-foreground mb-3">Couldn't load advocates right now.</p>
            <Button type="button" variant="outline" size="sm" onClick={refetch}>
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Retry
            </Button>
          </CardContent>
        </Card>
      )}

      {hasLocation && status === "empty" && (
        <Card className="border-dashed border-2" data-testid="advocates-empty">
          <CardContent className="p-8 text-center">
            <Users className="w-8 h-8 mx-auto text-muted-foreground mb-2" strokeWidth={1.5} />
            <p className="text-sm text-muted-foreground">No proxy counsels match this location and filters yet.</p>
          </CardContent>
        </Card>
      )}

      {hasLocation && status === "ready" && (
        <div className="space-y-3">
          {advocates.map((a) => {
            const isSelected = selectedAdvocateId === a.advocate_id;
            const hasAiInfo = a.ai_match_score != null || a.ai_match_reasons || a.estimated_response_time;
            return (
              <Card key={a.advocate_id} className={`bento-card ${isSelected ? "border-accent ring-1 ring-accent" : "border-none"}`} data-testid={`advocate-card-${a.advocate_id}`}>
                <CardContent className="p-4">
                  <div className="flex items-start gap-3">
                    <Avatar className="w-11 h-11">
                      <AvatarFallback className="bg-primary text-white text-xs font-bold">{initialsOf(a.name)}</AvatarFallback>
                    </Avatar>
                    <div className="min-w-0 flex-1">
                      <div className="font-display font-bold text-sm leading-tight">{a.name}</div>
                      <div className="flex items-center gap-1 text-xs text-muted-foreground mt-0.5">
                        <Star className="w-3 h-3 fill-amber-400 text-amber-400" /> {a.rating}
                        <span className="mx-1">·</span>
                        <Gavel className="w-3 h-3" /> {a.hearings_completed} hearings
                      </div>
                    </div>
                    <Badge className={`${a.availability?.available_now ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"} border-0 text-2xs font-bold flex-shrink-0`}>
                      {a.availability?.note}
                    </Badge>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-1">
                    {a.primary_courts?.map((c) => <Badge key={c} variant="outline" className="text-2xs font-semibold"><MapPin className="w-2.5 h-2.5 mr-1" />{c}</Badge>)}
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {a.practice_areas?.map((p) => <Badge key={p} variant="outline" className="text-2xs font-semibold text-accent border-accent/30">{p}</Badge>)}
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1 text-2xs text-muted-foreground items-center">
                    <LanguagesIcon className="w-3 h-3" /> {a.languages?.join(", ")}
                  </div>

                  {a.proposed_fee != null && (
                    <div className="mt-2 text-sm font-bold">{formatINR(a.proposed_fee)} <span className="text-xs font-medium text-muted-foreground">proposed fee</span></div>
                  )}

                  {hasAiInfo && (
                    <div className="mt-2 pt-2 border-t border-dashed space-y-1">
                      {a.ai_match_score != null && (
                        <Badge className="bg-violet-100 text-violet-700 border-0 text-2xs font-bold gap-1"><Sparkles className="w-2.5 h-2.5" /> AI Match {a.ai_match_score}%</Badge>
                      )}
                      {a.ai_match_reasons && <p className="text-2xs text-muted-foreground">{a.ai_match_reasons}</p>}
                      {a.estimated_response_time && <p className="text-2xs text-muted-foreground">Est. response: {a.estimated_response_time}</p>}
                    </div>
                  )}

                  <div className="mt-3 flex gap-2">
                    <Button type="button" size="sm" variant="outline" className="flex-1" onClick={() => setProfileAdvocate(a)} data-testid={`view-profile-${a.advocate_id}`}>
                      View Profile
                    </Button>
                    {isSelected ? (
                      <Button type="button" size="sm" variant="outline" className="flex-1 text-accent border-accent/30" onClick={onClear} data-testid={`clear-advocate-${a.advocate_id}`}>
                        Selected — Clear
                      </Button>
                    ) : (
                      <Button
                        type="button" size="sm" className="flex-1 bg-accent hover:bg-accent/90 font-bold"
                        onClick={() => onSelect?.(a)} data-testid={`select-advocate-${a.advocate_id}`}
                      >
                        Select Advocate
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      </div>

      <Dialog open={!!profileAdvocate} onOpenChange={(v) => !v && setProfileAdvocate(null)}>
        <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
          {profileAdvocate && (
            <>
              <DialogHeader>
                <DialogTitle className="font-display text-xl">{profileAdvocate.name}</DialogTitle>
                <DialogDescription>
                  <Star className="w-3.5 h-3.5 inline fill-amber-400 text-amber-400 -mt-0.5" /> {profileAdvocate.rating} · {profileAdvocate.hearings_completed} hearings completed
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-3 text-sm">
                <div><div className="cb-overline mb-1">About</div><p className="text-muted-foreground">{profileAdvocate.bio}</p></div>
                <div><div className="cb-overline mb-1">Experience</div><p>{profileAdvocate.experience_years} years · {profileAdvocate.education}</p></div>
                <div><div className="cb-overline mb-1">Primary Courts</div><div className="flex flex-wrap gap-1">{profileAdvocate.primary_courts?.map((c) => <Badge key={c} variant="outline">{c}</Badge>)}</div></div>
                <div><div className="cb-overline mb-1">Practice Areas</div><div className="flex flex-wrap gap-1">{profileAdvocate.practice_areas?.map((p) => <Badge key={p} variant="outline">{p}</Badge>)}</div></div>
                <div><div className="cb-overline mb-1">Languages</div><p>{profileAdvocate.languages?.join(", ")}</p></div>
                {(profileAdvocate.ai_match_score != null || profileAdvocate.ai_match_reasons) && (
                  <div className="pt-2 border-t border-dashed">
                    <div className="cb-overline mb-1">AI Suitability</div>
                    {profileAdvocate.ai_match_score != null && <p>{profileAdvocate.ai_match_score}% match</p>}
                    {profileAdvocate.ai_match_reasons && <p className="text-muted-foreground">{profileAdvocate.ai_match_reasons}</p>}
                  </div>
                )}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
