import React, { useEffect, useMemo, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Star, MapPin, Languages as LanguagesIcon, Gavel, RefreshCw, Users, Sparkles, ChevronDown, Search, X } from "lucide-react";
import { formatINR } from "@/lib/api";
import { getStates, getCourtsByState } from "@/lib/referenceDataApi";
import { useAdvocateRecommendations } from "@/lib/advocateRecommendationsApi";

const initialsOf = (name) => (name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();

/* The single mode switch — always visible "at the top" regardless of which
   mode is active. AI Mode takes no input at all: flipping it on is the
   entire interaction, the panel below immediately asks the recommendation
   endpoint for its top-ranked verified counsel with zero filters applied
   (see advocateRecommendationsApi.js). Manual Mode (default, off) hands
   control to SearchAdvocatesBar below instead. */
function AiModeToggle({ aiMode, onToggle }) {
  return (
    <Card className="dashboard-card border-none mb-4" data-testid="ai-mode-card">
      <CardContent className="p-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <Sparkles className="w-4 h-4 text-accent flex-shrink-0" />
          <span className="text-sm font-semibold">Use AI Recommendation</span>
        </div>
        <Switch checked={aiMode} onCheckedChange={onToggle} data-testid="ai-mode-toggle" />
      </CardContent>
    </Card>
  );
}

/* Shown only in AI Mode, in place of the manual search bar — no inputs of
   its own, just tells the customer what's happening while the shared results
   list below renders whatever the zero-filter recommendation call ranks. */
function AiRecommendationPanel() {
  return (
    <Card className="dashboard-card border-none mb-4 border border-accent/20 bg-accent/5" data-testid="ai-recommendation-panel">
      <CardContent className="p-4 flex items-start gap-2.5">
        <Sparkles className="w-4 h-4 text-accent flex-shrink-0 mt-0.5" />
        <p className="text-sm font-semibold leading-snug">
          AI will recommend the best verified proxy counsel for your request.
        </p>
      </CardContent>
    </Card>
  );
}

/* Shown only in Manual Mode, in place of the AI panel above — AI Mode hides
   this completely rather than disabling it (see AvailableAdvocatesPanel),
   so there's nothing stale left visible or interactive once the customer
   switches over. State/District/Court cascade the same way
   CourtLocationSelector does (reusing getStates/getCourtsByState — "City" is
   the existing `district` field every seeded court already carries, not a
   new schema field), but none of the three are mandatory here: the
   recommendation endpoint ranks on whatever subset of
   court_id/state_id/district/specialization/min_experience_years is
   actually set. */
function SearchAdvocatesBar({ filters, onFiltersChange, states, districts, courtOptions, hasActiveFilters }) {
  const set = (patch) => onFiltersChange({ ...filters, ...patch });

  return (
    <Card className="dashboard-card border-none mb-4" data-testid="advocate-search-bar">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-1.5 cb-overline">
            Search Advocates <Search className="w-3.5 h-3.5" />
          </div>
          {hasActiveFilters && (
            <button type="button" onClick={() => onFiltersChange({})} className="text-2xs font-semibold text-muted-foreground hover:text-foreground flex items-center gap-1">
              <X className="w-3 h-3" /> Clear
            </button>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="text-2xs">State</Label>
            <Select value={filters.state_id || undefined} onValueChange={(v) => set({ state_id: v, district: "", court_id: "" })}>
              <SelectTrigger className="h-8 text-sm mt-1" data-testid="filter-state"><SelectValue placeholder="Any state" /></SelectTrigger>
              <SelectContent>
                {states.map((s) => <SelectItem key={s.state_id} value={s.state_id}>{s.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-2xs">District</Label>
            <Select value={filters.district || undefined} onValueChange={(v) => set({ district: v, court_id: "" })} disabled={!filters.state_id}>
              <SelectTrigger className="h-8 text-sm mt-1" data-testid="filter-district"><SelectValue placeholder={filters.state_id ? "Any district" : "Select a state first"} /></SelectTrigger>
              <SelectContent>
                {districts.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-2xs">Court</Label>
            <Select value={filters.court_id || undefined} onValueChange={(v) => set({ court_id: v })} disabled={!filters.state_id}>
              <SelectTrigger className="h-8 text-sm mt-1" data-testid="filter-court"><SelectValue placeholder="Any court" /></SelectTrigger>
              <SelectContent>
                {courtOptions.map((c) => <SelectItem key={c.court_id} value={c.court_id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-2xs">Experience (yrs)</Label>
            <Input
              type="number" min="0" value={filters.min_experience_years ?? ""} className="h-8 text-sm mt-1"
              onChange={(e) => set({ min_experience_years: e.target.value ? Number(e.target.value) : undefined })}
              data-testid="filter-experience"
            />
          </div>
          <div className="col-span-2">
            <Label className="text-2xs">Expertise</Label>
            <Input
              value={filters.specialization || ""} placeholder="e.g. Criminal, Corporate" className="h-8 text-sm mt-1"
              onChange={(e) => set({ specialization: e.target.value || undefined })}
              data-testid="filter-expertise"
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/* Proxy Counsel Page — AI Mode toggle + Manual Search, as its own
   independent module (founder follow-up request): AI Mode ON -> zero-input
   AI ranking (reusing counsel_matching.score_candidates via
   GET /recommendations/advocates, see lib/advocateRecommendationsApi.js);
   AI Mode OFF (default) -> the same ranked endpoint, scoped down by whatever
   the manual search bar has set. Deliberately does NOT take a hearing-request
   `context`/location prop from its parent page — it owns its own AI-mode +
   filter state and calls useAdvocateRecommendations itself, so it works the
   same way regardless of what (if anything) a Hire Proxy Counsel request
   form on the same page is doing. `selectedAdvocateId`/`onSelect`/`onClear`
   are the only link back to the parent — purely "the user picked someone",
   not a data dependency in the other direction. */
export default function AvailableAdvocatesPanel({ selectedAdvocateId, onSelect, onClear }) {
  const [aiMode, setAiMode] = useState(false); // OFF by default — manual search is the default experience
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
    if (!filters.state_id) { setCourts([]); return; }
    getCourtsByState(filters.state_id)
      .then((c) => setCourts(c))
      .catch(() => setCourts([]));
  }, [filters.state_id]);

  const districts = useMemo(
    () => Array.from(new Set(courts.map((c) => c.district).filter(Boolean))).sort(),
    [courts],
  );
  const courtOptions = useMemo(
    () => (filters.district ? courts.filter((c) => c.district === filters.district) : courts),
    [courts, filters.district],
  );

  // Switching modes must never leak state across: the other mode's search
  // filters are wiped (so flipping back doesn't resurrect a stale search),
  // any open profile dialog is closed, and — critically — whatever advocate
  // was selected under the previous mode is cleared via onClear, since a
  // manual pick has no bearing on the AI panel and vice versa.
  const switchMode = (nextAiMode) => {
    setAiMode(nextAiMode);
    setFilters({});
    setProfileAdvocate(null);
    onClear?.();
  };

  // In Manual Mode, nothing is fetched until the user has actually applied a
  // filter — `context: null` tells useAdvocateRecommendations not to fetch
  // at all, so no advocate is preloaded/recommended before a real search
  // happens. AI Mode always fetches immediately with zero filters (`{}`).
  const hasActiveFilters = Object.values(filters).some((v) => v !== undefined && v !== "");
  const context = aiMode
    ? {}
    : hasActiveFilters
      ? {
          state_id: filters.state_id || undefined,
          district: filters.district || undefined,
          court_id: filters.court_id || undefined,
          specialization: filters.specialization || undefined,
          min_experience_years: filters.min_experience_years || undefined,
        }
      : null;
  const recommendations = useAdvocateRecommendations(context);
  const { status, advocates = [], metadata, refetch } = recommendations;

  // The heading itself is part of communicating which mode is active — never
  // call Manual Search results "Recommendations" (that word implies AI ranking).
  const title = aiMode ? "AI Recommendations" : "Search Results";
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

      <AiModeToggle aiMode={aiMode} onToggle={switchMode} />

      {aiMode ? (
        <AiRecommendationPanel />
      ) : (
        <SearchAdvocatesBar
          filters={filters} onFiltersChange={setFilters}
          states={states} districts={districts} courtOptions={courtOptions}
          hasActiveFilters={hasActiveFilters}
        />
      )}

      {metadata?.total_candidates != null && (
        <p className="text-2xs text-muted-foreground mb-3">
          Showing {metadata.returned ?? advocates.length} of {metadata.total_candidates} candidates
          {metadata.generated_at ? ` · updated ${new Date(metadata.generated_at).toLocaleTimeString("en-IN")}` : ""}
        </p>
      )}

      {status === "idle" && (
        <Card className="border-dashed border-2" data-testid="advocates-idle">
          <CardContent className="p-8 text-center">
            <Search className="w-8 h-8 mx-auto text-muted-foreground mb-2" strokeWidth={1.5} />
            <p className="text-sm text-muted-foreground">Use the filters above to search for verified proxy counsels.</p>
          </CardContent>
        </Card>
      )}

      {status === "loading" && (
        <div className="space-y-3">{[1, 2, 3].map((i) => <div key={i} className="h-40 shimmer rounded-xl"></div>)}</div>
      )}

      {status === "error" && (
        <Card className="border-dashed border-2" data-testid="advocates-error">
          <CardContent className="p-8 text-center">
            <p className="text-sm text-muted-foreground mb-3">Couldn't load advocates right now.</p>
            <Button type="button" variant="outline" size="sm" onClick={refetch}>
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Retry
            </Button>
          </CardContent>
        </Card>
      )}

      {status === "empty" && (
        <Card className="border-dashed border-2" data-testid="advocates-empty">
          <CardContent className="p-8 text-center">
            <Users className="w-8 h-8 mx-auto text-muted-foreground mb-2" strokeWidth={1.5} />
            <p className="text-sm text-muted-foreground">
              {aiMode ? "No verified proxy counsels are available right now." : "No proxy counsels match your search yet."}
            </p>
          </CardContent>
        </Card>
      )}

      {status === "ready" && (
        <div className="space-y-3">
          {advocates.map((a) => {
            const isSelected = selectedAdvocateId === a.advocate_id;
            // AI Match/reasons/response-time are AI-ranking artifacts — the
            // backend may still return them for a Manual Search result (same
            // scoring pipeline), but Manual Mode must never display them.
            const hasAiInfo = aiMode && (a.ai_match_score != null || a.ai_match_reasons || a.estimated_response_time);
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
                {aiMode && (profileAdvocate.ai_match_score != null || profileAdvocate.ai_match_reasons) && (
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
