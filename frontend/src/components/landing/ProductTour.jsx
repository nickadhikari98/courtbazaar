import React, { useCallback } from "react";
import { Joyride, ACTIONS, EVENTS, STATUS } from "react-joyride";
import TourTooltip from "./TourTooltip";

const steps = [
  {
    target: "#hero",
    title: "Welcome to CourtBazaar™",
    content: "Your one-stop platform for litigation support services. Let's take a quick look around the page.",
    placement: "bottom",
  },
  {
    target: "#services",
    title: "Core Services",
    content: "Order printing, photocopy, scanning, OCR and e-filing services for your matters — plus Proxy Counsel, our featured service.",
    placement: "top",
  },
  {
    target: "#pricing",
    title: "Package Plans",
    content: "Pick a plan that fits your practice, from individual advocates to full litigation teams. Bulk pricing is available too.",
    placement: "top",
  },
  {
    target: "#coverage",
    title: "Courts Coverage",
    content: "Check which courts we currently service before placing an order.",
    placement: "top",
  },
  {
    target: "#reviews",
    title: "Reviews",
    content: "See what advocates and law firms are saying about their experience with CourtBazaar™.",
    placement: "top",
  },
  {
    target: "#contact",
    title: "Contact & Footer",
    content: "Reach our team, browse useful links, or follow us on social media from here.",
    placement: "top",
  },
];

export { steps as productTourSteps };

export default function ProductTour({ run, stepIndex, onStepChange, onEnd }) {
  const handleEvent = useCallback((data) => {
    const { action, index, status, type } = data;

    if (type === EVENTS.STEP_AFTER || type === EVENTS.TARGET_NOT_FOUND) {
      onStepChange(index + (action === ACTIONS.PREV ? -1 : 1));
    } else if (status === STATUS.FINISHED || status === STATUS.SKIPPED) {
      onEnd();
    }
  }, [onStepChange, onEnd]);

  return (
    <Joyride
      steps={steps}
      run={run}
      stepIndex={stepIndex}
      onEvent={handleEvent}
      continuous
      scrollToFirstStep
      tooltipComponent={TourTooltip}
      options={{
        primaryColor: "#D97706",
        overlayColor: "rgba(15, 23, 42, 0.35)",
        zIndex: 10000,
        spotlightPadding: 12,
        spotlightRadius: 18,
        skipBeacon: true,
        overlayClickAction: false,
      }}
      styles={{
        spotlight: {
          stroke: "#D97706",
          strokeWidth: 3,
          strokeOpacity: 0.5,
          style: {
            filter: "drop-shadow(0 0 16px rgba(217, 119, 6, 0.45))",
            pointerEvents: "none",
          },
        },
        overlay: {
          transition: "opacity 0.3s ease",
        },
      }}
    />
  );
}
