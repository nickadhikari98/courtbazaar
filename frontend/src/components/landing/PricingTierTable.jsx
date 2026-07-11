import React from "react";
import { toast } from "sonner";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatINR } from "@/lib/pricingData";

export default function PricingTierTable({ pkg, variant }) {
  const isFeatured = pkg.badge === "popular" || pkg.badge === "best-value";
  const tableOnly = variant === "tableOnly";

  const handleSelectTier = (tier) => {
    toast.info(
      `You selected the ${pkg.name} package (up to ${tier.pages} pages) — payment is coming soon. We'll notify you as soon as it's live.`
    );
  };

  const table = (
    <div className={cn("divide-y divide-slate-100", !tableOnly && "mt-7")}>
      {pkg.tiers.map((tier) => (
        <div key={tier.pages} className="flex items-center justify-between gap-3 py-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">Up to {tier.pages} pages</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              <span className="line-through mr-1.5">{formatINR(tier.individual)}</span>
              <span className="font-bold text-foreground">{formatINR(tier.package)}</span>
              <span className="text-emerald-600 font-semibold ml-1.5">
                Save {formatINR(tier.savings)} · {tier.discount}
              </span>
            </p>
          </div>
          <button
            type="button"
            onClick={() => handleSelectTier(tier)}
            className={cn(
              "flex-shrink-0 text-xs font-bold px-3 py-1.5 rounded-md transition-colors",
              isFeatured
                ? "bg-accent hover:bg-primary text-white"
                : "bg-primary hover:bg-accent text-white"
            )}
          >
            Select
          </button>
        </div>
      ))}
    </div>
  );

  if (tableOnly) return table;

  return (
    <div
      id={pkg.slug}
      className={cn(
        "landing-pricing-card scroll-mt-28",
        pkg.badge === "popular" && "landing-pricing-popular",
        pkg.badge === "best-value" && "landing-pricing-best-value"
      )}
    >
      {pkg.badge === "popular" && <div className="landing-pricing-badge">Most Popular</div>}
      {pkg.badge === "best-value" && <div className="landing-pricing-badge landing-pricing-badge--dark">Best Value</div>}

      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-6">
        <div>
          <h3 className="landing-pricing-name text-2xl">{pkg.name}</h3>
          <p className="text-sm text-muted-foreground mt-1">{pkg.tagline}</p>
          <p className="text-xs text-muted-foreground mt-2">
            Individual Price: <span className="font-semibold text-foreground">{pkg.perPageRate}</span>
          </p>
          <div className="landing-pricing-savings mt-1">Save up to {pkg.savings}</div>

          <ul className="mt-4 space-y-1">
            {pkg.features.map((feature, i) => (
              <li key={i} className="landing-pricing-feature">
                <Check className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                <span>{feature}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {table}
    </div>
  );
}
