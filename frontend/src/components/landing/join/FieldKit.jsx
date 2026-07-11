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
import { uploadLeadDocument, removeLeadDocument } from "@/lib/leadsApi";
import { cn } from "@/lib/utils";

function FieldLabel({ label, required }) {
  if (!label) return null;
  return (
    <label className="text-sm font-semibold text-foreground block mb-1.5">
      {label}
      {required && <span className="text-red-500 ml-0.5">*</span>}
    </label>
  );
}

function resolveDateBound(bound) {
  if (bound === "today") return new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD in local time
  return bound;
}

export function TextField({ label, required, placeholder, type = "text", value, onChange, min, max }) {
  return (
    <div>
      <FieldLabel label={label} required={required} />
      <Input
        type={type}
        placeholder={placeholder}
        required={required}
        value={value ?? ""}
        onChange={(e) => onChange?.(e.target.value)}
        min={type === "date" ? resolveDateBound(min) : min}
        max={type === "date" ? resolveDateBound(max) : max}
      />
    </div>
  );
}

export function TextareaField({ label, required, placeholder, rows = 3, value, onChange }) {
  return (
    <div>
      <FieldLabel label={label} required={required} />
      <Textarea
        placeholder={placeholder}
        required={required}
        rows={rows}
        value={value ?? ""}
        onChange={(e) => onChange?.(e.target.value)}
      />
    </div>
  );
}

export function SelectField({ label, required, options = [], placeholder = "Select an option", value, onChange }) {
  return (
    <div>
      <FieldLabel label={label} required={required} />
      <Select value={value || ""} onValueChange={onChange}>
        <SelectTrigger>
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

export function RadioField({ label, required, options = [], other, value, onChange, otherValue, onOtherChange }) {
  const id = useId();
  const isOtherSelected = value === "Other";
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
        {other && (
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

export function FileField({ label, required, hint, multiple, value, onChange, leadId, draftToken, fieldKey }) {
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
          className="flex items-center gap-2.5 border-2 border-dashed border-slate-200 rounded-lg px-3.5 py-3 cursor-pointer hover:border-accent/50 hover:bg-accent/[0.03] transition-colors"
        >
          <UploadCloud className="w-4 h-4 text-accent flex-shrink-0" />
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

/* Turnaround Time select — when "Custom Time" is picked, reveals From/To
   time inputs with a smooth height/opacity transition instead of an abrupt
   layout jump. Used by the E-Filing Partner form. */
export function TurnaroundTimeField({
  label, required, options = [], value, onChange, fromValue, onFromChange, toValue, onToChange,
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
          <div
            className={`grid grid-cols-2 gap-3 pt-3 transition-opacity duration-300 ${isCustom ? "opacity-100" : "opacity-0"}`}
          >
            <div>
              <FieldLabel label="From" required={isCustom} />
              <Input type="time" value={fromValue ?? ""} onChange={(e) => onFromChange?.(e.target.value)} required={isCustom} />
            </div>
            <div>
              <FieldLabel label="To" required={isCustom} />
              <Input type="time" value={toValue ?? ""} onChange={(e) => onToChange?.(e.target.value)} required={isCustom} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* Field type -> component dispatch. `ctx` carries the controlled value/onChange
   for this field (keyed upstream by RoleForm) plus any cross-field context a
   field type needs (e.g. a district field reading its sibling state's value). */
export function renderField(field, key, ctx = {}) {
  const span = field.span === 2 ? "sm:col-span-2" : "";
  const {
    value, onChange, stateValue, otherValue, onOtherChange, fromValue, onFromChange, toValue, onToChange,
    leadId, draftToken, fieldKey: ctxFieldKey,
  } = ctx;

  switch (field.type) {
    case "select":
      return <div key={key} className={span}><SelectField {...field} value={value} onChange={onChange} /></div>;
    case "textarea":
      return <div key={key} className={span}><TextareaField {...field} value={value} onChange={onChange} /></div>;
    case "radio":
      return (
        <div key={key} className={cn(span, field.spacing === "loose" && "mt-2 sm:mt-3")}>
          <RadioField {...field} value={value} onChange={onChange} otherValue={otherValue} onOtherChange={onOtherChange} />
        </div>
      );
    case "checkboxes":
      return (
        <div key={key} className={span}>
          <CheckboxGroupField {...field} value={value} onChange={onChange} otherValue={otherValue} onOtherChange={onOtherChange} />
        </div>
      );
    case "file":
      return (
        <div key={key} className={span}>
          <FileField {...field} value={value} onChange={onChange} leadId={leadId} draftToken={draftToken} fieldKey={ctxFieldKey} />
        </div>
      );
    case "declaration":
      return <div key={key} className="sm:col-span-2"><DeclarationField items={field.items} value={value} onChange={onChange} /></div>;
    case "signature":
      return <div key={key} className={span}><SignatureField value={value} onChange={onChange} /></div>;
    case "state":
      return (
        <div key={key} className={span}>
          <StateDistrictField type="state" label={field.label} required={field.required} value={value} onChange={onChange} multiple={field.multiple} />
        </div>
      );
    case "district":
      return (
        <div key={key} className={span}>
          <StateDistrictField type="district" label={field.label} required={field.required} value={value} onChange={onChange} stateValue={stateValue} multiple={field.multiple} />
        </div>
      );
    case "turnaroundTime":
      return (
        <div key={key} className={span}>
          <TurnaroundTimeField
            {...field}
            value={value}
            onChange={onChange}
            fromValue={fromValue}
            onFromChange={onFromChange}
            toValue={toValue}
            onToChange={onToChange}
          />
        </div>
      );
    default:
      return <div key={key} className={span}><TextField {...field} value={value} onChange={onChange} /></div>;
  }
}
