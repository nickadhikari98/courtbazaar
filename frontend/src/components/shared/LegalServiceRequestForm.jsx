import React, { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
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

   `selectedAdvocate` ({advocate_id, name} | null) integrates the Available
   Advocates panel without this component needing to know anything about
   recommendations: when it changes, the form's own Advocate Preference
   fields update to match. The manual Any/Specific radio in the Work
   Required section still works completely standalone; this just gives an
   external panel a second way to reach the same state. */
export default function LegalServiceRequestForm({ serviceConfig, onSubmit, submitting, selectedAdvocate }) {
  const [fields, setFields] = useState({
    state_id: "", state_name: "", district: "", court_id: "", court_name: "",
    case_title: "", case_number: "", case_type: "", hearing_date: "", hearing_time: "", case_stage: "",
    work_required: [], work_required_notes: "",
    priority: "Normal",
    case_details: "",
    offered_amount: "", is_negotiable: false,
    target_type: "any", target_advocate_id: "", target_advocate_name: "",
  });
  const [files, setFiles] = useState([]);
  const [errors, setErrors] = useState({});

  const set = (patch) => setFields((f) => ({ ...f, ...patch }));

  useEffect(() => {
    if (selectedAdvocate) {
      set({ target_type: "specific", target_advocate_id: selectedAdvocate.advocate_id, target_advocate_name: selectedAdvocate.name });
    } else {
      // Panel selection was cleared (or never made) — don't leave the form
      // pointed at a stale advocate the user can no longer see as selected.
      set({ target_type: "any", target_advocate_id: "", target_advocate_name: "" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-sync when the selected advocate itself changes
  }, [selectedAdvocate?.advocate_id]);

  const toggleWorkType = (option) => {
    const has = fields.work_required.includes(option);
    set({ work_required: has ? fields.work_required.filter((w) => w !== option) : [...fields.work_required, option] });
  };

  // The customer's manually-entered offer — no AI/recommended pricing, no
  // service-based calculation. This is also what drives the payment amount
  // (see `fee` below), so the same number gates both submission and payment.
  const hasValidOfferAmount = Number(fields.offered_amount) > 0;

  const handleSubmit = (e) => {
    e.preventDefault();
    const validationErrors = serviceConfig.validate ? serviceConfig.validate(fields) : {};
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) return;

    const payload = {
      court_id: fields.court_id,
      hearing_date: fields.hearing_date,
      case_details: fields.case_details,
      fee: Number(fields.offered_amount),
      target_advocate_id: fields.target_type === "specific" ? fields.target_advocate_id.trim() : undefined,
      service_type: serviceConfig.serviceType,
      request_details: {
        common: {
          state_id: fields.state_id, state_name: fields.state_name, district: fields.district,
          court_name: fields.court_name,
          case_title: fields.case_title, case_number: fields.case_number || undefined,
          case_type: fields.case_type, case_stage: fields.case_stage, hearing_time: fields.hearing_time,
          priority: fields.priority,
          offered_amount: Number(fields.offered_amount), is_negotiable: fields.is_negotiable,
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
                  <Input
                    value={fields.target_advocate_id}
                    onChange={(e) => set({ target_advocate_id: e.target.value, target_advocate_name: "" })}
                    placeholder="Advocate's CourtBazaar ID"
                  />
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

      {/* 4. Price — customer-entered offer only; no AI or recommended pricing. */}
      {serviceConfig.requiresOfferAmount && (
        <Card className="dashboard-card border-none">
          <CardContent className="p-5 space-y-4">
            <div className="font-display font-bold mb-1">Price</div>
            <div>
              <Label>Your Offer Amount (₹) *</Label>
              <Input
                type="number" min="1" step="1" value={fields.offered_amount}
                onChange={(e) => set({ offered_amount: e.target.value })}
                placeholder="e.g. 5000"
                data-testid="offered-amount"
              />
              {errors.offered_amount && <p className="text-xs text-destructive mt-1">{errors.offered_amount}</p>}
            </div>
            <label className="flex items-center justify-between gap-4 cursor-pointer select-none">
              <span>
                <span className="text-sm font-semibold">Open to Negotiation</span>
                <span className="block text-xs text-muted-foreground mt-0.5">
                  Let advocates propose a different amount before accepting your request.
                </span>
              </span>
              <Switch
                checked={fields.is_negotiable}
                onCheckedChange={(v) => set({ is_negotiable: v })}
                data-testid="negotiable-switch"
              />
            </label>
          </CardContent>
        </Card>
      )}

      {/* 5. Documents */}
      {serviceConfig.supportsAttachments && (
        <Card className="dashboard-card border-none">
          <CardContent className="p-5 space-y-3">
            <div>
              <Label>Attachments (optional)</Label>
              <p className="text-xs text-muted-foreground mb-1.5">{ATTACHMENT_HELPER}</p>
              <input
                type="file" multiple
                onChange={(e) => setFiles(Array.from(e.target.files || []))}
                className="text-sm w-full file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:bg-secondary file:text-sm file:font-semibold"
                data-testid="request-attachments"
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* 6. Review & Submit */}
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
                <dd className="font-semibold mt-0.5">
                  {fields.target_type === "specific" ? (fields.target_advocate_name || fields.target_advocate_id || "—") : "Any available"}
                </dd>
              </div>
            )}
            {serviceConfig.requiresOfferAmount && (
              <div>
                <dt className="cb-overline">Your Offer</dt>
                <dd className="font-semibold mt-0.5">
                  {hasValidOfferAmount ? formatINR(Number(fields.offered_amount)) : "Not specified"}
                  {fields.is_negotiable && <Badge className="ml-2 bg-accent/10 text-accent border-0 font-bold text-2xs align-middle">Negotiable</Badge>}
                </dd>
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
          <Button
            type="submit"
            disabled={submitting || (serviceConfig.requiresOfferAmount && !hasValidOfferAmount)}
            className="bg-accent hover:bg-accent/90 font-bold"
            data-testid="submit-service-request"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin mr-1.5" />} {serviceConfig.submitButtonLabel || "Send Request"}
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}
