import React from "react";

export default function TrustBadge({ icon: Icon, label, description }) {
  return (
    <div className="landing-trust-badge">
      <Icon className="landing-trust-icon" strokeWidth={1.5} />
      <h4 className="landing-trust-label">{label}</h4>
      {description && <p className="landing-trust-desc">{description}</p>}
    </div>
  );
}
