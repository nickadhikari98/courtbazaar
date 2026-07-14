import React from "react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { formatINR } from "@/lib/pricingData";

/* Page-wise tier pricing, laid out as a responsive grid of compact cards
   instead of a single tall vertical list — lets a 10-tier package use the
   full available width instead of stretching one column. */
export default function PricingTierGrid({ pkg }) {
  const isFeatured = pkg.badge === "popular" || pkg.badge === "best-value";

  const handleSelectTier = (tier) => {
    toast.success(
      `You selected the ${pkg.name} package (up to ${tier.pages} pages) — payment is coming soon. We'll notify you as soon as it's live.`
    );
  };

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {pkg.tiers.map((tier) => (
        <div key={tier.pages} className="landing-pricing-tier-card">
          <p className="landing-pricing-tier-pages">Up to {tier.pages} pages</p>
          <div className="landing-pricing-tier-price-row">
            <span className="landing-pricing-tier-price">{formatINR(tier.package)}</span>
            <span className="landing-pricing-tier-price-strike">{formatINR(tier.individual)}</span>
          </div>
          <p className="landing-pricing-tier-savings">
            Save {formatINR(tier.savings)} · {tier.discount}
          </p>
          <button
            type="button"
            onClick={() => handleSelectTier(tier)}
            className={cn(
              "landing-pricing-tier-select",
              isFeatured ? "bg-accent hover:bg-primary text-white" : "bg-primary hover:bg-accent text-white"
            )}
          >
            Select
          </button>
        </div>
      ))}
    </div>
  );
}
