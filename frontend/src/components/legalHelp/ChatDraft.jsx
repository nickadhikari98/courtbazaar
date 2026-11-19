import React, { useId, useState } from "react";
import { Download, FileText, CircleAlert } from "lucide-react";
import { api } from "@/lib/api";

// A draft from chat_drafts.py. The draft text is read-only and shows exactly what
// the download will contain: a filled placeholder as its value (accent), an empty
// one as its [placeholder] (danger). The blanks are filled in a separate panel,
// one field per distinct placeholder. Values go only to the download endpoint,
// never to the model, and never touch the legal basis or the citations.
const PLACEHOLDER_RE = /\[([^[\]\n]{1,80})\]/g;
const STYLES = ["title", "heading", "para"];
export const DOWNLOAD_FAILED = "Download failed. Please try again.";
export const NO_HINDI_PDF = "PDF isn't available for Hindi drafts yet. Download the Word file instead.";

export function normalizeDraft(d) {
  if (!d || typeof d.draft_id !== "string" || !Array.isArray(d.blocks)) return null;
  const blocks = d.blocks.filter((b) => b && typeof b.text === "string" && STYLES.includes(b.style))
    .map((b) => ({ style: b.style, text: b.text, fill: b.fill === true }));
  return {
    draftId: d.draft_id,
    title: typeof d.title === "string" ? d.title : "Draft",
    disclaimer: typeof d.disclaimer === "string" ? d.disclaimer : "",
    note: typeof d.note === "string" ? d.note : null,
    fileStem: typeof d.file_stem === "string" ? d.file_stem : "draft",
    pdf: d.pdf !== false,
    blocks,
  };
}

export function placeholderNames(draft) {
  const names = [];
  draft.blocks.filter((b) => b.fill).forEach((b) => {
    for (const m of b.text.matchAll(PLACEHOLDER_RE)) if (!names.includes(m[1])) names.push(m[1]);
  });
  return names;
}

const valueOf = (values, name) => (values[name] || "").trim();

// The template text as it will be downloaded: values in place, empty ones as [placeholders].
function FilledText({ text, values }) {
  const parts = [];
  let last = 0;
  for (const m of text.matchAll(PLACEHOLDER_RE)) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const value = valueOf(values, m[1]);
    parts.push(value
      // Light: the accent darkened to 4.7:1 on the white card (the token is 3.2:1); dark keeps the token.
      ? <span key={m.index} className="font-semibold text-[hsl(32_95%_35%)] dark:text-accent" data-testid="chat-draft-filled">{value}</span>
      : <span key={m.index} className="font-semibold text-destructive" data-testid="chat-draft-empty">{m[0]}</span>);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export default function ChatDraft({ draft }) {
  const idBase = useId();
  const [values, setValues] = useState({});
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const names = placeholderNames(draft);
  const emptyCount = names.filter((n) => !valueOf(values, n)).length;

  // Empty fields are allowed: the advocate may print it and fill the rest by hand.
  const download = async (fmt) => {
    setBusy(fmt);
    setError(null);
    try {
      const filled = Object.fromEntries(names.filter((n) => valueOf(values, n)).map((n) => [n, valueOf(values, n)]));
      const { data } = await api.post(`/ai/drafts/${encodeURIComponent(draft.draftId)}/${fmt}`,
        { values: filled }, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${draft.fileStem}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      // 409: the PDF font can't print a value (e.g. a name in Devanagari); the Word file still works.
      setError(err?.response?.status === 409 ? NO_HINDI_PDF : DOWNLOAD_FAILED);
    } finally {
      setBusy(null);
    }
  };

  const btn = "inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-sm font-medium text-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";
  return (
    <div className="min-w-0 overflow-hidden rounded-xl border border-border bg-card text-card-foreground" data-testid="chat-draft">
      <p className="flex gap-2 border-b border-border bg-muted px-4 py-2 text-xs font-semibold leading-5" data-testid="chat-draft-disclaimer">
        <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span>{draft.disclaimer}</span>
      </p>
      <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_15rem]">
        <article className="min-w-0 space-y-2 break-words px-4 py-3 text-[15px] leading-7" data-testid="chat-draft-text">
          {draft.blocks.map((b, i) => {
            const content = b.fill ? <FilledText text={b.text} values={values} /> : b.text;
            if (b.style === "title") return <h3 key={i} className="text-center font-semibold">{content}</h3>;
            if (b.style === "heading") return <h4 key={i} className="pt-2 font-semibold">{content}</h4>;
            return <p key={i}>{content}</p>;
          })}
          {draft.note && <p className="text-xs text-muted-foreground" data-testid="chat-draft-note">{draft.note}</p>}
        </article>
        <section aria-label="Fill in the blanks" className="min-w-0 space-y-3 border-t border-border bg-muted/40 px-4 py-3 lg:border-l lg:border-t-0" data-testid="chat-draft-panel">
          <h4 className="text-sm font-semibold">Fill in the blanks</h4>
          {names.map((name, i) => (
            <div key={name} className="space-y-1">
              <label htmlFor={`${idBase}-f${i}`} className="block text-xs font-medium text-muted-foreground">{name}</label>
              <input
                id={`${idBase}-f${i}`} type="text" value={values[name] || ""} maxLength={500}
                onChange={(e) => setValues((prev) => ({ ...prev, [name]: e.target.value }))}
                className="block w-full min-w-0 rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                data-testid="chat-draft-field"
              />
            </div>
          ))}
          <p className="pt-1 text-sm text-muted-foreground" role="status" data-testid="chat-draft-empty-count">
            {emptyCount === 0 ? "All blanks filled." : `${emptyCount} of ${names.length} blanks still empty.`}
          </p>
          <div className="flex flex-col gap-2">
            <button type="button" className={btn} onClick={() => download("docx")} disabled={!!busy} data-testid="chat-draft-docx">
              <FileText className="h-4 w-4" aria-hidden="true" />{busy === "docx" ? "Preparing…" : "Download Word (.docx)"}
            </button>
            <button type="button" className={btn} onClick={() => download("pdf")} disabled={!!busy || !draft.pdf}
              title={draft.pdf ? undefined : NO_HINDI_PDF} data-testid="chat-draft-pdf">
              <Download className="h-4 w-4" aria-hidden="true" />{busy === "pdf" ? "Preparing…" : "Download PDF"}
            </button>
          </div>
          {!draft.pdf && <p className="text-xs text-muted-foreground">{NO_HINDI_PDF}</p>}
          {error && <p className="text-sm text-destructive" role="alert" data-testid="chat-draft-error">{error}</p>}
        </section>
      </div>
    </div>
  );
}
