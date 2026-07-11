import React from "react";
import { Check, Minus } from "lucide-react";

/* Display labels are cosmetic groupings of the underlying feature strings —
   the checklist itself is still derived entirely from pkg.features, so it
   can never drift from the real package data. */
const LABEL_MAP = {
  "1 Print Set": "Print-Out",
  "2 Photocopy Sets": "Photocopy",
  "Filing Ready PDF on Email": "Email Delivery",
};
const CANONICAL_ORDER = ["Scanning", "OCR", "Bookmarking", "Print-Out", "Photocopy", "Email Delivery"];

function buildMatrix(packages) {
  const normalized = packages.map((pkg) => new Set(pkg.features.map((f) => LABEL_MAP[f] || f)));
  const union = new Set();
  normalized.forEach((set) => set.forEach((f) => union.add(f)));
  const orderedFeatures = [
    ...CANONICAL_ORDER.filter((f) => union.has(f)),
    ...[...union].filter((f) => !CANONICAL_ORDER.includes(f)),
  ];
  return orderedFeatures.map((feature) => ({
    feature,
    included: normalized.map((set) => set.has(feature)),
  }));
}

export default function PricingComparisonTable({ packages = [] }) {
  const rows = buildMatrix(packages);

  return (
    <div className="landing-comparison-wrap">
      <table className="w-full text-sm border-collapse min-w-[480px]">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground border-b border-slate-200">
            <th className="py-2.5 pr-3 font-semibold">Feature</th>
            {packages.map((pkg) => (
              <th key={pkg.slug} className="py-2.5 px-3 font-semibold text-center">{pkg.name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ feature, included }) => (
            <tr key={feature} className="border-b border-slate-100 last:border-0">
              <td className="py-3 pr-3 font-medium">{feature}</td>
              {included.map((yes, i) => (
                <td key={packages[i].slug} className="py-3 px-3 text-center">
                  {yes ? (
                    <Check className="w-4 h-4 text-emerald-500 inline-block" />
                  ) : (
                    <Minus className="w-4 h-4 text-slate-300 inline-block" />
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
