import React from "react";
import CounselHiringPage from "@/components/proxyCounsel/CounselHiringPage";

/* Public entry point for single-hearing proxy counsel engagements — the one
   page in the app reachable without login (see App.js's HireProxyCounselRoute).
   All actual browse/filter/select/negotiate logic lives in the shared
   CounselHiringPage.jsx, which HireCounsel.jsx (full representation) also
   renders with a different serviceType — see that component's docstring. */
export default function HireProxyCounsel() {
  return <CounselHiringPage serviceType="proxy_counsel" />;
}
