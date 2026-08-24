import { Gavel, Scale } from "lucide-react";
import { SERVICE_WORK_TYPES } from "@/config/serviceWorkTypes";

export const PRIORITY_OPTIONS = ["Normal", "Urgent", "Extremely Urgent"];

/* Registry LegalServiceRequestForm actually consumes. Every piece of
   per-service *presentation* (title, description, icon, helper copy, review
   heading, empty-state text) and *capability* (does this service take
   attachments/budget/targeting, what work-type options it offers) lives
   here — the form component itself contains no service-specific literals.
   Onboarding a new legal service (e.g. "counsel" going live) means adding an
   entry here + a SERVICE_WORK_TYPES entry, not editing the form or writing
   a new one. */
export const SERVICE_CONFIGS = {
  proxy_counsel: {
    serviceType: "proxy_counsel",
    title: "Hire Proxy Counsel",
    description: "Request an available proxy counsel to appear on your behalf.",
    heroIcon: Gavel,
    // Browse-grid result count label ("{n} {unitLabel}(s)") — see
    // CounselHiringPage.jsx, the component both this and `counsel` below
    // configure rather than duplicate.
    unitLabel: "proxy counsel",
    helperText: "Fill in your request below — AI recommendations for the best-matched proxy counsels appear automatically once you continue.",
    submitLabel: "Find Proxy Counsel",
    reviewTitle: "Review your request",
    emptyStateCopy: {
      title: "No requests yet",
      body: "Send your first request above — any available Proxy Counsel can accept it.",
    },
    workTypeOptions: SERVICE_WORK_TYPES.proxy_counsel,
    requiresWorkType: true,
    supportsAttachments: true,
    supportsBudget: true,
    // Manual free-text "Specific Advocate ID" targeting is superseded by the
    // AI recommendations + Search More Counsels flow (components/proxyCounsel/*)
    // — selection now happens on a dedicated screen after this form, never by
    // typing an ID here. See HireProxyCounsel.jsx's module docstring.
    supportsTargeting: false,
    validate: (fields) => {
      const errors = {};
      if (!fields.state_id) errors.state_id = "State is required";
      if (!fields.district) errors.district = "District is required";
      if (!fields.court_id) errors.court_id = "Court is required";
      if (!fields.case_title?.trim()) errors.case_title = "Case title is required";
      if (!fields.case_type?.trim()) errors.case_type = "Case type is required";
      if (!fields.hearing_date) errors.hearing_date = "Hearing date is required";
      if (!fields.hearing_time) errors.hearing_time = "Hearing time is required";
      if (!fields.case_stage?.trim()) errors.case_stage = "Stage of case is required";
      if (!fields.case_details?.trim()) errors.case_details = "Instructions are required";
      if (!fields.work_required?.length) errors.work_required = "Select at least one type of work required";
      if (fields.work_required?.includes("Other") && !fields.work_required_notes?.trim()) {
        errors.work_required_notes = "Add a note describing the other work required";
      }
      if (!fields.priority) errors.priority = "Priority is required";
      // Budget is genuinely optional (blank is valid — the counsel's own
      // reference fee applies instead), but if a value IS present it must be
      // positive. Guards against native <input type="number">'s own
      // scroll-wheel-over-a-focused-field behavior silently decrementing an
      // untouched field to 0 or negative — not just a typed mistake.
      if (fields.budget !== "" && fields.budget != null && Number(fields.budget) <= 0) {
        errors.budget = "Proposed budget must be greater than 0";
      }
      return errors;
    },
  },
  // Hire Counsel (founder direction, 2026-08): full-matter representation,
  // as opposed to proxy_counsel's single-appearance engagements — but the
  // same browse/select/negotiate/pay flow (CounselHiringPage.jsx) and the
  // same verified counsel pool, since there's no separate "full
  // representation" professional profile in the schema yet. Only the
  // presentation differs; validate/workTypeOptions/etc. below are unused by
  // that flow today (same as on proxy_counsel), kept out rather than filled
  // in speculatively.
  counsel: {
    serviceType: "counsel",
    title: "Hire Counsel",
    description: "Engage an advocate for full legal representation on your matter.",
    heroIcon: Scale,
    unitLabel: "counsel",
    emptyStateCopy: {
      title: "No requests yet",
      body: "Send your first request above — any available Counsel can accept it.",
    },
  },
};
