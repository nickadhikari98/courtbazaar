import React from "react";
import { ArrowRight } from "lucide-react";
import ComingSoonBadge from "@/components/shared/ComingSoonBadge";

const colorMap = {
  amber: { bg: "bg-amber-50" },
  blue: { bg: "bg-blue-50" },
  emerald: { bg: "bg-emerald-50" },
  purple: { bg: "bg-purple-50" },
  rose: { bg: "bg-rose-50" },
  cyan: { bg: "bg-cyan-50" },
  orange: { bg: "bg-orange-50" },
};

export default function ServiceCard({ icon: Icon, name, description, color = "amber", cta = "Order Now", startingPrice }) {
  const colors = colorMap[color] || colorMap.amber;

  return (
    <div className="landing-service-card group">
      <ComingSoonBadge />
      <div className={`landing-service-icon ${colors.bg}`}>
        <Icon className="w-16 h-16" />
      </div>
      <h3 className="landing-service-title">{name}</h3>
      {startingPrice && (
        <div className="landing-service-price">
          <span className="landing-service-price-dot" />
          {startingPrice}
        </div>
      )}
      <p className="landing-service-desc">{description}</p>
      <div className="landing-service-cta">
        {cta}
        <ArrowRight className="inline w-4 h-4 ml-1 transition-transform duration-300 group-hover:translate-x-1" />
      </div>
    </div>
  );
}
