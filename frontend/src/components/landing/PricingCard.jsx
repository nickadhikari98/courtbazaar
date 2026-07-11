import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export default function PricingCard({
  slug,
  name,
  tagline,
  perPageRate,
  startingPrice,
  savings,
  features = [],
  cta = "View Package Details",
  badge, // "popular" | "best-value" | undefined
}) {
  const isFeatured = badge === "popular" || badge === "best-value";
  const detailsLink = `/pricing#${slug}`;

  return (
    <div
      className={cn(
        "landing-pricing-card",
        badge === "popular" && "landing-pricing-popular",
        badge === "best-value" && "landing-pricing-best-value"
      )}
    >
      {badge === "popular" && <div className="landing-pricing-badge">Most Popular</div>}
      {badge === "best-value" && <div className="landing-pricing-badge landing-pricing-badge--dark">Best Value</div>}

      <h3 className="landing-pricing-name">{name}</h3>
      {tagline && <p className="text-sm text-muted-foreground mt-1">{tagline}</p>}

      <div className="mt-5">
        <span className="text-xs text-muted-foreground font-medium">Starting from</span>
        <div>
          <span className="landing-pricing-price">₹{startingPrice}</span>
          {perPageRate && <span className="landing-pricing-period"> · {perPageRate}</span>}
        </div>
        {savings && (
          <div className="landing-pricing-savings">Save up to {savings}</div>
        )}
      </div>

      <ul className="mt-6 space-y-1 flex-1">
        {features.map((feature, i) => (
          <li key={i} className="landing-pricing-feature">
            <Check className="w-4 h-4 text-emerald-500 flex-shrink-0" />
            <span>{feature}</span>
          </li>
        ))}
      </ul>

      <div className="mt-6 space-y-2.5">
        <Link to={detailsLink}>
          <Button
            className={cn(
              "w-full font-bold h-11 rounded-lg transition-colors",
              isFeatured
                ? "bg-accent hover:bg-primary text-white"
                : "bg-primary hover:bg-accent text-white"
            )}
          >
            Choose Plan
          </Button>
        </Link>
        <Link
          to={detailsLink}
          className="block w-full text-center text-sm font-semibold text-muted-foreground hover:text-primary transition-colors py-1"
        >
          {cta}
        </Link>
      </div>
    </div>
  );
}
