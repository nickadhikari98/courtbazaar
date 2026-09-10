import React, { useState } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loader2, ShieldCheck } from "lucide-react";
import { SERVICE_WORK_TYPES } from "@/config/serviceWorkTypes";
import { TIME_OF_DAY_OPTIONS } from "@/config/proxyCounselPricing";
import { toggleInArray } from "@/lib/utils";
import WorkRequiredField from "@/components/shared/WorkRequiredField";
import PriorityField from "@/components/shared/PriorityField";

const WORK_TYPE_OPTIONS = SERVICE_WORK_TYPES.proxy_counsel;

/* Step 3 of the Proxy Counsel request flow (see HireProxyCounsel.jsx /
   HearingDetailDialog.jsx): the actual case brief, only ever shown to the
   requester once payment is confirmed (backend refuses the submit call
   otherwise — see hearings.submit_case_details). This is deliberately the
   same fields the old all-in-one intake form used to collect upfront,
   just moved behind the payment gate rather than in front of it — no new
   fields are being introduced here, only a later reveal point. */
export default function ProxyCounselCaseDetailsForm({ onSubmit, submitting }) {
  const [fields, setFields] = useState({
    case_title: "", case_number: "", case_type: "", case_stage: "", hearing_time: "",
    work_required: [], work_required_notes: "", priority: "Normal", case_details: "",
  });
  const [errors, setErrors] = useState({});
  const set = (patch) => setFields((f) => ({ ...f, ...patch }));

  const toggleWorkType = (option) => set({ work_required: toggleInArray(fields.work_required, option) });

  const handleSubmit = (e) => {
    e.preventDefault();
    const validationErrors = {};
    if (!fields.case_title.trim()) validationErrors.case_title = "Case title is required";
    if (!fields.case_type.trim()) validationErrors.case_type = "Case type is required";
    if (!fields.case_stage.trim()) validationErrors.case_stage = "Stage of case is required";
    if (!fields.work_required.length) validationErrors.work_required = "Select at least one type of work required";
    if (fields.work_required.includes("Other") && !fields.work_required_notes.trim()) {
      validationErrors.work_required_notes = "Add a note describing the other work required";
    }
    if (!fields.case_details.trim()) validationErrors.case_details = "Instructions are required";
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) return;
    onSubmit(fields);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 border rounded-lg p-4 bg-accent/5 border-accent/30">
      <div className="flex items-start gap-2.5">
        <ShieldCheck className="w-4 h-4 flex-shrink-0 mt-0.5 text-accent" />
        <div>
          <div className="font-display font-bold text-sm">Share case details</div>
          <p className="text-xs text-muted-foreground mt-0.5">Payment is confirmed — add your case brief so your counsel can prepare. Documents can be attached below once this is saved.</p>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        <div>
          <Label>Case Title *</Label>
          <Input value={fields.case_title} onChange={(e) => set({ case_title: e.target.value })} placeholder="e.g. State vs. Sharma" data-testid="case-details-title" />
          {errors.case_title && <p className="text-xs text-destructive mt-1">{errors.case_title}</p>}
        </div>
        <div>
          <Label>Case Number (optional)</Label>
          <Input value={fields.case_number} onChange={(e) => set({ case_number: e.target.value })} placeholder="e.g. CC 1234/2026" />
        </div>
        <div>
          <Label>Case Type *</Label>
          <Input value={fields.case_type} onChange={(e) => set({ case_type: e.target.value })} placeholder="e.g. Civil, Criminal, Writ" />
          {errors.case_type && <p className="text-xs text-destructive mt-1">{errors.case_type}</p>}
        </div>
        <div>
          <Label>Stage of Case *</Label>
          <Input value={fields.case_stage} onChange={(e) => set({ case_stage: e.target.value })} placeholder="e.g. Framing of charges, Final arguments" />
          {errors.case_stage && <p className="text-xs text-destructive mt-1">{errors.case_stage}</p>}
        </div>
        <div>
          <Label>Hearing Time (optional)</Label>
          <Select value={fields.hearing_time || undefined} onValueChange={(v) => set({ hearing_time: v })}>
            <SelectTrigger><SelectValue placeholder="Select a time slot" /></SelectTrigger>
            <SelectContent>
              {TIME_OF_DAY_OPTIONS.map((opt) => <SelectItem key={opt} value={opt}>{opt}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      <WorkRequiredField
        options={WORK_TYPE_OPTIONS}
        value={fields.work_required}
        onToggle={toggleWorkType}
        notes={fields.work_required_notes}
        onNotesChange={(v) => set({ work_required_notes: v })}
        error={errors.work_required}
        notesError={errors.work_required_notes}
        testIdPrefix="case-details-work"
        compact
      />

      <PriorityField value={fields.priority} onChange={(v) => set({ priority: v })} compact />

      <div>
        <Label>Instructions *</Label>
        <Textarea rows={3} value={fields.case_details} onChange={(e) => set({ case_details: e.target.value })} placeholder="Matter details, what's needed at this hearing" />
        {errors.case_details && <p className="text-xs text-destructive mt-1">{errors.case_details}</p>}
      </div>

      <Button type="submit" disabled={submitting} className="bg-accent hover:bg-accent/90 font-bold" data-testid="case-details-submit">
        {submitting && <Loader2 className="w-4 h-4 animate-spin mr-1.5" />} Share Case Details
      </Button>
    </form>
  );
}
