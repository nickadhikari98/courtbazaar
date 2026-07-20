import React from "react";
import { Link } from "react-router-dom";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Scale, MapPin, FileText, ListChecks, PenSquare, ArrowRight } from "lucide-react";

/* Placeholder for a distinct "Hire Counsel" service — full legal
   representation, as opposed to Hire Proxy Counsel's single-appearance
   engagements. Onboarding workflows (matching, acceptance, escrow for a
   full engagement) aren't built yet, so this page is intentionally
   informational, not a disabled form — an actually-disabled form reads as
   broken, specific copy doesn't. Once live, it reuses the exact same
   LegalServiceRequestForm component as Hire Proxy Counsel with its own
   entry in config/serviceRequestFields.js's SERVICE_CONFIGS — no parallel
   form, no parallel request model. */
const ARCHITECTURE_STEPS = [
  { icon: MapPin, label: "Location", detail: "Same State → District → Court picker" },
  { icon: FileText, label: "Matter Details", detail: "Same case title, type, hearing date & stage fields" },
  { icon: ListChecks, label: "Work Required", detail: "Its own set of counsel-specific engagement types" },
  { icon: PenSquare, label: "Documents & Review", detail: "Same attachments, budget, and review flow" },
];

export default function HireCounsel() {
  return (
    <PageContainer className="max-w-3xl">
      <PageHeader eyebrow="Services" eyebrowIcon={Scale} title="Hire Counsel"
                  description="Full legal representation for your matter — being onboarded onto CourtBazaar." />

      <Card className="dashboard-card border-none mt-6">
        <CardContent className="p-6">
          <Badge className="bg-accent/10 text-accent border-0 font-bold mb-3">Onboarding in progress</Badge>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Hire Counsel is being onboarded onto CourtBazaar as a distinct service from Hire Proxy Counsel —
            engaging an advocate for full representation on a matter, not just a single hearing appearance.
            Matching, acceptance, and escrow-backed payment for full engagements are still being built.
          </p>
          <p className="text-sm text-muted-foreground leading-relaxed mt-3">
            Once live, requesting Counsel will feel identical to requesting Proxy Counsel today — the same
            structured request architecture, just configured for this service:
          </p>

          <div className="grid sm:grid-cols-2 gap-3 mt-4">
            {ARCHITECTURE_STEPS.map((step) => (
              <div key={step.label} className="flex items-start gap-2.5 bg-secondary/40 border border-border rounded-xl p-3.5">
                <step.icon className="w-4 h-4 text-accent flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-sm font-bold">{step.label}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">{step.detail}</div>
                </div>
              </div>
            ))}
          </div>

          <Link to="/hire-proxy-counsel" className="inline-flex items-center gap-1.5 text-sm font-bold text-accent hover:underline mt-5">
            Need an advocate for a single hearing instead? Try Hire Proxy Counsel <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
