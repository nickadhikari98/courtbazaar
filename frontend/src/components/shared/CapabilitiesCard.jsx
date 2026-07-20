import React, { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { BadgeCheck } from "lucide-react";
import { getPracticeProfile } from "@/lib/practiceApi";

/* Founder feedback: the professional's identity is "Advocate" — Proxy Counsel
   (and anything else in user.capabilities) is a capability that advocate
   offers, not a replacement identity. This card is the one place that
   distinction is spelled out; reused by Profile.jsx and Practice.jsx so the
   framing stays identical everywhere it appears. */
export const CAPABILITY_LABELS = {
  can_practice_proxy_counsel: "Proxy Counsel",
  can_hire_proxy_counsel: "Hires Proxy Counsel",
  can_manage_firm: "Law Firm Manager",
};

export default function CapabilitiesCard({ user }) {
  const capabilities = user?.capabilities || [];
  const [practiceAreas, setPracticeAreas] = useState([]);

  useEffect(() => {
    if (!capabilities.includes("can_practice_proxy_counsel")) return;
    getPracticeProfile().then((p) => setPracticeAreas(p?.practice_areas || [])).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capabilities.includes("can_practice_proxy_counsel")]);

  const capabilityBadges = capabilities.map((c) => CAPABILITY_LABELS[c]).filter(Boolean);
  if (!capabilityBadges.length && !practiceAreas.length) return null;

  return (
    <Card className="dashboard-card border-none mb-6" data-testid="capabilities-card">
      <CardContent className="p-6">
        <div className="flex items-center gap-2 mb-1">
          <BadgeCheck className="w-4 h-4 text-accent" />
          <span className="cb-overline">Identity</span>
        </div>
        <div className="font-display font-bold text-lg">Advocate</div>
        {!!capabilityBadges.length && (
          <>
            <div className="cb-overline mt-4 mb-1.5">Capabilities</div>
            <div className="flex flex-wrap gap-1.5">
              {capabilityBadges.map((label) => (
                <Badge key={label} variant="outline" className="font-semibold" data-testid={`capability-${label.toLowerCase().replace(/\s+/g, '-')}`}>
                  {label}
                </Badge>
              ))}
            </div>
          </>
        )}
        {!!practiceAreas.length && (
          <>
            <div className="cb-overline mt-4 mb-1.5">Practice areas</div>
            <div className="flex flex-wrap gap-1.5">
              {practiceAreas.map((area) => (
                <Badge key={area} variant="outline" className="font-semibold text-muted-foreground">
                  {area}
                </Badge>
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
