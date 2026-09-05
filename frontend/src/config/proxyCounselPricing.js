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
};

// Founder direction (2026-09): every plain "what time" picker in the app
// (My Practice availability, hearing time, stenographer start time, e-filing
// turnaround) should offer this same short list instead of a literal clock
// input — a user picks a slot, not a minute. Reuses PRICING_SLOT_LABELS
// (minus "urgent", which isn't a time-of-day choice) so there's exactly one
// place these four options are spelled out.
export const TIME_OF_DAY_OPTIONS = PRICING_SLOTS.filter((s) => s !== "urgent").map((s) => PRICING_SLOT_LABELS[s]);

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
  { key: "7-10", label: "7–10 yrs" },
  { key: "10+", label: "10+ yrs" },
];

export const experienceBracketLabel = (key) => EXPERIENCE_BRACKETS.find((b) => b.key === key)?.label || null;

// Mirrors practice.py's EXPERIENCE_PRICING_SURCHARGE/pricing_minimum exactly
// (founder direction, 2026-09, revised) — the rate-card floor scales with
// experience: "0-3" is the unmodified PRICING_MINIMUMS rate, each bracket
// step above that adds another flat surcharge to every slot's floor — the
// step size differs by court type, ₹100/step for district, ₹200/step for
// high_court. Purely for the "Min ₹X" hints/validation this page shows live
// as someone types — the backend is still what actually enforces it (see
// practice.validate_pricing).
export const EXPERIENCE_PRICING_SURCHARGE = { district: 100, high_court: 200 };

export const pricingMinimum = (courtType, slot, experienceBracket) => {
  const base = PRICING_MINIMUMS[courtType][slot];
  const bracketIndex = Math.max(0, EXPERIENCE_BRACKETS.findIndex((b) => b.key === experienceBracket));
  return base + EXPERIENCE_PRICING_SURCHARGE[courtType] * bracketIndex;
};
