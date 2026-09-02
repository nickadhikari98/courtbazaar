import React, { useEffect, useId, useState } from "react";
import { toast } from "sonner";
import { UploadCloud, X, CheckCircle2, Eye, RefreshCw, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Checkbox } from "@/components/ui/checkbox";
import StateDistrictField from "./StateDistrictField";
import DateField from "./DateField";
import { SingleSelectCombobox } from "./Combobox";
import CourtOfPracticeField from "./CourtOfPracticeField";
import { uploadLeadDocument, removeLeadDocument } from "@/lib/leadsApi";
import { cn, resolveDateBound } from "@/lib/utils";
import { TIME_OF_DAY_OPTIONS } from "@/config/proxyCounselPricing";

function FieldLabel({ label, required }) {
  if (!label) return null;
  return (
    <label className="text-sm font-semibold text-foreground block mb-1.5">
      {label}
      {required && <span className="text-red-500 ml-0.5">*</span>}
    </label>
  );
}

// Shared red-border treatment for the field types that own a single native
// input — kept as one class string so the "invalid" look is identical
// everywhere instead of being redefined per component.
const invalidInputClass = "border-red-500 focus-visible:ring-red-500 focus-visible:ring-1";

export function TextField({ label, required, placeholder, type = "text", value, onChange, onBlur, error, min, max }) {
  return (
    <div>
      <FieldLabel label={label} required={required} />
      <Input
        type={type}
        placeholder={placeholder}
        required={required}
        value={value ?? ""}
        onChange={(e) => onChange?.(e.target.value)}
        onBlur={onBlur}
        aria-invalid={!!error}
        className={cn(error && invalidInputClass)}
        min={type === "date" ? resolveDateBound(min) : min}
        max={type === "date" ? resolveDateBound(max) : max}
      />
    </div>
  );
}

export function TextareaField({ label, required, placeholder, rows = 3, value, onChange, onBlur, error }) {
  return (
    <div>
      <FieldLabel label={label} required={required} />
      <Textarea
        placeholder={placeholder}
        required={required}
        rows={rows}
        value={value ?? ""}
        onChange={(e) => onChange?.(e.target.value)}
        onBlur={onBlur}
        aria-invalid={!!error}
        className={cn(error && invalidInputClass)}
      />
    </div>
  );
}

export function SelectField({ label, required, options = [], placeholder = "Select an option", value, onChange, error }) {
  return (
    <div>
      <FieldLabel label={label} required={required} />
      <Select value={value || ""} onValueChange={onChange}>
        <SelectTrigger aria-invalid={!!error} className={cn(error && invalidInputClass)}>
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {options.map((opt) => (
            <SelectItem key={opt} value={opt}>{opt}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export function RadioField({
  label, required, options = [], other, otherTriggerValues, value, onChange, otherValue, onOtherChange,
}) {
  const id = useId();
  const isOtherSelected = otherTriggerValues ? otherTriggerValues.includes(value) : value === "Other";
  return (
    <div>
      <FieldLabel label={label} required={required} />
      <RadioGroup
        value={value || ""}
        onValueChange={onChange}
        className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2.5"
      >
        {options.map((opt) => (
          <div key={opt} className="flex items-center gap-2">
            <RadioGroupItem value={opt} id={`${id}-${opt}`} />
            <label htmlFor={`${id}-${opt}`} className="text-sm cursor-pointer">{opt}</label>
          </div>
        ))}
        {/* Legacy pattern: `options` doesn't include "Other" literally, so a
            synthetic extra choice is appended here. */}
        {other && !otherTriggerValues && (
          <div className="col-span-2 sm:col-span-3 flex items-center gap-2">
            <RadioGroupItem value="Other" id={`${id}-other`} />
            <label htmlFor={`${id}-other`} className="text-sm cursor-pointer flex-shrink-0">Other</label>
            <Input
              placeholder="Please specify"
              className="h-8 text-sm"
              value={otherValue ?? ""}
              onChange={(e) => onOtherChange?.(e.target.value)}
              disabled={!isOtherSelected}
            />
          </div>
        )}
      </RadioGroup>
      {/* otherTriggerValues pattern: the specify-able choices are already
          normal options above; just reveal/require the text field alongside. */}
      {otherTriggerValues && (
        <Input
          placeholder="Please specify"
          className="h-9 text-sm mt-2.5"
          value={otherValue ?? ""}
          onChange={(e) => onOtherChange?.(e.target.value)}
          disabled={!isOtherSelected}
        />
      )}
    </div>
  );
}

export function CheckboxGroupField({ label, required, options = [], other, value = [], onChange, otherValue, onOtherChange }) {
  const id = useId();
  const selected = Array.isArray(value) ? value : [];
  const isOtherChecked = selected.includes("Other");

  const toggle = (opt) => {
    const next = selected.includes(opt) ? selected.filter((v) => v !== opt) : [...selected, opt];
    onChange?.(next);
  };

  return (
    <div>
      <FieldLabel label={label} required={required} />
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2.5">
        {options.map((opt) => (
          <div key={opt} className="flex items-center gap-2">
            <Checkbox
              id={`${id}-${opt}`}
              checked={selected.includes(opt)}
              onCheckedChange={() => toggle(opt)}
            />
            <label htmlFor={`${id}-${opt}`} className="text-sm cursor-pointer">{opt}</label>
          </div>
        ))}
        {other && (
          <div className="col-span-2 sm:col-span-3 flex items-center gap-2">
            <Checkbox
              id={`${id}-other`}
              checked={isOtherChecked}
              onCheckedChange={() => toggle("Other")}
            />
            <label htmlFor={`${id}-other`} className="text-sm cursor-pointer flex-shrink-0">Other</label>
            <Input
              placeholder="Please specify"
              className="h-8 text-sm"
              value={otherValue ?? ""}
              onChange={(e) => onOtherChange?.(e.target.value)}
              disabled={!isOtherChecked}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function formatFileSize(bytes) {
  if (bytes === undefined || bytes === null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Mirrors server.py's validate_upload extension whitelist exactly — catching
// an unsupported type here is purely a faster round-trip, not a new rule.
const ALLOWED_FILE_EXTENSIONS = new Set(["pdf", "jpg", "jpeg", "png"]);

// Field hints are free text like "PDF/JPG/PNG, Max 5MB" — parsed rather than
// duplicated into a separate maxSizeMB prop on every one of the ~20 file
// fields across roleFormData.js, so the hint text stays the single source
// of truth for the limit shown to the user and the limit enforced here.
function parseMaxSizeBytes(hint) {
  const m = /(\d+)\s*MB/i.exec(hint || "");
  return m ? Number(m[1]) * 1024 * 1024 : null;
}

export function FileField({ label, required, hint, multiple, value, onChange, onValidationError, error, leadId, draftToken, fieldKey }) {
  const id = useId();
  const files = Array.isArray(value) ? value : [];
  const [previewUrls, setPreviewUrls] = useState({});
  const [uploading, setUploading] = useState([]); // names currently mid-upload

  // Preview URLs are session-only object URLs, never persisted to the draft —
  // revoke them on unmount so we don't leak blob memory.
  useEffect(() => () => {
    Object.values(previewUrls).forEach((url) => URL.revokeObjectURL(url));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFiles = async (fileList) => {
    const picked = Array.from(fileList || []);
    if (!picked.length) return;

    // Client-side type/size check first — inline, not a toast, so a bad
    // file is reported the same way every other invalid field is (and
    // without a wasted upload request).
    const maxBytes = parseMaxSizeBytes(hint);
    const maxLabel = /\d+\s*MB/i.exec(hint || "")?.[0];
    for (const f of picked) {
      const ext = f.name.includes(".") ? f.name.split(".").pop().toLowerCase() : "";
      if (!ALLOWED_FILE_EXTENSIONS.has(ext)) {
        onValidationError?.(`${f.name}: unsupported file type. Allowed: PDF, JPG, PNG.`);
        return;
      }
      if (maxBytes && f.size > maxBytes) {
        onValidationError?.(`${f.name}: file is too large${maxLabel ? ` (max ${maxLabel})` : ""}.`);
        return;
      }
    }
    onValidationError?.(null);

    if (!leadId || !draftToken) {
      toast.error("Still setting up your application — please wait a moment and try again.");
      return;
    }

    setUploading((prev) => [...prev, ...picked.map((f) => f.name)]);
    const newUrls = {};
    picked.forEach((f) => {
      if (f.type.startsWith("image/")) newUrls[f.name] = URL.createObjectURL(f);
    });
    setPreviewUrls((prev) => (multiple ? { ...prev, ...newUrls } : newUrls));

    try {
      const uploaded = [];
      for (const f of picked) {
        // eslint-disable-next-line no-await-in-loop
        const doc = await uploadLeadDocument(leadId, draftToken, fieldKey, f);
        uploaded.push({ name: f.name, size: f.size, type: f.type, doc_id: doc.doc_id });
      }
      if (!multiple) {
        // Replacing: drop the previously stored document server-side (best-effort).
        const prevDoc = files[0];
        if (prevDoc?.doc_id) removeLeadDocument(leadId, draftToken, prevDoc.doc_id).catch(() => {});
        onChange?.(uploaded);
      } else {
        onChange?.([...files, ...uploaded]);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed. Please try again.");
      setPreviewUrls((prev) => {
        const next = { ...prev };
        picked.forEach((f) => {
          if (next[f.name]) { URL.revokeObjectURL(next[f.name]); delete next[f.name]; }
        });
        return next;
      });
    } finally {
      setUploading((prev) => prev.filter((n) => !picked.some((f) => f.name === n)));
    }
  };

  const removeFile = async (f) => {
    setPreviewUrls((prev) => {
      if (prev[f.name]) URL.revokeObjectURL(prev[f.name]);
      const { [f.name]: _removed, ...rest } = prev;
      return rest;
    });
    onChange?.(files.filter((x) => x.name !== f.name));
    if (f.doc_id && leadId && draftToken) {
      try {
        await removeLeadDocument(leadId, draftToken, f.doc_id);
      } catch {
        /* best-effort — the field is already cleared client-side */
      }
    }
  };

  const hasFiles = files.length > 0;
  const isUploading = uploading.length > 0;

  return (
    <div>
      <FieldLabel label={label} required={required} />

      {isUploading && (
        <div className="space-y-2 mb-2">
          {uploading.map((name) => (
            <div key={name} className="flex items-center gap-3 border border-slate-200 bg-slate-50 rounded-lg px-3.5 py-2.5">
              <Loader2 className="w-5 h-5 text-accent flex-shrink-0 animate-spin" />
              <p className="text-sm font-semibold text-foreground truncate">{name}</p>
              <p className="text-xs text-muted-foreground ml-auto flex-shrink-0">Uploading…</p>
            </div>
          ))}
        </div>
      )}

      {hasFiles && (
        <div className="space-y-2 mb-2">
          {files.map((f) => (
            <div
              key={f.name}
              className="flex items-center gap-3 border border-emerald-200 bg-emerald-50/70 rounded-lg px-3.5 py-2.5"
            >
              <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-foreground truncate">{f.name}</p>
                <p className="text-xs text-emerald-700 font-medium">
                  Upload completed{f.size !== undefined ? ` · ${formatFileSize(f.size)}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                {previewUrls[f.name] && (
                  <a
                    href={previewUrls[f.name]}
                    target="_blank"
                    rel="noreferrer"
                    className="p-1.5 rounded-md text-emerald-700 hover:bg-emerald-100 transition-colors"
                    aria-label={`Preview ${f.name}`}
                  >
                    <Eye className="w-4 h-4" />
                  </a>
                )}
                {!multiple && (
                  <label
                    htmlFor={id}
                    className="p-1.5 rounded-md text-emerald-700 hover:bg-emerald-100 cursor-pointer transition-colors"
                    aria-label={`Replace ${f.name}`}
                  >
                    <RefreshCw className="w-4 h-4" />
                  </label>
                )}
                <button
                  type="button"
                  onClick={() => removeFile(f)}
                  className="p-1.5 rounded-md text-red-600 hover:bg-red-100 transition-colors"
                  aria-label={`Remove ${f.name}`}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {(!hasFiles || multiple) && (
        <label
          htmlFor={id}
          className={cn(
            "flex items-center gap-2.5 border-2 border-dashed rounded-lg px-3.5 py-3 cursor-pointer transition-colors",
            error
              ? "border-red-400 bg-red-50/50 hover:border-red-500"
              : "border-slate-200 hover:border-accent/50 hover:bg-accent/[0.03]",
          )}
        >
          <UploadCloud className={cn("w-4 h-4 flex-shrink-0", error ? "text-red-500" : "text-accent")} />
          <span className="text-sm text-muted-foreground truncate">
            {hasFiles ? "Add more files" : "Click to upload"}
          </span>
          {hint && <span className="text-xs text-muted-foreground/70 ml-auto flex-shrink-0 hidden sm:inline">{hint}</span>}
        </label>
      )}

      <input
        id={id}
        type="file"
        multiple={multiple}
        required={required && files.length === 0}
        className="sr-only"
        accept=".pdf,.jpg,.jpeg,.png"
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}

export function DeclarationField({ items = [], value = [], onChange }) {
  const checked = Array.isArray(value) ? value : [];
  const toggle = (i) => {
    const next = checked.includes(i) ? checked.filter((v) => v !== i) : [...checked, i];
    onChange?.(next);
  };
  return (
    <div className="space-y-2.5">
      {items.map((text, i) => (
        <div key={i} className="flex items-start gap-2.5">
          <Checkbox
            id={`decl-${i}`}
            required
            checked={checked.includes(i)}
            onCheckedChange={() => toggle(i)}
            className="mt-0.5"
          />
          <label htmlFor={`decl-${i}`} className="text-sm text-muted-foreground leading-relaxed cursor-pointer">
            {text}
          </label>
        </div>
      ))}
    </div>
  );
}

export function SignatureField({ value, onChange }) {
  const signature = value ?? "";
  return (
    <div>
      <FieldLabel label="Digital Signature" required />
      <div className="relative">
        <Input
          value={signature}
          onChange={(e) => onChange?.(e.target.value)}
          placeholder="Sign Here"
          className="font-display italic h-14 text-lg"
          required
        />
        {signature && (
          <button
            type="button"
            onClick={() => onChange?.("")}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            aria-label="Clear signature"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}

/* Turnaround Time select — when "Custom Time" is picked, reveals a time-slot
   select with a smooth height/opacity transition instead of an abrupt
   layout jump. Used by the E-Filing Partner form. Bug fix: the reveal used
   to be a literal From/To clock-time pair — switched to the same short
   slot list every other time-of-day picker in the app now uses (see
   TIME_OF_DAY_OPTIONS), a pick not a typed time. `toValue`/`onToChange`
   stay accepted for prop-signature compatibility but are unused — the
   single picked slot now goes entirely into `fromValue`. */
export function TurnaroundTimeField({
  label, required, options = [], value, onChange, fromValue, onFromChange,
}) {
  const isCustom = value === "Custom Time";
  return (
    <div>
      <SelectField label={label} required={required} options={options} value={value} onChange={onChange} />
      <div
        className="grid transition-all duration-300 ease-in-out"
        style={{ gridTemplateRows: isCustom ? "1fr" : "0fr" }}
      >
        <div className="overflow-hidden">
          <div className={`pt-3 transition-opacity duration-300 ${isCustom ? "opacity-100" : "opacity-0"}`}>
            <FieldLabel label="Time Slot" required={isCustom} />
            <Select value={fromValue || undefined} onValueChange={onFromChange}>
              <SelectTrigger><SelectValue placeholder="Select a time slot" /></SelectTrigger>
              <SelectContent>
                {TIME_OF_DAY_OPTIONS.map((opt) => <SelectItem key={opt} value={opt}>{opt}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>
    </div>
  );
}

/* Field type -> component dispatch. `ctx` carries the controlled value/onChange
   for this field (keyed upstream by RoleForm) plus any cross-field context a
   field type needs (e.g. a district field reading its sibling state's value).

   Error display is handled once, here, for every field type uniformly — the
   message renders directly below whatever the field type renders, and the
   wrapping div is what gets scrolled/focused when RoleForm jumps to the
   first invalid field on a blocked Next/Submit. Only the field types with a
   single native input (Text/Textarea/Select/File) additionally get a red
   border on that input — the rest (radio/checkbox groups, date, state/
   district, ...) rely on the message + outer highlight alone. */
export function renderField(field, key, ctx = {}) {
  const span = field.span === 2 ? "sm:col-span-2" : "";
  const {
    value, onChange, onBlur, error, onValidationError, stateValue, otherValue, onOtherChange,
    fromValue, onFromChange, toValue, onToChange, leadId, draftToken, fieldKey: ctxFieldKey, registerRef,
  } = ctx;

  let outerClassName = span;
  let body;

  switch (field.type) {
    case "select":
      body = <SelectField {...field} value={value} onChange={onChange} error={error} />;
      break;
    case "date":
      body = <DateField {...field} value={value} onChange={onChange} />;
      break;
    case "barCouncil":
      body = (
        <>
          <FieldLabel label={field.label} required={field.required} />
          <SingleSelectCombobox
            options={field.options}
            value={value}
            onChange={onChange}
            other={field.other}
            otherValue={otherValue}
            onOtherChange={onOtherChange}
            placeholder="Select your State Bar Council"
          />
        </>
      );
      break;
    case "courtOfPractice":
      body = <CourtOfPracticeField label={field.label} required={field.required} value={value} onChange={onChange} />;
      break;
    case "textarea":
      body = <TextareaField {...field} value={value} onChange={onChange} onBlur={onBlur} error={error} />;
      break;
    case "radio":
      outerClassName = cn(span, field.spacing === "loose" && "mt-2 sm:mt-3");
      body = <RadioField {...field} value={value} onChange={onChange} otherValue={otherValue} onOtherChange={onOtherChange} />;
      break;
    case "checkboxes":
      body = <CheckboxGroupField {...field} value={value} onChange={onChange} otherValue={otherValue} onOtherChange={onOtherChange} />;
      break;
    case "file":
      body = (
        <FileField
          {...field} value={value} onChange={onChange} error={error} onValidationError={onValidationError}
          leadId={leadId} draftToken={draftToken} fieldKey={ctxFieldKey}
        />
      );
      break;
    case "declaration":
      outerClassName = "sm:col-span-2";
      body = <DeclarationField items={field.items} value={value} onChange={onChange} />;
      break;
    case "signature":
      body = <SignatureField value={value} onChange={onChange} />;
      break;
    case "state":
      body = <StateDistrictField type="state" label={field.label} required={field.required} value={value} onChange={onChange} multiple={field.multiple} />;
      break;
    case "district":
      body = (
        <StateDistrictField
          type="district" label={field.label} required={field.required} value={value} onChange={onChange}
          stateValue={stateValue} multiple={field.multiple}
        />
      );
      break;
    case "turnaroundTime":
      body = (
        <TurnaroundTimeField
          {...field}
          value={value}
          onChange={onChange}
          fromValue={fromValue}
          onFromChange={onFromChange}
          toValue={toValue}
          onToChange={onToChange}
        />
      );
      break;
    default:
      body = <TextField {...field} value={value} onChange={onChange} onBlur={onBlur} error={error} />;
  }

  return (
    <div key={key} className={outerClassName} ref={registerRef}>
      {body}
      {error && <p className="text-xs font-medium text-red-600 mt-1.5">{error}</p>}
    </div>
  );
}
