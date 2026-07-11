import React from "react";
import { Landmark } from "lucide-react";
import {
  PrintOutIcon, PhotocopyIcon, ScanningIcon, OcrBookmarkIcon, EFilingDistrictIcon, EFilingHighIcon,
} from "@/components/landing";

const iconByKey = {
  print: PrintOutIcon,
  photocopy: PhotocopyIcon,
  scan: ScanningIcon,
  ocr: OcrBookmarkIcon,
  "efiling-district": EFilingDistrictIcon,
  "efiling-high": EFilingHighIcon,
  "efiling-supreme": Landmark,
};

export default function PricingServiceRow({ label, price, description, icon }) {
  const Icon = iconByKey[icon] || Landmark;
  return (
    <div className="landing-service-row">
      <div className="landing-service-row-icon">
        <Icon className="w-7 h-7" strokeWidth={1.5} />
      </div>
      <div className="min-w-0">
        <p className="landing-service-row-name">{label}</p>
        {description && <p className="landing-service-row-desc">{description}</p>}
      </div>
      <span className="landing-service-row-price">{price}</span>
    </div>
  );
}
