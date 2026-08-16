/* Mirrors backend/practice.py's PRICING_SLOTS/PRICING_MINIMUMS/EXPERIENCE_BRACKETS
   exactly (founder rate card, 2026-08) — kept as a duplicated static config
   rather than fetched, same tradeoff already accepted for PRIORITY_OPTIONS
   (config/serviceRequestFields.js). If the numbers ever change, update both
   files together; the backend is still the source of truth that actually
   enforces the floor (see practice.validate_pricing) — this file only
   drives the form's labels/placeholders and the profile display. */
export const PRICING_SLOTS = ["morning", "afternoon", "full_day", "weekend", "urgent"];

export const PRICING_SLOT_LABELS = {
  morning: "10 AM – 1 PM",
  afternoon: "2 PM – 5 PM",
  full_day: "Full Day",
  weekend: "Weekends",
  urgent: "Urgent (same-day)",
};

export const PRICING_COURT_TYPES = ["district", "high_court"];

export const PRICING_COURT_TYPE_LABELS = {
  district: "District Courts",
  high_court: "High Courts",
};

export const PRICING_MINIMUMS = {
  district: { morning: 499, afternoon: 499, full_day: 899, weekend: 1999, urgent: 1999 },
  high_court: { morning: 999, afternoon: 999, full_day: 1499, weekend: 2999, urgent: 2999 },
};

export const EXPERIENCE_BRACKETS = [
  { key: "0-3", label: "0–3 yrs" },
  { key: "3-5", label: "3–5 yrs" },
  { key: "5-7", label: "5–7 yrs" },
  { key: "10+", label: "10+ yrs" },
];

export const experienceBracketLabel = (key) => EXPERIENCE_BRACKETS.find((b) => b.key === key)?.label || null;
