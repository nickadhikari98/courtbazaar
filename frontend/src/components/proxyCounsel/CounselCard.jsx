import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Star, MapPin, BadgeCheck, Loader2 } from "lucide-react";
import { formatINR } from "@/lib/api";

export const initialsOf = (name) => (name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();

/* Purely presentational — used by both CounselDiscoveryPanel (AI
   recommendations) and ManualCounselSearch (the "Search More Counsels"
   fallback), so the card looks identical regardless of which path the
   customer took to reach it. `counsel` is one entry from
   lib/advocateRecommendationsApi.js's getAvailableAdvocates. */
export default function CounselCard({ counsel, onViewProfile, onSelect, selecting, disabled }) {
  return (
    <Card className="bento-card border-none" data-testid={`counsel-card-${counsel.advocate_id}`}>
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          <Avatar className="w-12 h-12 flex-shrink-0">
            {counsel.avatar_url && <AvatarImage src={counsel.avatar_url} alt={counsel.name} />}
            <AvatarFallback className="bg-primary text-white text-xs font-bold">{initialsOf(counsel.name)}</AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <div className="font-display font-bold text-sm leading-tight truncate">{counsel.name}</div>
              {counsel.verified && <BadgeCheck className="w-4 h-4 text-accent flex-shrink-0" aria-label="Verified" />}
            </div>
            <div className="flex items-center gap-1 text-xs text-muted-foreground mt-0.5">
              <Star className="w-3 h-3 fill-amber-400 text-amber-400 flex-shrink-0" /> {counsel.rating}
              {(counsel.experience_bracket_label || counsel.experience_years != null) && (
                <>
                  <span className="mx-1">·</span>
                  {counsel.experience_bracket_label || `${counsel.experience_years} yrs experience`}
                </>
              )}
            </div>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-1">
          {counsel.primary_courts?.[0] && (
            <Badge variant="outline" className="text-2xs font-semibold">
              <MapPin className="w-2.5 h-2.5 mr-1" />{counsel.primary_courts[0]}
            </Badge>
          )}
          {counsel.practice_areas?.[0] && (
            <Badge variant="outline" className="text-2xs font-semibold text-accent border-accent/30">
              {counsel.practice_areas[0]}
            </Badge>
          )}
        </div>

        <div className="mt-2 text-sm font-bold">
          {counsel.proposed_fee != null
            ? <>{formatINR(counsel.proposed_fee)} <span className="text-xs font-medium text-muted-foreground">starting from</span></>
            : <span className="text-xs font-medium text-muted-foreground">Fee to be discussed</span>}
        </div>

        <div className="mt-3 flex gap-2">
          <Button type="button" size="sm" variant="outline" className="flex-1" disabled={!!disabled} onClick={() => onViewProfile?.(counsel)} data-testid={`view-profile-${counsel.advocate_id}`}>
            View Profile
          </Button>
          <Button
            type="button" size="sm" className="flex-1 bg-accent hover:bg-accent/90 font-bold"
            disabled={!!selecting || !!disabled} onClick={() => onSelect?.(counsel)} data-testid={`select-counsel-${counsel.advocate_id}`}
          >
            {selecting ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : null} Select Counsel
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
