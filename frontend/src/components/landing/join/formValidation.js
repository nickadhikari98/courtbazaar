/* Shared field-key derivation + validation logic for every "Join as..."
   role form (RoleForm.jsx renders from roleFormData.js's field lists via
   FieldKit.jsx). Centralized here so RoleForm's per-step gating and
   FieldKit's per-keystroke inline validation both derive errors the exact
   same way — one definition of "is this field currently valid", not two
   that can drift apart. */

function slugify(str) {
  return String(str).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/(^_+|_+$)/g, "");
}

export function fieldKey(sectionTitle, field, index) {
  const base = field.label || field.type || `field_${index}`;
  return `${slugify(sectionTitle)}__${slugify(base)}`;
}

export function isValueFilled(field, value) {
  if (field.type === "declaration") {
    return Array.isArray(value) && value.length === (field.items?.length || 0);
  }
  if (field.type === "checkboxes" || field.type === "file") {
    return Array.isArray(value) && value.length > 0;
  }
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "string") return value.trim().length > 0;
  return value !== undefined && value !== null && value !== "";
}

// Mirrors leads.py's is_valid_phone/_PHONE_VALID_RE exactly (10 digits,
// first digit 6-9) — the point of validating client-side is to never let
// the frontend call something valid that the backend would then reject at
// actual submit time.
export function validateMobile(value) {
  if (!/^\d+$/.test(value)) return "Mobile number must contain digits only.";
  if (value.length !== 10) return "Mobile number must contain exactly 10 digits.";
  if (!/^[6-9]/.test(value)) return "Enter a valid 10-digit Indian mobile number.";
  return null;
}

// Mirrors leads.py's is_valid_email/_EMAIL_VALID_RE exactly.
export function validateEmailFormat(value) {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value.trim()) ? null : "Enter a valid email address.";
}

export function validatePincode(value) {
  return /^[1-9]\d{5}$/.test(value.trim()) ? null : "PIN code must be exactly 6 digits.";
}

export function validateGST(value) {
  const v = value.trim().toUpperCase();
  return /^\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z]Z[0-9A-Z]$/.test(v) ? null : "Enter a valid 15-character GSTIN.";
}

export function validatePAN(value) {
  const v = value.trim().toUpperCase();
  return /^[A-Z]{5}\d{4}[A-Z]$/.test(v) ? null : "Enter a valid PAN (e.g. ABCDE1234F).";
}

export function validateAadhaar(value) {
  const digits = value.replace(/\s+/g, "");
  if (!/^\d{12}$/.test(digits)) return "Aadhaar number must be exactly 12 digits.";
  if (/^[01]/.test(digits)) return "Enter a valid Aadhaar number.";
  return null;
}

function formatError(field, value) {
  if (!isValueFilled(field, value)) return null; // emptiness is the required-check's job, not this one's
  if (field.type === "tel") return validateMobile(String(value));
  if (field.type === "email") return validateEmailFormat(String(value));
  if (field.validate === "pincode") return validatePincode(String(value));
  if (field.validate === "gst") return validateGST(String(value));
  if (field.validate === "pan") return validatePAN(String(value));
  if (field.validate === "aadhaar") return validateAadhaar(String(value));
  return null;
}

// Full per-field check: required-ness, format, and the cross-field cases
// (future-dated DOB, "Custom Time" needing From/To, "Other" needing a typed
// value) that used to only ever surface as one section-wide "please fill in
// all required fields" toast with no indication of which field.
export function getFieldError(field, key, values) {
  const isRequired = field.required || field.type === "signature";
  const value = values[key];

  if (isRequired && !isValueFilled(field, value)) {
    return field.type === "file" ? "This document is required." : "This field is required.";
  }

  const fmtError = formatError(field, value);
  if (fmtError) return fmtError;

  if (field.type === "date" && field.max === "today" && value) {
    const today = new Date().toLocaleDateString("en-CA");
    if (value > today) return "Date cannot be in the future.";
  }
  if (field.type === "turnaroundTime" && value === "Custom Time") {
    // Bug fix: this used to also require `${key}__to`, back when the reveal
    // was a literal From/To clock-time pair — TurnaroundTimeField now
    // offers a single time-of-day slot (see TIME_OF_DAY_OPTIONS), so only
    // `__from` is ever set; the old check made "Custom Time" impossible to
    // submit once the second input was removed.
    if (!values[`${key}__from`]) return "Please select a time slot.";
  }
  if (field.other || field.otherTriggerValues) {
    const isOtherSelected = field.otherTriggerValues
      ? field.otherTriggerValues.includes(value)
      : value === "Other";
    if (isOtherSelected && !isValueFilled({ type: "text" }, values[`${key}__other`])) {
      return "Please specify.";
    }
  }
  return null;
}

// Every field in a section -> { [key]: message } for the ones currently invalid.
export function validateSection(section, values) {
  const errors = {};
  section.fields.forEach((field, i) => {
    const key = fieldKey(section.title, field, i);
    const err = getFieldError(field, key, values);
    if (err) errors[key] = err;
  });
  return errors;
}
