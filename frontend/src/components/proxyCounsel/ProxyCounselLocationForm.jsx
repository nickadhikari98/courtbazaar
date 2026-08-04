import React, { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Info, ArrowRight } from "lucide-react";
import CourtLocationSelector from "@/components/shared/CourtLocationSelector";

/* Step 1 of the Proxy Counsel request flow (see HireProxyCounsel.jsx):
   deliberately just Location + Hearing Date — founder's explicit BlaBlaCar
   comparison was "fill state, district, court, date, then show me
   recommendations", not the full case intake. Everything else (case title,
   type, stage, work required, instructions, attachments) moves to
   ProxyCounselCaseDetailsForm, filled in only after a counsel is selected
   AND payment is confirmed — see HearingDetailDialog.jsx.

   Kept as its own small component (not a stripped-down mode of the generic
   LegalServiceRequestForm) so this flow's fields can diverge freely without
   touching the form Hire Counsel is documented to reuse later. */
export default function ProxyCounselLocationForm({ onSubmit, initialValues }) {
  const [fields, setFields] = useState(() => ({
    state_id: "", state_name: "", district: "", court_id: "", court_name: "", hearing_date: "",
    ...initialValues,
  }));
  const [errors, setErrors] = useState({});
  const set = (patch) => setFields((f) => ({ ...f, ...patch }));

  const handleSubmit = (e) => {
    e.preventDefault();
    const validationErrors = {};
    if (!fields.state_id) validationErrors.state_id = "State is required";
    // No district check here — CourtLocationSelector deliberately leaves
    // district blank for a High Court pick (it isn't seated in any
    // district), so court_id is the only real location requirement; district
    // is just a narrowing step District Court mode happens to use.
    if (!fields.court_id) validationErrors.court_id = "Court is required";
    if (!fields.hearing_date) validationErrors.hearing_date = "Hearing date is required";
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) return;
    onSubmit(fields);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="flex items-start gap-2.5 text-xs text-muted-foreground bg-secondary/40 border border-border rounded-xl px-4 py-3">
        <Info className="w-4 h-4 flex-shrink-0 mt-0.5 text-accent" />
        <span>Tell us where and when — we'll show you the best-matched proxy counsels next. Case details and documents are shared with your counsel only after payment.</span>
      </div>

      <Card className="dashboard-card border-none">
        <CardContent className="p-5">
          <div className="font-display font-bold mb-3">Location</div>
          <CourtLocationSelector
            value={{ state_id: fields.state_id, state_name: fields.state_name, district: fields.district, court_id: fields.court_id, court_name: fields.court_name }}
            onChange={(loc) => set(loc)}
          />
          {(errors.state_id || errors.district || errors.court_id) && (
            <p className="text-xs text-destructive mt-2">{errors.state_id || errors.district || errors.court_id}</p>
          )}
        </CardContent>
      </Card>

      <Card className="dashboard-card border-none">
        <CardContent className="p-5">
          <div className="font-display font-bold mb-3">Hearing Date</div>
          <div className="max-w-xs">
            <Label>Date *</Label>
            <Input type="date" value={fields.hearing_date} onChange={(e) => set({ hearing_date: e.target.value })} data-testid="proxy-counsel-hearing-date" />
            {errors.hearing_date && <p className="text-xs text-destructive mt-1">{errors.hearing_date}</p>}
          </div>
        </CardContent>
      </Card>

      <Button type="submit" className="bg-accent hover:bg-accent/90 font-bold" data-testid="proxy-counsel-find-counsel">
        Find Proxy Counsel <ArrowRight className="w-4 h-4 ml-2" />
      </Button>
    </form>
  );
}
