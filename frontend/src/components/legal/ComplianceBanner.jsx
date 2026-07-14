import React from "react";
import { ShieldCheck } from "lucide-react";

export default function ComplianceBanner() {
  return (
    <div className="legal-compliance-banner" role="note">
      <ShieldCheck className="w-4 h-4 flex-shrink-0" strokeWidth={2} />
      <p>
        These policies govern your use of CourtBazaar services. Please read them carefully before using the
        platform.
      </p>
    </div>
  );
}
