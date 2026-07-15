import React from "react";
import { UtilityBar, LandingNav, LandingFooter } from "@/components/landing";

/**
 * Shared shell for marketing pages: UtilityBar + LandingNav + content + LandingFooter.
 * Replaces the identical `<div className="min-h-screen bg-background">` shell that
 * About/Contact/Pricing/Security/Trust/Landing each hand-rolled — see
 * PRODUCT_DESIGN_SYSTEM.md §3.2 and DESIGN_SYSTEM_AUDIT.md §1.
 *
 * `navProps` passes through to LandingNav (e.g. Landing.jsx's `onTakeTour`).
 */
export default function MarketingLayout({ navProps, children }) {
  return (
    <div className="min-h-screen bg-background">
      <UtilityBar />
      <LandingNav {...navProps} />
      {children}
      <LandingFooter />
    </div>
  );
}
