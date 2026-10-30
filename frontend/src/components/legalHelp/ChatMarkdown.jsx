import React from "react";

/* Renders the small Markdown subset Instant Legal Help's document answers use
   (see ai_chat._sanitize_markdown_reply): "## " / "### " headings, "- " / "•"
   bullets, "1. " numbered lists (one level of indented sub-items), "---"
   dividers, **bold**, and blank-line paragraphs. Plain replies (general
   questions, fallbacks) render as ordinary paragraphs.

   Builds React elements only — never dangerouslySetInnerHTML — so nothing in
   a reply can become markup, links or script. Anything that isn't one of the
   patterns above is shown as literal text. Links in model text stay text on
   purpose: the server strips Markdown links, and a URL the model wrote is not
   an approved source (approved ones arrive separately as citations).

   The one exception is a "[n]" marker for a verified web source: when
   `citeLinks` (from ChatSources' webCitationLinks) has an entry for n, the
   marker becomes a link to that source's URL; otherwise it stays text. */

const HEADING_RE = /^(#{2,3})\s+(.+)$/;
const BULLET_RE = /^(\s*)[-•*]\s+(.+)$/;
const NUMBERED_RE = /^(\s*)(\d{1,3})[.)]\s+(.+)$/;
const DIVIDER_RE = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/;
// Text with nothing to read: only section numbers, punctuation or bold markers ("6.", "-", "**").
const NO_CONTENT_RE = /^[\s\d.)(*:;,_\-–—•]*$/;

/* Never show structure without content: a heading that is only a number,
   a heading with nothing under it before the next heading of the same or a
   higher level (or the end), an empty list item, or a divider at the start,
   the end or next to another divider. The server removes these already
   (answer_guard._rebuild); this keeps a stale or unexpected reply from
   showing them. */
function dropEmptyStructure(blocks) {
  const kept = [];
  blocks.forEach((block) => {
    if (block.type === "heading" && NO_CONTENT_RE.test(block.text)) return;
    if (block.type === "ul" || block.type === "ol") {
      const keepIdx = block.items.map((_, j) => j).filter((j) => !NO_CONTENT_RE.test(block.items[j]));
      if (!keepIdx.length) return;
      if (keepIdx.length !== block.items.length) {
        const next = { type: block.type, start: block.start, items: keepIdx.map((j) => block.items[j]) };
        if (block.children) {
          const children = {};
          keepIdx.forEach((j, k) => { if (block.children[j]) children[k] = block.children[j]; });
          if (Object.keys(children).length) next.children = children;
        }
        kept.push(next);
        return;
      }
    }
    kept.push(block);
  });
  const withContent = kept.filter((block, i) => {
    if (block.type !== "heading") return true;
    const next = kept.slice(i + 1).find((b) => b.type !== "hr");
    return Boolean(next) && !(next.type === "heading" && next.level <= block.level);
  });
  const out = [];
  withContent.forEach((block) => {
    if (block.type === "hr" && (!out.length || out[out.length - 1].type === "hr")) return;
    out.push(block);
  });
  while (out.length && out[out.length - 1].type === "hr") out.pop();
  return out;
}

function renderCiteMarkers(text, keyPrefix, citeLinks) {
  if (!citeLinks?.size) return text;
  return String(text).split(/(\[\d{1,2}\])/g).map((part, i) => {
    const source = /^\[\d{1,2}\]$/.test(part) && citeLinks.get(Number(part.slice(1, -1)));
    if (!source) return <React.Fragment key={`${keyPrefix}-c${i}`}>{part}</React.Fragment>;
    const n = part.slice(1, -1);
    // A document with no approved link (url: null) still gets its chip.
    if (!source.url) {
      return (
        <span
          key={`${keyPrefix}-c${i}`}
          title={source.title}
          aria-label={`Source ${n}: ${source.title}`}
          className="mx-0.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-md bg-accent/10 px-1 align-[2px] text-[11px] font-semibold leading-none text-accent"
          data-testid="instant-legal-help-cite"
        >
          {n}
        </span>
      );
    }
    return (
      <a
        key={`${keyPrefix}-c${i}`}
        href={source.url}
        target="_blank"
        rel="noopener noreferrer"
        title={source.title}
        aria-label={`Source ${n}: ${source.title} (opens in a new tab)`}
        className="mx-0.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-md bg-accent/10 px-1 align-[2px] text-[11px] font-semibold leading-none text-accent no-underline hover:bg-accent hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
        data-testid="instant-legal-help-cite"
      >
        {n}
      </a>
    );
  });
}

function renderInline(text, keyPrefix, citeLinks) {
  // **bold** only; unmatched asterisks stay as text.
  const parts = String(text).split(/(\*\*[^*\n]+?\*\*)/g);
  return parts.map((part, i) => (
    part.startsWith("**") && part.endsWith("**") && part.length > 4
      ? <strong key={`${keyPrefix}-${i}`} className="font-semibold text-foreground">{part.slice(2, -2)}</strong>
      : <React.Fragment key={`${keyPrefix}-${i}`}>{renderCiteMarkers(part, `${keyPrefix}-${i}`, citeLinks)}</React.Fragment>
  ));
}

/* Groups lines into blocks: heading | list (ul/ol) | divider | paragraph. A
   blank line ends a paragraph or list. A list line indented further than its
   list's first item becomes a sub-item of the item above
   (list.children[index]); `children` is only present on lists that have any.
   Any extra indent counts, because both ai_chat._sanitize_reply and
   cleanAssistantText collapse runs of spaces, so "  - a" arrives as " - a".
   Exported for tests. */
export function parseBlocks(text) {
  const blocks = [];
  let para = null;
  let list = null;
  let listIndent = 0;
  const flush = () => {
    if (para) blocks.push(para);
    if (list) blocks.push(list);
    para = null;
    list = null;
  };
  for (const raw of String(text || "").split("\n")) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) { flush(); continue; }
    if (DIVIDER_RE.test(line)) {
      flush();
      blocks.push({ type: "hr" });
      continue;
    }
    const heading = line.match(HEADING_RE);
    if (heading) {
      flush();
      blocks.push({ type: "heading", level: heading[1].length, text: heading[2] });
      continue;
    }
    const bullet = line.match(BULLET_RE);
    const numbered = !bullet && line.match(NUMBERED_RE);
    if (bullet || numbered) {
      const indent = (bullet ? bullet[1] : numbered[1]).replace(/\t/g, "  ").length;
      const itemText = bullet ? bullet[2] : numbered[3];
      if (list && indent > listIndent && list.items.length) {
        const parent = list.items.length - 1;
        list.children = list.children || {};
        (list.children[parent] = list.children[parent] || []).push(itemText);
        continue;
      }
      const type = bullet ? "ul" : "ol";
      if (para) { blocks.push(para); para = null; }
      if (!list || list.type !== type) {
        if (list) blocks.push(list);
        list = { type, start: numbered ? Number(numbered[2]) : 1, items: [] };
        listIndent = indent;
      }
      list.items.push(itemText);
      continue;
    }
    if (list) { blocks.push(list); list = null; }
    if (!para) para = { type: "p", lines: [] };
    para.lines.push(line.trim());
  }
  flush();
  return blocks;
}

function ListBlock({ block, blockKey, citeLinks }) {
  const ListTag = block.type;
  return (
    <ListTag
      start={block.type === "ol" && block.start !== 1 ? block.start : undefined}
      className={`${block.type === "ul" ? "list-disc" : "list-decimal marker:font-semibold marker:text-accent"} pl-6 space-y-2 marker:text-muted-foreground`}
    >
      {block.items.map((item, j) => (
        <li key={`${blockKey}-${j}`} className="pl-1">
          {renderInline(item, `${blockKey}-${j}`, citeLinks)}
          {block.children?.[j] && (
            <ul className="list-[circle] pl-5 mt-1.5 space-y-1 marker:text-muted-foreground">
              {block.children[j].map((sub, k) => (
                <li key={`${blockKey}-${j}-${k}`} className="pl-1">{renderInline(sub, `${blockKey}-${j}-${k}`, citeLinks)}</li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ListTag>
  );
}

export default function ChatMarkdown({ text, citeLinks }) {
  const blocks = dropEmptyStructure(parseBlocks(text));
  return (
    <div
      className="space-y-3 text-[15px] leading-7 text-foreground break-words [overflow-wrap:anywhere]"
      data-testid="chat-markdown"
    >
      {blocks.map((block, i) => {
        const key = `b${i}`;
        if (block.type === "hr") {
          return <hr key={key} className="border-border my-4" />;
        }
        if (block.type === "heading") {
          // A top-level heading after other content starts a new section:
          // a hairline above it separates the sections of a long answer.
          return block.level === 2
            ? (
              <h3
                key={key}
                className={`font-display font-bold text-base sm:text-[17px] leading-snug ${i > 0 ? "border-t border-border pt-4 mt-5" : ""}`}
              >
                {renderInline(block.text, key, citeLinks)}
              </h3>
            )
            : <h4 key={key} className="font-semibold text-[15px] leading-snug pt-1">{renderInline(block.text, key, citeLinks)}</h4>;
        }
        if (block.type === "ul" || block.type === "ol") {
          return <ListBlock key={key} block={block} blockKey={key} citeLinks={citeLinks} />;
        }
        return (
          <p key={key}>
            {block.lines.map((line, j) => (
              <React.Fragment key={`${key}-${j}`}>
                {j > 0 && <br />}
                {renderInline(line, `${key}-${j}`, citeLinks)}
              </React.Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}
