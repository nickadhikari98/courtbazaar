import React from "react";
import { BookOpen, ExternalLink, Globe } from "lucide-react";

/* The "Sources" block under a document answer. Every entry comes from the
   response's `citations`, which the server builds from approved-source
   metadata and the text actually retrieved (llm_service.build_citations) —
   never from the reply text — so this component only displays what it's
   given, after checking its shape:

     { title: string, url: string | null, rules: string[], document?: string }

   `title` is the set of rules or document the verified rules belong to;
   `document` (optional, newer responses) names the approved file they came
   from, shown only when it differs from the title. A source is a link only
   when the server supplied an https URL for it (KB_SOURCE_DISPLAY);
   otherwise it's a plain label. Rule numbers are shown only when the server
   verified them. Nothing here is inferred or invented.

   A web source (general legal answers, llm_service.generate_web_answer) is

     { kind: "web", index: number, title: string, url: string, domain: string }

   built by the server only from the search response's citation annotations;
   `index` is the "[n]" marker in the reply. It needs an https URL, and its
   domain is always read from that URL. Web and document sources are told
   apart by icon and label, never merged. */

const MAX_SOURCES = 10;
const MAX_TITLE_LENGTH = 200;
const RULE_REF_RE = /^\d{1,3}(?:\.\d{1,3})?(?:\([a-z]{1,4}\))?$/i;

function safeHttpsUrl(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

const MAX_CITE_INDEX = 99;

/* Well-formed web sources, one per index, sorted by index. Exported for tests. */
export function normalizeWebCitations(raw) {
  if (!Array.isArray(raw)) return [];
  const byIndex = new Map();
  for (const c of raw) {
    if (!c || typeof c !== "object" || c.kind !== "web") continue;
    const url = safeHttpsUrl(c.url);
    const { index } = c;
    if (!url || !Number.isInteger(index) || index < 1 || index > MAX_CITE_INDEX || byIndex.has(index)) continue;
    if (byIndex.size >= MAX_SOURCES) break;
    const domain = new URL(url).hostname;
    const title = typeof c.title === "string" ? c.title.trim().slice(0, MAX_TITLE_LENGTH) : "";
    byIndex.set(index, { index, url, domain, title: title || domain });
  }
  return [...byIndex.values()].sort((a, b) => a.index - b.index);
}

/* index -> source, for linking the "[n]" markers in the reply text. */
export function webCitationLinks(raw) {
  return new Map(normalizeWebCitations(raw).map((s) => [s.index, s]));
}

/* Document sources: drops anything that isn't a well-formed citation, merges
   duplicates by title, and caps the list. Exported for tests. */
export function normalizeCitations(raw) {
  if (!Array.isArray(raw)) return [];
  const byTitle = new Map();
  for (const c of raw) {
    if (!c || typeof c !== "object" || (c.kind !== undefined && c.kind !== "document")) continue;
    const title = typeof c.title === "string" ? c.title.trim().slice(0, MAX_TITLE_LENGTH) : "";
    if (!title) continue;
    // `rule_labels` cites the clause ("4(i)") when the answer did.
    const cited = Array.isArray(c.rule_labels) && c.rule_labels.length ? c.rule_labels : c.rules;
    const rules = Array.isArray(cited)
      ? cited.filter((r) => typeof r === "string" && RULE_REF_RE.test(r.trim())).map((r) => r.trim())
      : [];
    const existing = byTitle.get(title);
    if (existing) {
      for (const r of rules) if (!existing.rules.includes(r)) existing.rules.push(r);
      existing.url = existing.url || safeHttpsUrl(c.url);
      continue;
    }
    if (byTitle.size >= MAX_SOURCES) continue;
    const document = typeof c.document === "string" ? c.document.trim().slice(0, MAX_TITLE_LENGTH) : "";
    byTitle.set(title, {
      title,
      url: safeHttpsUrl(c.url),
      rules: [...new Set(rules)],
      document: document && document !== title ? document : null,
    });
  }
  return [...byTitle.values()];
}

/* Source number -> document source, for the chips in an answer card. Numbers
   match the list below: document sources follow any web ones. */
export function documentCitationLinks(raw) {
  const web = normalizeWebCitations(raw);
  const first = (web.length ? web[web.length - 1].index : 0) + 1;
  return new Map(normalizeCitations(raw).map((s, i) => [first + i, s]));
}

function ruleLabel(rules) {
  return `${rules.length > 1 ? "Rules" : "Rule"} ${rules.join(", ")}`;
}

function WebSource({ source }) {
  return (
    <li
      className="flex items-start gap-2.5 rounded-lg border border-border bg-white px-3 py-2"
      data-testid="instant-legal-help-web-source"
    >
      <span className="mt-0.5 inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-md bg-accent/10 px-1 text-2xs font-bold text-accent" aria-hidden="true">
        {source.index}
      </span>
      <div className="min-w-0 flex-1 text-sm leading-6">
        <div className="flex items-start gap-1.5 font-medium text-foreground [overflow-wrap:anywhere]">
          <Globe className="mt-1 h-3.5 w-3.5 shrink-0 text-accent" aria-hidden="true" />
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="underline decoration-accent/40 underline-offset-2 hover:text-accent hover:decoration-accent"
            data-testid="instant-legal-help-source-link"
          >
            <span className="sr-only">Source {source.index}: </span>
            {source.title}
            <ExternalLink className="ml-1 inline h-3 w-3 align-[-1px]" aria-hidden="true" />
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        </div>
        <div className="text-xs text-muted-foreground" data-testid="instant-legal-help-source-domain">
          Official website · <span className="font-medium text-foreground/80">{source.domain}</span>
        </div>
        <div className="truncate text-xs text-muted-foreground" title={source.url} data-testid="instant-legal-help-source-url">
          {source.url}
        </div>
      </div>
    </li>
  );
}

export default function ChatSources({ citations }) {
  const web = normalizeWebCitations(citations);
  const sources = normalizeCitations(citations);
  if (!sources.length && !web.length) return null;
  // Document sources are numbered after the web ones so no number means two things.
  const firstDocNumber = (web.length ? web[web.length - 1].index : 0) + 1;
  return (
    <section
      className="mt-4 border-t border-border pt-3"
      aria-label="Sources"
      data-testid="instant-legal-help-citations"
    >
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Sources</h4>
      <ol className="mt-2 space-y-2">
        {web.map((s) => <WebSource key={`web-${s.index}`} source={s} />)}
        {sources.map((s, i) => (
          <li
            key={`doc-${s.title}`}
            className="flex items-start gap-2.5 rounded-lg border border-border bg-white px-3 py-2"
            data-testid="instant-legal-help-source"
          >
            <span className="mt-0.5 inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-md bg-accent/10 px-1 text-2xs font-bold text-accent" aria-hidden="true">
              {firstDocNumber + i}
            </span>
            <div className="min-w-0 flex-1 text-sm leading-6">
              <div className="flex items-start gap-1.5 font-medium text-foreground [overflow-wrap:anywhere]">
                <BookOpen className="mt-1 h-3.5 w-3.5 shrink-0 text-accent" aria-hidden="true" />
                {s.url ? (
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline decoration-accent/40 underline-offset-2 hover:text-accent hover:decoration-accent"
                    data-testid="instant-legal-help-source-link"
                  >
                    {s.title}
                    <ExternalLink className="ml-1 inline h-3 w-3 align-[-1px]" aria-hidden="true" />
                    <span className="sr-only"> (opens in a new tab)</span>
                  </a>
                ) : (
                  <span>{s.title}</span>
                )}
              </div>
              {s.rules.length > 0 && (
                <div className="text-xs text-muted-foreground" data-testid="instant-legal-help-source-detail">
                  {ruleLabel(s.rules)}
                </div>
              )}
              {s.document && (
                <div className="text-xs text-muted-foreground [overflow-wrap:anywhere]" data-testid="instant-legal-help-source-document">
                  From: {s.document}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
