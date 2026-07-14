import React from "react";
import { Link } from "react-router-dom";
import { ChevronRight, Home } from "lucide-react";

/* Hand-built (not the shadcn primitive — ui/breadcrumb.jsx was removed
   earlier in this project). `items` is an ordered list of
   { label, href? } — the last item (current page) should omit `href`. */
export default function Breadcrumb({ items = [] }) {
  return (
    <nav aria-label="Breadcrumb" className="text-sm">
      <ol className="flex flex-wrap items-center gap-1.5 text-muted-foreground">
        <li className="flex items-center gap-1.5">
          <Link to="/" className="flex items-center gap-1 hover:text-foreground transition-colors" aria-label="Home">
            <Home className="w-3.5 h-3.5" />
          </Link>
        </li>
        {items.map((item, i) => (
          <li key={item.label} className="flex items-center gap-1.5">
            <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/50 flex-shrink-0" />
            {item.href && i < items.length - 1 ? (
              <Link to={item.href} className="hover:text-foreground transition-colors font-medium">
                {item.label}
              </Link>
            ) : (
              <span className="text-foreground font-semibold" aria-current="page">
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
