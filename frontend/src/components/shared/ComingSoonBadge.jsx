import React from "react";
import { cn } from "@/lib/utils";

/* Single shared "Coming Soon" badge used everywhere in the app — same
   color, angle, typography, padding, shadow, and border radius wherever it
   appears.
   - variant="corner" (default): the diagonal ribbon pinned to a card's
     top-right corner. Needs a `relative overflow-hidden` ancestor (see
     ServiceCard/FeaturedServiceCard/PricingPackageCard for the pattern).
   - variant="inline": the same visual styling, laid out in normal flow so
     it can sit next to text (footer list items, inline labels) where the
     corner ribbon's fixed-width absolute geometry wouldn't fit. */
export default function ComingSoonBadge({ variant = "corner", label = "Coming Soon", className }) {
  return (
    <span
      className={cn(
        "landing-coming-soon-badge",
        variant === "inline" && "landing-coming-soon-badge--inline",
        className
      )}
    >
      {label}
    </span>
  );
}
