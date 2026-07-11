import React from "react";
import { Link, useLocation } from "react-router-dom";
import { Wallet } from "lucide-react";
import { UtilityBar, LandingNav, LandingFooter } from "@/components/landing";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { individualPricing, packages, addOnServices, formatINR } from "@/lib/pricingData";
import PricingServiceRow from "@/components/landing/pricing/PricingServiceRow";
import PackageSavingsBanner from "@/components/landing/pricing/PackageSavingsBanner";
import PricingPackageCard from "@/components/landing/pricing/PricingPackageCard";
import PricingComparisonTable from "@/components/landing/pricing/PricingComparisonTable";
import TrustIndicatorsStrip from "@/components/landing/pricing/TrustIndicatorsStrip";
import BulkPricingOffer from "@/components/landing/pricing/BulkPricingOffer";

export default function Pricing() {
  const location = useLocation();
  const activeSlug = location.hash ? location.hash.slice(1) : null;
  const activePackage = activeSlug ? packages.find((pkg) => pkg.slug === activeSlug) : null;

  return (
    <div className="min-h-screen bg-background">
      <UtilityBar />
      <LandingNav />

      {/* Header */}
      <section className="landing-section pb-0">
        <div className="landing-container">
          <div className="landing-section-header">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-accent/10 mb-4">
              <Wallet className="w-7 h-7 text-accent" strokeWidth={2} />
            </div>
            <h1 className="landing-section-title">Pricing & Packages</h1>
            <p className="landing-section-subtitle">
              Choose the option that best fits your litigation workflow. Whether you need a single service
              or complete filing support, CourtBazaar has a transparent pricing plan for you.
            </p>
          </div>

          {/* Individual Pricing */}
          <div className="max-w-3xl mx-auto">
            <h2 className="font-display font-bold text-lg mb-4">Individual Pricing</h2>
            <div className="grid sm:grid-cols-2 gap-3">
              {individualPricing.map((item) => (
                <PricingServiceRow key={item.label} {...item} />
              ))}
            </div>
          </div>

          {/* Package savings banner */}
          <div className="max-w-3xl mx-auto mt-14">
            <PackageSavingsBanner packages={packages} />
          </div>
        </div>
      </section>

      {/* Packages */}
      <section className="landing-section pt-14">
        <div className="landing-container max-w-5xl mx-auto">
          {activePackage ? (
            <>
              <div className="flex items-center justify-between mb-6">
                <p className="text-sm text-muted-foreground">
                  Showing <span className="font-semibold text-foreground">{activePackage.name}</span> package details
                </p>
                <Link to="/pricing" className="text-sm font-semibold text-primary hover:underline">
                  View all packages
                </Link>
              </div>
              <div className="max-w-md mx-auto">
                <PricingPackageCard pkg={activePackage} />
              </div>
            </>
          ) : (
            <Tabs defaultValue="packages">
              <div className="flex justify-center mb-9">
                <TabsList className="landing-pricing-toggle">
                  <TabsTrigger value="packages" className="landing-pricing-toggle-trigger">
                    View Packages
                  </TabsTrigger>
                  <TabsTrigger value="comparison" className="landing-pricing-toggle-trigger">
                    View Comparison
                  </TabsTrigger>
                </TabsList>
              </div>

              <TabsContent value="packages" className="mt-0">
                <div className="grid grid-cols-1 sm:grid-cols-3 items-stretch gap-6">
                  {packages.map((pkg) => (
                    <div key={pkg.slug} className="flex">
                      <PricingPackageCard pkg={pkg} />
                    </div>
                  ))}
                </div>
              </TabsContent>

              <TabsContent value="comparison" className="mt-0">
                <PricingComparisonTable packages={packages} />
              </TabsContent>
            </Tabs>
          )}
        </div>
      </section>

      {/* Add-on services */}
      <section className="landing-section bg-slate-50 pt-0">
        <div className="landing-container max-w-4xl mx-auto">
          <div className="bg-white border border-slate-200 rounded-2xl p-6 sm:p-8">
            <h2 className="font-display font-bold text-lg mb-1">Add-On Services</h2>
            <p className="text-sm text-muted-foreground mb-5">
              Add e-filing to any package only when you need it.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse min-w-[480px]">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground border-b border-slate-200">
                    <th className="py-2.5 pr-3 font-semibold">Service</th>
                    <th className="py-2.5 px-3 font-semibold">Individual Price</th>
                    <th className="py-2.5 px-3 font-semibold">Package Add-On Price</th>
                    <th className="py-2.5 pl-3 font-semibold">Savings</th>
                  </tr>
                </thead>
                <tbody>
                  {addOnServices.map((addOn) => (
                    <tr key={addOn.service} className="border-b border-slate-100 last:border-0">
                      <td className="py-2.5 pr-3 font-medium">{addOn.service}</td>
                      <td className="py-2.5 px-3 text-muted-foreground">{formatINR(addOn.individual)}</td>
                      <td className="py-2.5 px-3 font-bold">{formatINR(addOn.addOn)}</td>
                      <td className="py-2.5 pl-3 text-emerald-600 font-semibold">{formatINR(addOn.savings)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Trust indicators */}
          <div className="mt-10">
            <TrustIndicatorsStrip />
          </div>

          {/* Bulk pricing offer */}
          <div className="mt-10">
            <BulkPricingOffer />
          </div>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
