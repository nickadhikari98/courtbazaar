import React, { useRef, useState } from "react";
import { Check, ChevronDown, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatINR } from "@/lib/pricingData";
import PricingTierTable from "../PricingTierTable";

export default function PricingPackageCard({ pkg }) {
  const [open, setOpen] = useState(false);
  const detailsRef = useRef(null);

  const isPopular = pkg.badge === "popular";
  const isBestValue = pkg.badge === "best-value";
  const maxTierSavings = pkg.tiers[pkg.tiers.length - 1]?.savings;

  const handleChoosePlan = () => {
    setOpen(true);
    requestAnimationFrame(() => {
      detailsRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  };

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

      <h3 className="landing-pricing-name text-xl">{pkg.name}</h3>
      <p className="text-sm text-muted-foreground mt-1">{pkg.tagline}</p>

      <div className="mt-5">
        <span className="text-xs text-muted-foreground font-medium">Starting from</span>
        <div className="landing-pricing-hero-price">
          ₹{pkg.startingPrice}
          <span className="text-sm font-normal text-muted-foreground ml-1.5">{pkg.perPageRate}</span>
        </div>
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
        onClick={handleChoosePlan}
        className={cn(
          "landing-pricing-hero-cta mt-6",
          isPopular || isBestValue ? "bg-accent hover:bg-primary text-white" : "bg-primary hover:bg-accent text-white"
        )}
      >
        Choose This Plan <ArrowRight className="w-4 h-4" />
      </button>

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        data-open={open}
        className="landing-pricing-hero-expand-trigger justify-center"
      >
        View full page-wise pricing <ChevronDown className="w-4 h-4" />
      </button>

      <div
        ref={detailsRef}
        className="grid transition-all duration-300 ease-in-out"
        style={{ gridTemplateRows: open ? "1fr" : "0fr" }}
      >
        <div className="overflow-hidden">
          <div className="pt-4">
            <PricingTierTable pkg={pkg} variant="tableOnly" />
          </div>
        </div>
      </div>
    </div>
  );
}
