import React from "react";
import { Check, ChevronDown, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatINR } from "@/lib/pricingData";
import ComingSoonBadge from "@/components/shared/ComingSoonBadge";

export default function PricingPackageCard({ pkg, isExpanded, onToggleDetails }) {
  const isPopular = pkg.badge === "popular";
  const isBestValue = pkg.badge === "best-value";
  const maxTierSavings = pkg.tiers[pkg.tiers.length - 1]?.savings;

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
          isPopular || isBestValue ? "bg-accent hover:bg-primary text-white" : "bg-primary hover:bg-accent text-white"
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
