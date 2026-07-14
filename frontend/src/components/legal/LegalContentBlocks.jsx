import React from "react";
import { AlertTriangle, Info, TriangleAlert } from "lucide-react";

const calloutStyles = {
  info: { icon: Info, className: "legal-callout legal-callout--info" },
  warning: { icon: TriangleAlert, className: "legal-callout legal-callout--warning" },
  notice: { icon: AlertTriangle, className: "legal-callout legal-callout--notice" },
};

/* Highlights every case-insensitive occurrence of `query` inside `text`. */
function HighlightedText({ text, query }) {
  if (!query) return text;
  const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"));
  return parts.map((part, i) =>
    part.toLowerCase() === query.toLowerCase() ? (
      <mark key={i} className="legal-highlight">
        {part}
      </mark>
    ) : (
      part
    )
  );
}

function Block({ block, query }) {
  switch (block.type) {
    case "p":
      return (
        <p className="legal-block-p">
          <HighlightedText text={block.text} query={query} />
        </p>
      );
    case "list":
      return (
        <ul className="legal-block-list">
          {block.items.map((item, i) => (
            <li key={i}>
              <HighlightedText text={item} query={query} />
            </li>
          ))}
        </ul>
      );
    case "definition":
      return (
        <div className="legal-definition">
          <dt>{block.term}</dt>
          <dd>
            <HighlightedText text={block.text} query={query} />
          </dd>
        </div>
      );
    case "callout": {
      const { icon: Icon, className } = calloutStyles[block.variant] || calloutStyles.info;
      return (
        <div className={className} role="note">
          <Icon className="w-4 h-4 flex-shrink-0 mt-0.5" strokeWidth={2} />
          <p>
            <HighlightedText text={block.text} query={query} />
          </p>
        </div>
      );
    }
    default:
      return null;
  }
}

export default function LegalContentBlocks({ blocks = [], query }) {
  return (
    <div className="space-y-3">
      {blocks.map((block, i) => (
        <Block key={i} block={block} query={query} />
      ))}
    </div>
  );
}
