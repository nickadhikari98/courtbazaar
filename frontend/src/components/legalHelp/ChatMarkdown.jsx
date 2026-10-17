import React from "react";

/* Renders the small Markdown subset Instant Legal Help's document answers use
   (see ai_chat._sanitize_markdown_reply): "## " / "### " headings, "- " / "•"
   bullets, "1. " numbered lists, **bold**, and blank-line paragraphs. Plain
   replies (general questions, fallbacks) render as ordinary paragraphs.

   Builds React elements only — never dangerouslySetInnerHTML — so nothing in
   a reply can become markup, links or script. Anything that isn't one of the
   patterns above is shown as literal text. */

const HEADING_RE = /^(#{2,3})\s+(.+)$/;
const BULLET_RE = /^\s*[-•*]\s+(.+)$/;
const NUMBERED_RE = /^\s*(\d{1,3})[.)]\s+(.+)$/;

function renderInline(text, keyPrefix) {
  // **bold** only; unmatched asterisks stay as text.
  const parts = String(text).split(/(\*\*[^*\n]+?\*\*)/g);
  return parts.map((part, i) => (
    part.startsWith("**") && part.endsWith("**") && part.length > 4
      ? <strong key={`${keyPrefix}-${i}`} className="font-semibold text-foreground">{part.slice(2, -2)}</strong>
      : <React.Fragment key={`${keyPrefix}-${i}`}>{part}</React.Fragment>
  ));
}

/* Groups lines into blocks: heading | list (ul/ol) | paragraph. A blank line
   ends a paragraph or list. Exported for tests. */
export function parseBlocks(text) {
  const blocks = [];
  let para = null;
  let list = null;
  const flush = () => {
    if (para) blocks.push(para);
    if (list) blocks.push(list);
    para = null;
    list = null;
  };
  for (const raw of String(text || "").split("\n")) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) { flush(); continue; }
    const heading = line.match(HEADING_RE);
    if (heading) {
      flush();
      blocks.push({ type: "heading", level: heading[1].length, text: heading[2] });
      continue;
    }
    const bullet = line.match(BULLET_RE);
    const numbered = !bullet && line.match(NUMBERED_RE);
    if (bullet || numbered) {
      const type = bullet ? "ul" : "ol";
      if (para) { blocks.push(para); para = null; }
      if (!list || list.type !== type) {
        if (list) blocks.push(list);
        list = { type, start: numbered ? Number(numbered[1]) : 1, items: [] };
      }
      list.items.push(bullet ? bullet[1] : numbered[2]);
      continue;
    }
    if (list) { blocks.push(list); list = null; }
    if (!para) para = { type: "p", lines: [] };
    para.lines.push(line.trim());
  }
  flush();
  return blocks;
}

export default function ChatMarkdown({ text }) {
  const blocks = parseBlocks(text);
  return (
    <div className="space-y-3 text-[15px] leading-7 text-foreground break-words" data-testid="chat-markdown">
      {blocks.map((block, i) => {
        const key = `b${i}`;
        if (block.type === "heading") {
          return block.level === 2
            ? <h3 key={key} className="font-display font-bold text-base leading-snug pt-2 first:pt-0">{renderInline(block.text, key)}</h3>
            : <h4 key={key} className="font-semibold text-[15px] leading-snug pt-1">{renderInline(block.text, key)}</h4>;
        }
        if (block.type === "ul" || block.type === "ol") {
          const ListTag = block.type;
          return (
            <ListTag
              key={key}
              start={block.type === "ol" && block.start !== 1 ? block.start : undefined}
              className={`${block.type === "ul" ? "list-disc" : "list-decimal"} pl-5 space-y-1.5 marker:text-muted-foreground`}
            >
              {block.items.map((item, j) => <li key={`${key}-${j}`} className="pl-1">{renderInline(item, `${key}-${j}`)}</li>)}
            </ListTag>
          );
        }
        return (
          <p key={key}>
            {block.lines.map((line, j) => (
              <React.Fragment key={`${key}-${j}`}>
                {j > 0 && <br />}
                {renderInline(line, `${key}-${j}`)}
              </React.Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}
