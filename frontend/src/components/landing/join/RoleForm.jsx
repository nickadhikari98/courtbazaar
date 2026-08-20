import React, { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { renderField } from "./FieldKit";
import useDraftForm from "./useDraftForm";
import SubmissionSuccess from "./SubmissionSuccess";
import { submitLead, toBackendRole } from "@/lib/leadsApi";
import { fieldKey, getFieldError, validateSection } from "./formValidation";

// Typed free-text inputs defer their first validation to onBlur (so an error
// doesn't flash mid-keystroke on the very first attempt); once shown (or
// once the field has been blurred at least once) it re-validates live on
// every change so it can clear itself the moment the value becomes valid.
// Everything else (select/radio/checkbox/file/date/...) is a discrete "pick"
// action, so it validates immediately on change — there's no meaningful
// "still mid-typing" state to protect against.
const DEFERRED_VALIDATION_TYPES = new Set([undefined, "text", "tel", "email", "number", "textarea"]);

function buildInitialValues(sections) {
  const values = {};
  sections.forEach((section) => {
    section.fields.forEach((field, i) => {
      const key = fieldKey(section.title, field, i);
      if (field.type === "state") {
        values[key] = field.multiple ? [field.default || "Delhi"] : (field.default || "Delhi");
      } else if (field.type === "district" && field.multiple) {
        values[key] = [];
      } else if (field.type === "date" && field.default === "today") {
        values[key] = new Date().toLocaleDateString("en-CA");
      } else if (field.default !== undefined) {
        values[key] = field.default;
      } else if (field.type === "checkboxes" || field.type === "declaration" || field.type === "file" || field.type === "courtOfPractice") {
        values[key] = [];
      } else {
        values[key] = "";
      }
    });
  });
  return values;
}

export default function RoleForm({ roleLabel, roleKey, sections = [], onDone }) {
  const initialValues = useMemo(() => buildInitialValues(sections), [sections]);
  const storageKey = roleKey ? `courtbazaar_draft_${roleKey}` : null;
  const roleAppliedFor = toBackendRole(roleKey);
  const {
    values, setValue, currentStep, setCurrentStep,
    hasPendingDraft, resumeDraft, discardDraft, saveDraft, clearDraft, resetForm,
    leadId, draftToken, ensureLeadDraft,
  } = useDraftForm(storageKey, initialValues, roleAppliedFor);

  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [errors, setErrors] = useState({});
  const [touched, setTouched] = useState({});
  const stepHeadingRef = useRef(null);
  const fieldRefs = useRef({});

  // A draft needs to exist server-side before a file field can attach an
  // upload to it — a document can be the very first thing a user fills in,
  // so this can't wait for the first autosave/explicit-save.
  useEffect(() => {
    if (!hasPendingDraft) ensureLeadDraft().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasPendingDraft]);

  const totalSteps = sections.length;
  const section = sections[currentStep];
  const isFirstStep = currentStep === 0;
  const isLastStep = currentStep === totalSteps - 1;

  const goToStep = (next) => {
    setCurrentStep(next);
    requestAnimationFrame(() => stepHeadingRef.current?.focus());
  };

  const setFieldError = (key, message) => {
    setErrors((prev) => {
      if (!message) {
        if (!(key in prev)) return prev;
        const { [key]: _drop, ...rest } = prev;
        return rest;
      }
      if (prev[key] === message) return prev;
      return { ...prev, [key]: message };
    });
  };

  const handleFieldChange = (field, key, val) => {
    setValue(key, val);
    const nextValues = { ...values, [key]: val };
    if (!DEFERRED_VALIDATION_TYPES.has(field.type)) {
      setTouched((prev) => (prev[key] ? prev : { ...prev, [key]: true }));
      setFieldError(key, getFieldError(field, key, nextValues));
    } else if (touched[key]) {
      setFieldError(key, getFieldError(field, key, nextValues));
    }
  };

  const handleFieldBlur = (field, key) => {
    setTouched((prev) => (prev[key] ? prev : { ...prev, [key]: true }));
    setFieldError(key, getFieldError(field, key, values));
  };

  const focusFirstError = (sectionErrors) => {
    const firstKey = section.fields
      .map((field, i) => fieldKey(section.title, field, i))
      .find((k) => sectionErrors[k]);
    const node = firstKey && fieldRefs.current[firstKey];
    if (!node) return;
    node.scrollIntoView({ behavior: "smooth", block: "center" });
    node.querySelector("input, textarea, button, [role='combobox']")?.focus();
  };

  // Runs before Next/Submit: validates every field on the current step (not
  // just the ones already touched), so a field the user never interacted
  // with — e.g. skipped straight past — still gets caught here instead of
  // silently passing.
  const validateCurrentStep = () => {
    const sectionErrors = validateSection(section, values);
    setErrors((prev) => {
      const next = { ...prev };
      section.fields.forEach((field, i) => {
        const key = fieldKey(section.title, field, i);
        if (sectionErrors[key]) next[key] = sectionErrors[key];
        else delete next[key];
      });
      return next;
    });
    setTouched((prev) => {
      const next = { ...prev };
      section.fields.forEach((field, i) => { next[fieldKey(section.title, field, i)] = true; });
      return next;
    });
    if (Object.keys(sectionErrors).length > 0) {
      focusFirstError(sectionErrors);
      return false;
    }
    return true;
  };

  const handleNext = () => {
    if (isLastStep) return;
    if (!validateCurrentStep()) return;
    goToStep(currentStep + 1);
  };
  const handlePrevious = () => {
    if (!isFirstStep) goToStep(currentStep - 1);
  };

  const handleSaveDraft = async () => {
    try {
      await saveDraft();
      toast.success("Draft saved. You can resume this application anytime.");
    } catch {
      toast.error("Your progress is saved on this device, but we couldn't back it up online. Check your connection and try again.");
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isLastStep) return;
    if (!validateCurrentStep()) return;
    setSubmitting(true);
    try {
      const ids = await ensureLeadDraft();
      await submitLead(ids.leadId, ids.draftToken);
      setSubmitted(true);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "We couldn't submit your application. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleBackToHome = () => {
    clearDraft();
    resetForm();
    setSubmitted(false);
    onDone?.();
  };

  if (submitted) {
    return <SubmissionSuccess roleLabel={roleLabel} onBackToHome={handleBackToHome} />;
  }

  if (!section) return null;

  let lastStateValue;

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {hasPendingDraft && (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-accent/5 border border-accent/30 rounded-lg px-4 py-3">
          <p className="text-sm font-semibold text-foreground">Resume your saved draft?</p>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Button type="button" size="sm" variant="outline" onClick={discardDraft}>
              Start Fresh
            </Button>
            <Button type="button" size="sm" className="bg-accent hover:bg-accent/90 text-white" onClick={resumeDraft}>
              Resume
            </Button>
          </div>
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs font-bold text-accent uppercase tracking-wide">
            Step {currentStep + 1} of {totalSteps}
          </span>
        </div>
        <div className="w-full h-1 bg-slate-100 rounded-full overflow-hidden mb-3">
          <div
            className="h-full bg-accent rounded-full transition-all duration-300"
            style={{ width: `${((currentStep + 1) / totalSteps) * 100}%` }}
          />
        </div>
        <h4
          ref={stepHeadingRef}
          tabIndex={-1}
          className="font-display font-bold text-sm uppercase tracking-wide text-primary/80 mb-3 pb-2 border-b border-slate-100 outline-none"
        >
          {section.title}
        </h4>
        <div className="grid sm:grid-cols-2 gap-x-4 gap-y-4">
          {section.fields.map((field, i) => {
            const key = fieldKey(section.title, field, i);
            if (field.type === "state") lastStateValue = values[key];

            const ctx = {
              value: values[key],
              onChange: (v) => handleFieldChange(field, key, v),
              onBlur: () => handleFieldBlur(field, key),
              error: errors[key] || null,
              registerRef: (node) => { fieldRefs.current[key] = node; },
            };
            if (field.type === "district") ctx.stateValue = lastStateValue;
            if (field.type === "file") {
              ctx.leadId = leadId;
              ctx.draftToken = draftToken;
              ctx.fieldKey = key;
              ctx.onValidationError = (message) => setFieldError(key, message);
            }
            if (field.other || field.otherTriggerValues) {
              const otherKey = `${key}__other`;
              ctx.otherValue = values[otherKey];
              ctx.onOtherChange = (v) => setValue(otherKey, v);
            }
            if (field.type === "turnaroundTime") {
              const fromKey = `${key}__from`;
              const toKey = `${key}__to`;
              ctx.fromValue = values[fromKey];
              ctx.onFromChange = (v) => setValue(fromKey, v);
              ctx.toValue = values[toKey];
              ctx.onToChange = (v) => setValue(toKey, v);
            }
            return renderField(field, key, ctx);
          })}
        </div>
      </div>

      <div className="sticky bottom-0 -mx-6 -mb-6 mt-4 bg-white border-t border-slate-100 px-4 sm:px-6 py-3 sm:py-4">
        <div className="flex flex-wrap items-center justify-between gap-y-2 gap-x-3">
          <div>
            {!isFirstStep && (
              <Button type="button" variant="outline" onClick={handlePrevious} className="font-bold">
                <ArrowLeft className="w-4 h-4 mr-1.5" /> Previous
              </Button>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2 ml-auto justify-end">
            <Button type="button" variant="outline" onClick={handleSaveDraft} className="font-bold text-muted-foreground border-slate-300 px-3 sm:px-4">
              Save as Draft
            </Button>
            {!isLastStep ? (
              <Button type="button" onClick={handleNext} className="bg-primary hover:bg-primary/90 font-bold px-4 sm:px-6">
                Next <ArrowRight className="w-4 h-4 ml-1.5" />
              </Button>
            ) : (
              <Button type="submit" disabled={submitting} className="bg-accent hover:bg-accent/90 text-white font-bold px-5 sm:px-8">
                {submitting ? "Submitting..." : "Submit Application"}
              </Button>
            )}
          </div>
        </div>
      </div>
    </form>
  );
}
