import React from "react";

export default function StepItem({ number, title, description, icon: Icon, showConnector = false }) {
  return (
    <div className="landing-step">
      {showConnector && <div className="landing-step-connector" />}
      <div className="landing-step-icon">
        <Icon className="w-9 h-9" />
      </div>
      <div className="landing-step-number landing-step-number--active">{number}</div>
      <h4 className="landing-step-title">{title}</h4>
      <p className="landing-step-desc">{description}</p>
    </div>
  );
}
