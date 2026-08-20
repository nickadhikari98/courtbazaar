import React from "react";
import PageContainer from "@/components/layout/PageContainer";
import PricingCard from "@/components/landing/PricingCard";
import BulkPricingOffer from "@/components/landing/pricing/BulkPricingOffer";
import { packages } from "@/lib/pricingData";

/* "Packages" in the workspace — now renders the exact same Basic/Standard/
   Premium package cards as the landing page pricing section (@/lib/pricingData
   via the shared PricingCard), instead of the deprecated monthly
   free/advocate_pro/law_firm/enterprise subscription tiers the backend's
   /subscriptions/plans endpoint returned. One source of truth for what a
   package is, so the workspace can't drift from what visitors see on the
   landing page. "Choose Plan" links to /pricing#slug for full page-wise
   pricing, same as the landing teaser cards. */
export default function Subscription() {
  return (
    <PageContainer className="max-w-6xl">
      <div className="cb-overline text-accent">Plans &amp; packages</div>
      <h1 className="font-display font-black text-3xl lg:text-4xl tracking-tighter mt-1">Choose a plan that suits you</h1>
      <p className="text-muted-foreground font-medium mt-2">
        Flexible packages for individuals, advocates, law firms and litigation teams.
      </p>

      <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-6 items-stretch">
        {packages.map((pkg) => (
          <div key={pkg.slug} className="h-full grid">
            <PricingCard pkg={pkg} variant="teaser" />
          </div>
        ))}
      </div>

      <div className="mt-8">
        <BulkPricingOffer
          title="More than 1000 pages?"
          subtitle="Get special bulk pricing for law firms, senior advocates, chambers and litigation teams."
        />
      </div>
    </PageContainer>
  );
}
