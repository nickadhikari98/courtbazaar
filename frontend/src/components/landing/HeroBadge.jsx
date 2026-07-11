import React from "react";
import { Sparkles } from "lucide-react";

export default function HeroBadge({ icon: Icon = Sparkles, children }) {
  return (
    <div className="landing-hero-badge">
      <span className="landing-hero-badge-accent" />
      <Icon className="w-3.5 h-3.5 text-accent flex-shrink-0" strokeWidth={2.25} />
      <span>{children}</span>
    </div>
  );
}
