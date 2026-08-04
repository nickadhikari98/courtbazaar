import React, { useState } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Loader2, ShieldCheck } from "lucide-react";
import { SERVICE_WORK_TYPES } from "@/config/serviceWorkTypes";
import { PRIORITY_OPTIONS } from "@/config/serviceRequestFields";

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

  const toggleWorkType = (option) => {
    const has = fields.work_required.includes(option);
    set({ work_required: has ? fields.work_required.filter((w) => w !== option) : [...fields.work_required, option] });
  };

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
          <Input type="time" value={fields.hearing_time} onChange={(e) => set({ hearing_time: e.target.value })} />
        </div>
      </div>

      <div>
        <div className="font-display font-bold text-sm mb-2">Work Required *</div>
        <div className="grid sm:grid-cols-2 gap-2">
          {WORK_TYPE_OPTIONS.map((option) => (
            <label key={option} className="flex items-center gap-2 text-sm font-medium">
              <Checkbox checked={fields.work_required.includes(option)} onCheckedChange={() => toggleWorkType(option)} data-testid={`case-details-work-${option.toLowerCase().replace(/\s+/g, "-")}`} />
              {option}
            </label>
          ))}
        </div>
        {errors.work_required && <p className="text-xs text-destructive mt-1">{errors.work_required}</p>}
        {fields.work_required.includes("Other") && (
          <div className="mt-2">
            <Label>Describe the other work required</Label>
            <Input value={fields.work_required_notes} onChange={(e) => set({ work_required_notes: e.target.value })} />
            {errors.work_required_notes && <p className="text-xs text-destructive mt-1">{errors.work_required_notes}</p>}
          </div>
        )}
      </div>

      <div>
        <div className="font-display font-bold text-sm mb-2">Priority</div>
        <RadioGroup value={fields.priority} onValueChange={(v) => set({ priority: v })} className="flex flex-wrap gap-4">
          {PRIORITY_OPTIONS.map((p) => (
            <label key={p} className="flex items-center gap-2 text-sm font-medium">
              <RadioGroupItem value={p} /> {p}
            </label>
          ))}
        </RadioGroup>
      </div>

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
