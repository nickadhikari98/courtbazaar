import { Gavel } from "lucide-react";
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
    helperText: "Search, view profile, and select an advocate directly — coming soon via advocate discovery. For now, submit a request below and any available Proxy Counsel can accept it, or target one directly if you know their CourtBazaar ID.",
    reviewTitle: "Review your request",
    emptyStateCopy: {
      title: "No requests yet",
      body: "Send your first request above — any available Proxy Counsel can accept it.",
    },
    workTypeOptions: SERVICE_WORK_TYPES.proxy_counsel,
    requiresWorkType: true,
    supportsAttachments: true,
    supportsBudget: true,
    supportsTargeting: true,
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
      if (fields.target_type === "specific" && !fields.target_advocate_id?.trim()) {
        errors.target_advocate_id = "Enter the advocate's CourtBazaar ID, or switch back to Any Available Advocate";
      }
      return errors;
    },
  },
  // counsel: {...} added when Hire Counsel's request form goes live — same shape
};
