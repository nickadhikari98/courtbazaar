import React, { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Star, MapPin, Languages as LanguagesIcon, Gavel, RefreshCw, Users, Sparkles, ChevronDown, Check } from "lucide-react";
import { formatINR } from "@/lib/api";

const initialsOf = (name) => (name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();

/* Purely presentational — takes the output of useAdvocateRecommendations
   (lib/advocateRecommendationsApi.js) as plain props and renders it. This
   component never imports advocateRecommendationsApi.js and never calls a
   fetch itself; every one of {status, advocates, source, metadata} is
   handed to it by the parent page. That's what makes it safe to swap the
   underlying data source (mock -> plain listing endpoint -> AI
   recommendation service) with zero changes here. */
export default function AvailableAdvocatesPanel({
  status, advocates = [], source, metadata, context, selectedAdvocateId, onSelect, onClear, onRetry,
}) {
  const [profileAdvocate, setProfileAdvocate] = useState(null);
  // Mobile-only collapse (§ Mobile Experience) — desktop (lg:) always shows
  // the full panel via the `lg:block` override below, this state never
  // applies there.
  const [expanded, setExpanded] = useState(false);

  const selectable = source && source !== "mock";
  const title = source === "mock" ? "Suggested Advocate Preview" : source ? "Recommended Proxy Counsels" : "Available Proxy Counsels";
  const hasContext = !!(context?.court_id || context?.state_id);
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

      {hasContext && (
        <Card className="dashboard-card border-none mb-4" data-testid="advocate-request-context">
          <CardContent className="p-4">
            <div className="cb-overline mb-2">Looking for</div>
            <dl className="space-y-1.5 text-sm">
              <div className="flex justify-between gap-2"><dt className="text-muted-foreground">Court</dt><dd className="font-semibold text-right">{context?.court_name || "Not yet selected"}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-muted-foreground">Priority</dt><dd className="font-semibold">{context?.priority || "Normal"}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-muted-foreground">Work Type</dt><dd className="font-semibold text-right">{context?.work_type?.length ? context.work_type.join(", ") : "Not specified"}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-muted-foreground">Hearing Date</dt><dd className="font-semibold">{context?.hearing_date || "Not yet set"}</dd></div>
            </dl>
          </CardContent>
        </Card>
      )}

      {source === "mock" && (
        <div className="text-xs text-muted-foreground bg-secondary/40 border border-border rounded-xl px-3 py-2 mb-4">
          Sample listing — live advocate matching coming soon.
        </div>
      )}

      {/* Read defensively — absent for the mock provider today, appears
          automatically once a real recommendation source populates it. */}
      {metadata?.total_candidates != null && (
        <p className="text-2xs text-muted-foreground mb-3">
          Showing {metadata.returned ?? advocates.length} of {metadata.total_candidates} candidates
          {metadata.generated_at ? ` · updated ${new Date(metadata.generated_at).toLocaleTimeString("en-IN")}` : ""}
        </p>
      )}

      {status === "idle" && (
        <Card className="border-dashed border-2" data-testid="advocates-idle">
          <CardContent className="p-6">
            <MapPin className="w-8 h-8 mx-auto text-muted-foreground mb-2" strokeWidth={1.5} />
            <p className="text-sm font-semibold text-center mb-3">Recommendations will appear once you've selected:</p>
            <ul className="space-y-1.5 text-sm mb-3 max-w-[220px] mx-auto">
              <li className="flex items-center gap-2"><Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> State</li>
              <li className="flex items-center gap-2"><Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> District</li>
              <li className="flex items-center gap-2"><Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> Court</li>
            </ul>
            <p className="text-xs text-muted-foreground text-center">
              Work Type, Priority, Hearing Date, and Budget also help improve future recommendations.
            </p>
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
            <Button type="button" variant="outline" size="sm" onClick={onRetry}>
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Retry
            </Button>
          </CardContent>
        </Card>
      )}

      {status === "empty" && (
        <Card className="border-dashed border-2" data-testid="advocates-empty">
          <CardContent className="p-8 text-center">
            <Users className="w-8 h-8 mx-auto text-muted-foreground mb-2" strokeWidth={1.5} />
            <p className="text-sm text-muted-foreground">No advocates available for this court yet — your request will still broadcast to anyone eligible.</p>
          </CardContent>
        </Card>
      )}

      {status === "ready" && (
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

                  {/* Reserved — only renders once a real recommendation source actually provides these; absent for every mock advocate. */}
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
                        disabled={!selectable} title={!selectable ? "Live recommendations will be available once advocate matching is enabled" : undefined}
                        onClick={() => onSelect?.(a)} data-testid={`select-advocate-${a.advocate_id}`}
                      >
                        Select Advocate
                      </Button>
                    )}
                  </div>
                  {!selectable && (
                    <p className="text-2xs text-muted-foreground mt-1.5">Live recommendations will be available once advocate matching is enabled.</p>
                  )}
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
                {/* Reserved — hidden until a real recommendation source populates it, same rule as the card. */}
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
