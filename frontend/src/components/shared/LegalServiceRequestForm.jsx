import React, { useEffect, useRef, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Info, Paperclip, Loader2 } from "lucide-react";
import { formatINR } from "@/lib/api";
import CourtLocationSelector from "@/components/shared/CourtLocationSelector";
import { PRIORITY_OPTIONS } from "@/config/serviceRequestFields";

const ATTACHMENT_HELPER = "Case papers, Vakalatnama, prior order sheets, or other supporting documents — attached after the request is created.";

/* Generic, configuration-driven request form for any Legal Service Request
   (Hire Proxy Counsel today; Hire Counsel and future services reuse this
   same component with their own `serviceConfig` — see
   config/serviceRequestFields.js). Contains no service-specific literals:
   title/description/icon/helper copy/work-type options/section visibility
   all come from `serviceConfig`.

   `onSubmit(payload, files)` — `payload` separates the existing top-level
   hearing-request fields (court_id, hearing_date, case_details, fee,
   target_advocate_id) from the new `request_details` bag; `files` is the
   raw FileList selected in the Documents step, for the parent page to
   upload (as `case_document`) once the hearing_id exists. This component
   only collects, validates, and structures input — it never calls the API
   itself.

   Two optional props integrate the Available Advocates panel without this
   component needing to know anything about recommendations:
   - `selectedAdvocate` ({advocate_id, name} | null) — when it changes, the
     form's own Advocate Preference fields update to match. The manual
     Any/Specific radio in the Work Required section still works completely
     standalone; this just gives an external panel a second way to reach
     the same state.
   - `onContextChange(context)` — fired whenever a field relevant to
     advocate matching changes, so a parent page can feed a recommendations
     hook without this form knowing that hook exists.

   `initialValues`/`initialFiles` — pre-fill the form (e.g. "Edit Request"
   going back from the counsel-selection step): without these the form
   always mounts blank, so anything the customer already filled in would be
   silently lost on going back to edit a single field. `initialValues` only
   needs to carry the fields being restored (merged over the normal blank
   defaults); `initialFiles` restores the native file input's displayed
   selection via a DataTransfer (file inputs can't take a value/defaultValue
   prop directly). Both are read once, on mount, by design — this form
   doesn't re-sync to a changing initialValues after that. */
export default function LegalServiceRequestForm({
  serviceConfig, onSubmit, submitting, selectedAdvocate, onContextChange, initialValues, initialFiles,
}) {
  const [fields, setFields] = useState(() => ({
    state_id: "", state_name: "", district: "", court_id: "", court_name: "",
    case_title: "", case_number: "", case_type: "", hearing_date: "", hearing_time: "", case_stage: "",
    work_required: [], work_required_notes: "",
    priority: "Normal",
    case_details: "",
    budget: "",
    target_type: "any", target_advocate_id: "",
    ...initialValues,
  }));
  const [files, setFiles] = useState(() => initialFiles || []);
  const [errors, setErrors] = useState({});
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (!initialFiles?.length || !fileInputRef.current) return;
    const dt = new DataTransfer();
    initialFiles.forEach((f) => dt.items.add(f));
    fileInputRef.current.files = dt.files;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- restore once, on mount, matching the initialFiles useState above
  }, []);

  const set = (patch) => setFields((f) => ({ ...f, ...patch }));

  useEffect(() => {
    if (!selectedAdvocate) return;
    set({ target_type: "specific", target_advocate_id: selectedAdvocate.advocate_id });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-sync when the selected advocate itself changes
  }, [selectedAdvocate?.advocate_id]);

  useEffect(() => {
    onContextChange?.({
      court_id: fields.court_id, court_name: fields.court_name, state_id: fields.state_id, district: fields.district,
      work_type: fields.work_required, priority: fields.priority,
      hearing_date: fields.hearing_date, budget: fields.budget,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- report only the fields relevant to advocate matching
  }, [fields.court_id, fields.court_name, fields.state_id, fields.district, fields.work_required, fields.priority, fields.hearing_date, fields.budget]);
  const toggleWorkType = (option) => {
    const has = fields.work_required.includes(option);
    set({ work_required: has ? fields.work_required.filter((w) => w !== option) : [...fields.work_required, option] });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const validationErrors = serviceConfig.validate ? serviceConfig.validate(fields) : {};
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) return;

    const payload = {
      court_id: fields.court_id,
      hearing_date: fields.hearing_date,
      case_details: fields.case_details,
      fee: fields.budget ? Number(fields.budget) : undefined,
      target_advocate_id: fields.target_type === "specific" ? fields.target_advocate_id.trim() : undefined,
      service_type: serviceConfig.serviceType,
      request_details: {
        common: {
          state_id: fields.state_id, state_name: fields.state_name, district: fields.district,
          court_name: fields.court_name,
          case_title: fields.case_title, case_number: fields.case_number || undefined,
          case_type: fields.case_type, case_stage: fields.case_stage, hearing_time: fields.hearing_time,
          priority: fields.priority,
        },
        service_specific: {
          work_required: fields.work_required,
          work_required_notes: fields.work_required_notes || undefined,
        },
      },
    };
    onSubmit(payload, files);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {serviceConfig.helperText && (
        <div className="flex items-start gap-2.5 text-xs text-muted-foreground bg-secondary/40 border border-border rounded-xl px-4 py-3">
          <Info className="w-4 h-4 flex-shrink-0 mt-0.5 text-accent" />
          <span>{serviceConfig.helperText}</span>
        </div>
      )}

      {/* 1. Location */}
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

      {/* 2. Matter Details */}
      <Card className="dashboard-card border-none">
        <CardContent className="p-5 space-y-3">
          <div className="font-display font-bold mb-1">Matter Details</div>
          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <Label>Case Title *</Label>
              <Input value={fields.case_title} onChange={(e) => set({ case_title: e.target.value })} placeholder="e.g. State vs. Sharma" />
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
              <Label>Hearing Date *</Label>
              <Input type="date" value={fields.hearing_date} onChange={(e) => set({ hearing_date: e.target.value })} />
              {errors.hearing_date && <p className="text-xs text-destructive mt-1">{errors.hearing_date}</p>}
            </div>
            <div>
              <Label>Hearing Time *</Label>
              <Input type="time" value={fields.hearing_time} onChange={(e) => set({ hearing_time: e.target.value })} />
              {errors.hearing_time && <p className="text-xs text-destructive mt-1">{errors.hearing_time}</p>}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 3. Work Required */}
      <Card className="dashboard-card border-none">
        <CardContent className="p-5 space-y-4">
          {serviceConfig.requiresWorkType && (
            <div>
              <div className="font-display font-bold mb-2">Work Required</div>
              <div className="grid sm:grid-cols-2 gap-2">
                {serviceConfig.workTypeOptions.map((option) => (
                  <label key={option} className="flex items-center gap-2 text-sm font-medium">
                    <Checkbox checked={fields.work_required.includes(option)} onCheckedChange={() => toggleWorkType(option)} data-testid={`work-type-${option.toLowerCase().replace(/\s+/g, '-')}`} />
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
          )}

          <div>
            <div className="font-display font-bold mb-2">Priority</div>
            <RadioGroup value={fields.priority} onValueChange={(v) => set({ priority: v })} className="flex flex-wrap gap-4">
              {PRIORITY_OPTIONS.map((p) => (
                <label key={p} className="flex items-center gap-2 text-sm font-medium">
                  <RadioGroupItem value={p} /> {p}
                </label>
              ))}
            </RadioGroup>
          </div>

          {serviceConfig.supportsTargeting && (
            <div>
              <div className="font-display font-bold mb-2">Advocate Preference</div>
              <RadioGroup value={fields.target_type} onValueChange={(v) => set({ target_type: v })} className="flex flex-wrap gap-4 mb-2">
                <label className="flex items-center gap-2 text-sm font-medium">
                  <RadioGroupItem value="any" /> Any Available Advocate
                </label>
                <label className="flex items-center gap-2 text-sm font-medium">
                  <RadioGroupItem value="specific" /> Specific Advocate
                </label>
              </RadioGroup>
              {fields.target_type === "specific" && (
                <div>
                  <Input value={fields.target_advocate_id} onChange={(e) => set({ target_advocate_id: e.target.value })} placeholder="Advocate's CourtBazaar ID" />
                  {errors.target_advocate_id && <p className="text-xs text-destructive mt-1">{errors.target_advocate_id}</p>}
                </div>
              )}
            </div>
          )}

          <div>
            <Label>Instructions *</Label>
            <Textarea rows={3} value={fields.case_details} onChange={(e) => set({ case_details: e.target.value })} placeholder="Matter details, what's needed at this hearing" />
            {errors.case_details && <p className="text-xs text-destructive mt-1">{errors.case_details}</p>}
          </div>
        </CardContent>
      </Card>

      {/* 4. Documents */}
      {(serviceConfig.supportsAttachments || serviceConfig.supportsBudget) && (
        <Card className="dashboard-card border-none">
          <CardContent className="p-5 space-y-3">
            {serviceConfig.supportsAttachments && (
              <div>
                <Label>Attachments (optional)</Label>
                <p className="text-xs text-muted-foreground mb-1.5">{ATTACHMENT_HELPER}</p>
                <input
                  ref={fileInputRef}
                  type="file" multiple
                  onChange={(e) => setFiles(Array.from(e.target.files || []))}
                  className="text-sm w-full file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:bg-secondary file:text-sm file:font-semibold"
                  data-testid="request-attachments"
                />
              </div>
            )}
            {serviceConfig.supportsBudget && (
              <div>
                <Label>Proposed Budget (optional)</Label>
                <Input type="number" value={fields.budget} onChange={(e) => set({ budget: e.target.value })} placeholder="₹" />
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* 5. Review & Submit */}
      <Card className="dashboard-card border-none">
        <CardContent className="p-5 space-y-3">
          <div className="font-display font-bold">{serviceConfig.reviewTitle || "Review your request"}</div>
          <dl className="grid sm:grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="cb-overline">Location &amp; Court</dt>
              <dd className="font-semibold mt-0.5">{fields.district || "—"}{fields.court_name ? ` · ${fields.court_name}` : ""}</dd>
            </div>
            <div>
              <dt className="cb-overline">Hearing</dt>
              <dd className="font-semibold mt-0.5">{fields.hearing_date || "—"} {fields.hearing_time && `at ${fields.hearing_time}`}</dd>
            </div>
            {serviceConfig.requiresWorkType && (
              <div className="sm:col-span-2">
                <dt className="cb-overline">Work Required</dt>
                <dd className="mt-1 flex flex-wrap gap-1.5">
                  {fields.work_required.length
                    ? fields.work_required.map((w) => <Badge key={w} variant="outline" className="font-semibold">{w}</Badge>)
                    : <span className="text-muted-foreground">—</span>}
                </dd>
              </div>
            )}
            <div>
              <dt className="cb-overline">Priority</dt>
              <dd className="mt-0.5"><Badge className="bg-accent/10 text-accent border-0 font-bold">{fields.priority}</Badge></dd>
            </div>
            {serviceConfig.supportsTargeting && (
              <div>
                <dt className="cb-overline">Advocate</dt>
                <dd className="font-semibold mt-0.5">{fields.target_type === "specific" ? (fields.target_advocate_id || "—") : "Any available"}</dd>
              </div>
            )}
            {serviceConfig.supportsBudget && (
              <div>
                <dt className="cb-overline">Proposed Budget</dt>
                <dd className="font-semibold mt-0.5">{fields.budget ? formatINR(Number(fields.budget)) : "Not specified"}</dd>
              </div>
            )}
            {serviceConfig.supportsAttachments && (
              <div>
                <dt className="cb-overline">Attachments</dt>
                <dd className="font-semibold mt-0.5 flex items-center gap-1.5">
                  {files.length ? <><Paperclip className="w-3.5 h-3.5" /> {files.length} file{files.length > 1 ? "s" : ""}</> : "None"}
                </dd>
              </div>
            )}
          </dl>
          <Button type="submit" disabled={submitting} className="bg-accent hover:bg-accent/90 font-bold" data-testid="submit-service-request">
            {submitting && <Loader2 className="w-4 h-4 animate-spin mr-1.5" />} {serviceConfig.submitLabel || "Send Request"}
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}
