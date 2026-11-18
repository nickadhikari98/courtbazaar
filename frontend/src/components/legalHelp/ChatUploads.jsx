import React from "react";
import { FileText, X, CircleAlert } from "lucide-react";

// Chat document uploads (backend chat_uploads.py): PDF or DOCX, 10 MB, kept 30 days.
export const UPLOAD_ACCEPT = ".pdf,.docx";
export const UPLOAD_MAX_BYTES = 10 * 1024 * 1024;
export const QUICK_ACTIONS = ["Summarise this document", "Ask a question about it", "Check it against the rules"];
export const ASK_PREFIX = "About the attached document: ";
const GUEST_TEXT = "Sign in to attach documents. File uploads are available to logged-in users only.";
const TOO_LARGE_TEXT = "This file is too large. The limit is 10 MB.";
const WRONG_TYPE_TEXT = "Only PDF and Word (.docx) files can be attached.";
const FAILED_TEXT = "Upload failed. Please try again.";

// Checked before uploading; the server checks again (and pages, scans, length).
export function checkFile(file, signedIn) {
  if (!signedIn) return GUEST_TEXT;
  if (!/\.(pdf|docx)$/i.test(file?.name || "")) return WRONG_TYPE_TEXT;
  if (file.size > UPLOAD_MAX_BYTES) return TOO_LARGE_TEXT;
  return null;
}

// The server's own message for a rejected file (too large, wrong type, scanned PDF…), else a generic one.
export function uploadErrorText(err) {
  const status = err?.response?.status;
  const detail = err?.response?.data?.detail;
  if (status === 413 && typeof detail !== "string") return TOO_LARGE_TEXT;
  if (status && status < 500 && typeof detail === "string") return detail;
  return FAILED_TEXT;
}

export function FileChip({ name, onRemove, testId }) {
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-lg border border-border bg-muted px-2 py-1 text-xs font-medium text-foreground" data-testid={testId}>
      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="truncate" title={name}>{name}</span>
      {onRemove && (
        <button
          type="button" onClick={onRemove} aria-label={`Remove ${name}`}
          className="-mr-1 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-background hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          data-testid="chat-upload-remove"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </span>
  );
}

// Above the composer: this chat's files (removable), the one in flight, an inline error,
// quick actions for files not yet asked about, and the 30-day note once per chat.
export default function AttachmentBar({ uploads, pending, error, onRemove, onDismissError, quickActions, onQuickAction }) {
  if (!uploads.length && !pending && !error) return null;
  return (
    <div className="mb-2 space-y-2 px-1" data-testid="chat-uploads">
      {(uploads.length > 0 || pending) && (
        <div className="flex flex-wrap items-center gap-2">
          {uploads.map((u) => (
            <FileChip key={u.upload_id} name={u.file_name} onRemove={() => onRemove(u)} testId="chat-upload-file" />
          ))}
          {pending && (
            <div className="flex min-w-0 max-w-[16rem] flex-1 flex-col gap-1" data-testid="chat-upload-pending">
              <span className="truncate text-xs text-muted-foreground" title={pending.name}>Uploading {pending.name}…</span>
              <div
                className="h-1.5 w-full overflow-hidden rounded-full bg-muted" role="progressbar"
                aria-label={`Uploading ${pending.name}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pending.progress}
              >
                {/* eslint-disable-next-line no-restricted-syntax -- width is the runtime upload progress */}
                <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${pending.progress}%` }} />
              </div>
            </div>
          )}
        </div>
      )}
      {error && (
        <div role="alert" className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive" data-testid="chat-upload-error">
          <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="flex-1">{error}</span>
          <button type="button" onClick={onDismissError} aria-label="Dismiss" className="shrink-0 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
      {quickActions && (
        <div className="flex flex-wrap gap-2" data-testid="chat-upload-quick-actions">
          {QUICK_ACTIONS.map((text) => (
            <button
              key={text} type="button" onClick={() => onQuickAction(text)}
              className="rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium hover:border-accent/50 hover:bg-accent/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {text}
            </button>
          ))}
        </div>
      )}
      {uploads.length > 0 && (
        <p className="text-2xs text-muted-foreground" data-testid="chat-upload-retention">
          Kept for 30 days, then deleted. Remove a file any time.
        </p>
      )}
    </div>
  );
}
