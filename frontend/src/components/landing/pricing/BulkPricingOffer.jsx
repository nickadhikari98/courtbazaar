import React from "react";
import { MessageCircle } from "lucide-react";

/* Shared bulk-pricing offer card — used on both the /pricing page and the
   homepage pricing teaser, so both surfaces stay visually part of one design
   system. Copy is prop-driven; the WhatsApp destination/prefilled text is
   fixed (same link everywhere), not something either caller should change. */
export default function BulkPricingOffer({
  title = "Need Bulk Printing?",
  subtitle = "Get special pricing for Law Firms, Chambers and Litigation Teams — volume discounts available for more than 1000 pages.",
  ctaText = "Get Instant Quote on WhatsApp",
}) {
  return (
    <div className="landing-bulk-offer">
      <MessageCircle className="w-10 h-10 text-white mx-auto relative" strokeWidth={1.75} />
      <h2 className="landing-bulk-offer-title mt-3">{title}</h2>
      <p className="landing-bulk-offer-subtitle">{subtitle}</p>
      <a
        href="https://wa.me/919876543210?text=Hi%2C%20I%27d%20like%20a%20bulk%20pricing%20quote%20for%20CourtBazaar%20services."
        target="_blank"
        rel="noopener noreferrer"
        className="landing-bulk-offer-cta"
      >
        <MessageCircle className="w-4 h-4" />
        {ctaText}
      </a>
    </div>
  );
}
