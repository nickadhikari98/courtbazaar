import React from "react";
import { FileCheck2, ShieldCheck, Zap, Users } from "lucide-react";

const items = [
  { icon: FileCheck2, label: "GST Invoice Available" },
  { icon: ShieldCheck, label: "Secure Payments" },
  { icon: Zap, label: "Fast Delivery" },
  { icon: Users, label: "Trusted by Delhi Advocates" },
];

export default function TrustIndicatorsStrip() {
  return (
    <div className="landing-trust-strip">
      {items.map(({ icon: Icon, label }) => (
        <div key={label} className="landing-trust-strip-item">
          <Icon className="w-5 h-5" strokeWidth={2} />
          <span className="landing-trust-strip-label">{label}</span>
        </div>
      ))}
    </div>
  );
}
