import React, { useRef, useEffect } from "react";
import { X } from "lucide-react";
import PricingTierGrid from "./PricingTierGrid";

/* Full-width panel rendered BELOW the package cards (not inside any one
   card) so expanding a package's page-wise pricing never stretches or
   misaligns the card grid — only one package's tiers show at a time. */
export default function PricingDetailsPanel({ pkg, onClose }) {
  const panelRef = useRef(null);

  useEffect(() => {
    if (pkg) {
      requestAnimationFrame(() => {
        panelRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    }
  }, [pkg]);

  return (
    <div
      className="grid transition-all duration-300 ease-in-out"
      style={{ gridTemplateRows: pkg ? "1fr" : "0fr" }}
    >
      <div className="overflow-hidden">
        {pkg && (
          <div ref={panelRef} className="landing-pricing-details-panel mt-8">
            <div className="flex items-center justify-between mb-6">
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-accent">Page-wise Pricing</p>
                <h3 className="font-display font-bold text-xl mt-0.5">{pkg.name}</h3>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="landing-pricing-details-close"
                aria-label="Close pricing details"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <PricingTierGrid pkg={pkg} />
          </div>
        )}
      </div>
    </div>
  );
}
