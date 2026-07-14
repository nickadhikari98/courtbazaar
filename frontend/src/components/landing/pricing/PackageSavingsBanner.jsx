import React from "react";
import { Wallet, Tag, ShieldCheck, Zap, Scale } from "lucide-react";

export default function PackageSavingsBanner({ packages = [], activePackage = null }) {
  const maxSavingsPct = Math.max(...packages.map((p) => parseInt(p.savings, 10) || 0));
  const lowestStartingPrice = Math.min(...packages.map((p) => parseInt(p.startingPrice, 10) || 0));

  // When the user arrived via a specific package's link (e.g. /pricing#standard),
  // show that package's own figures here instead of the cross-package aggregate —
  // otherwise the banner above a single-package view would cite a different
  // package's price than the one actually being shown below it.
  const savingsPctText = activePackage ? parseInt(activePackage.savings, 10) || maxSavingsPct : maxSavingsPct;
  const startingPriceText = activePackage ? parseInt(activePackage.startingPrice, 10) || lowestStartingPrice : lowestStartingPrice;

  const benefits = [
    { icon: Wallet, text: `Save up to ${savingsPctText}%` },
    { icon: Tag, text: `Starting from ₹${startingPriceText}` },
    { icon: ShieldCheck, text: "No hidden charges" },
    { icon: Zap, text: "Faster turnaround" },
    { icon: Scale, text: "Built for Advocates & Law Firms" },
  ];

  return (
    <div className="landing-savings-banner">
      <h2 className="font-display font-bold text-xl sm:text-2xl">Save up to {maxSavingsPct}% with Packages</h2>
      <p className="text-sm text-muted-foreground mt-2 max-w-xl mx-auto">
        Buying services separately costs more. Packages are specially designed for advocates and law firms.
      </p>
      <div className="landing-savings-banner-items">
        {benefits.map(({ icon: Icon, text }) => (
          <div key={text} className="landing-savings-banner-item">
            <Icon className="w-4 h-4" strokeWidth={2} />
            <span>{text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
