import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Check, ChevronDown, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatINR } from "@/lib/pricingData";
import ComingSoonBadge from "@/components/shared/ComingSoonBadge";

/**
 * Pricing package card. Two variants sharing one implementation instead of
 * two independently-coded components (see DESIGN_SYSTEM_AUDIT.md §2.F):
 *  - "teaser" (default): homepage grid — links out to /pricing#slug for detail.
 *  - "full": /pricing page — expand/collapse toggle for page-wise pricing,
 *    plus the ComingSoonBadge ribbon and tier-savings chip only used there.
 *
 * `isExpanded`/`onToggleDetails` only apply to variant="full" — they're unused
 * in "teaser" mode, so omit them there.
 */
export default function PricingCard({ pkg, variant = "teaser", isExpanded, onToggleDetails }) {
  const isPopular = pkg.badge === "popular";
  const isBestValue = pkg.badge === "best-value";
  const isFeatured = isPopular || isBestValue;
  const detailsLink = `/pricing#${pkg.slug}`;

  if (variant === "full") {
    const maxTierSavings = pkg.tiers?.[pkg.tiers.length - 1]?.savings;
    return (
      <div
        id={pkg.slug}
        className={cn(
          "landing-pricing-hero-card scroll-mt-28",
          isPopular && "landing-pricing-hero-popular",
          isBestValue && "landing-pricing-hero-best-value"
        )}
      >
        {isPopular && (
          <div className="landing-pricing-hero-badge landing-pricing-hero-badge--popular">⭐ Most Popular</div>
        )}
        {isBestValue && (
          <div className="landing-pricing-hero-badge landing-pricing-hero-badge--best-value">🏆 Best Value</div>
        )}
        <div className="landing-pricing-hero-ribbon-clip">
          <ComingSoonBadge />
        </div>

        <h3 className="landing-pricing-name text-xl">{pkg.name}</h3>
        <p className="text-sm text-muted-foreground mt-1">{pkg.tagline}</p>

        <div className="mt-5">
          <span className="text-xs text-muted-foreground font-medium">Starting from</span>
          <div className="landing-pricing-hero-price">₹{pkg.startingPrice}</div>
          <span className="landing-pricing-hero-rate-pill">{pkg.perPageRate}</span>
        </div>

        <div className="landing-pricing-hero-savings-row">
          {maxTierSavings !== undefined && (
            <span className="landing-pricing-hero-savings-chip">Save up to {formatINR(maxTierSavings)}</span>
          )}
          <span className="landing-pricing-hero-savings-chip landing-pricing-hero-savings-chip--pct">
            {pkg.savings} off
          </span>
        </div>

        <div className="mt-6 flex-1">
          <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-2.5">What's Included</p>
          <ul className="space-y-1.5">
            {pkg.features.map((feature, i) => (
              <li key={i} className="landing-pricing-feature">
                <Check className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                <span>{feature}</span>
              </li>
            ))}
          </ul>
        </div>

        <button
          type="button"
          onClick={() => onToggleDetails(pkg.slug)}
          className={cn(
            "landing-pricing-hero-cta mt-6",
            isFeatured ? "bg-accent hover:bg-primary text-white" : "bg-primary hover:bg-accent text-white"
          )}
        >
          Choose This Plan <ArrowRight className="w-4 h-4" />
        </button>

        <button
          type="button"
          onClick={() => onToggleDetails(pkg.slug)}
          data-open={isExpanded}
          className="landing-pricing-hero-expand-trigger justify-center"
        >
          View full page-wise pricing <ChevronDown className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "landing-pricing-card",
        isPopular && "landing-pricing-popular",
        isBestValue && "landing-pricing-best-value"
      )}
    >
      {isPopular && <div className="landing-pricing-badge">Most Popular</div>}
      {isBestValue && <div className="landing-pricing-badge landing-pricing-badge--dark">Best Value</div>}

      <h3 className="landing-pricing-name">{pkg.name}</h3>
      {pkg.tagline && <p className="text-sm text-muted-foreground mt-1">{pkg.tagline}</p>}

      <div className="mt-5">
        <span className="text-xs text-muted-foreground font-medium">Starting from</span>
        <div>
          <span className="landing-pricing-price">₹{pkg.startingPrice}</span>
          {pkg.perPageRate && <span className="landing-pricing-period"> · {pkg.perPageRate}</span>}
        </div>
        {pkg.savings && <div className="landing-pricing-savings">Save up to {pkg.savings}</div>}
      </div>

      <ul className="mt-6 space-y-1 flex-1">
        {pkg.features.map((feature, i) => (
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
              isFeatured ? "bg-accent hover:bg-primary text-white" : "bg-primary hover:bg-accent text-white"
            )}
          >
            Choose Plan
          </Button>
        </Link>
        <Link
          to={detailsLink}
          className="block w-full text-center text-sm font-semibold text-muted-foreground hover:text-primary transition-colors py-1"
        >
          View Package Details
        </Link>
      </div>
    </div>
  );
}
