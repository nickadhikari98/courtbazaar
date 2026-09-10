import React from "react";
import CounselHiringPage from "@/components/proxyCounsel/CounselHiringPage";

/* Hire Counsel — full legal representation for a matter, as opposed to Hire
   Proxy Counsel's single-appearance engagements. Founder direction
   (2026-08): the same browse/filter/select/negotiate/pay flow as Hire Proxy
   Counsel, just configured for this service (see CounselHiringPage.jsx and
   its SERVICE_CONFIGS.counsel entry in config/serviceRequestFields.js) —
   no parallel form, no parallel request model, no separate professional
   pool. Public route, same as Hire Proxy Counsel (see App.js) — an
   anonymous visitor can browse and filter counsels; selecting one is what
   requires login + can_hire_proxy_counsel (enforced in CounselHiringPage.jsx
   itself, not the route). */
export default function HireCounsel() {
  return <CounselHiringPage serviceType="counsel" />;
}
