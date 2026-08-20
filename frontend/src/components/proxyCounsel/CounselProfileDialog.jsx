import React from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Star, BadgeCheck } from "lucide-react";
import { formatINR } from "@/lib/api";
import { PRICING_SLOTS, PRICING_SLOT_LABELS, PRICING_COURT_TYPES, PRICING_COURT_TYPE_LABELS } from "@/config/proxyCounselPricing";

/* "View Profile" destination for a CounselCard — shared by both the AI
   recommendations list and the manual search fallback. `counsel` is null
   when closed (controls the Dialog's own open state). */
export default function CounselProfileDialog({ counsel, onOpenChange }) {
  return (
    <Dialog open={!!counsel} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto cb-scroll">
        {counsel && (
          <>
            <DialogHeader>
              <DialogTitle className="font-display text-xl flex items-center gap-1.5">
                {counsel.name}
                {counsel.verified && <BadgeCheck className="w-4 h-4 text-accent" aria-label="Verified" />}
              </DialogTitle>
              <DialogDescription>
                <Star className="w-3.5 h-3.5 inline fill-amber-400 text-amber-400 -mt-0.5" /> {counsel.rating} · {counsel.hearings_completed} hearings completed
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3 text-sm">
              <div><div className="cb-overline mb-1">About</div><p className="text-muted-foreground">{counsel.bio}</p></div>
              <div><div className="cb-overline mb-1">Experience</div><p>{counsel.experience_bracket_label || (counsel.experience_years != null ? `${counsel.experience_years} years` : "—")} · {counsel.education}</p></div>
              <div><div className="cb-overline mb-1">Primary Courts</div><div className="flex flex-wrap gap-1">{counsel.primary_courts?.map((c) => <Badge key={c} variant="outline">{c}</Badge>)}</div></div>
              <div><div className="cb-overline mb-1">Practice Areas</div><div className="flex flex-wrap gap-1">{counsel.practice_areas?.map((p) => <Badge key={p} variant="outline">{p}</Badge>)}</div></div>
              <div><div className="cb-overline mb-1">Languages</div><p>{counsel.languages?.join(", ")}</p></div>
              {PRICING_COURT_TYPES.some((ct) => counsel.pricing?.[ct] && Object.keys(counsel.pricing[ct]).length > 0) ? (
                <div>
                  <div className="cb-overline mb-1">Availability &amp; Pricing</div>
                  <div className="space-y-2">
                    {PRICING_COURT_TYPES.filter((ct) => counsel.pricing?.[ct] && Object.keys(counsel.pricing[ct]).length > 0).map((ct) => (
                      <div key={ct}>
                        <div className="text-xs font-bold text-muted-foreground">{PRICING_COURT_TYPE_LABELS[ct]}</div>
                        <div className="grid grid-cols-2 gap-x-3 gap-y-1 mt-1">
                          {PRICING_SLOTS.filter((s) => counsel.pricing[ct][s] != null).map((s) => (
                            <div key={s} className="flex justify-between text-xs">
                              <span className="text-muted-foreground">{PRICING_SLOT_LABELS[s]}</span>
                              <span className="font-bold">{formatINR(counsel.pricing[ct][s])}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : counsel.proposed_fee != null && (
                <div><div className="cb-overline mb-1">Reference Fee</div><p className="font-bold">{formatINR(counsel.proposed_fee)}</p></div>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
