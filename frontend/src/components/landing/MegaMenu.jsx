import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Printer, Copy, ScanLine, FileText, Landmark, Building2, Mic, ArrowRight, Sparkles,
} from "lucide-react";
import { listPublicServices } from "@/lib/servicesApi";

// Same "which id gets which small icon" idea as Landing.jsx's
// LANDING_ILLUSTRATIONS, kept separate since the mega menu deliberately uses
// plain lucide glyphs rather than the bespoke landing illustrations — the
// service list itself (names/descriptions/order) still comes from the same
// backend surface="landing" call, so it can never drift from Landing.jsx again.
const MEGAMENU_ICONS = {
  svc_bw_print: Printer,
  svc_bw_photocopy: Copy,
  svc_scanning: ScanLine,
  svc_ocr: FileText,
  svc_efile_district: Landmark,
  svc_efile_hc: Building2,
  svc_steno_hearing: Mic,
};

const proxyCounsel = {
  image: "/images/illustrations/proxy-counsel-badge.png",
  name: "Counsel / Proxy Counsel",
  description: "Find and connect with verified proxy counsels across Delhi",
};

export default function MegaMenu() {
  const [services, setServices] = useState([]);

  useEffect(() => {
    listPublicServices("landing").then(setServices).catch(() => setServices([]));
  }, []);

  return (
    <div className="landing-mega-menu">
      <div className="grid grid-cols-3 gap-1">
        {services.map((s) => {
          const Icon = MEGAMENU_ICONS[s.service_id] || FileText;
          return (
            <Link
              key={s.service_id}
              to="/#services"
              className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors"
            >
              <div className="w-9 h-9 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
                <Icon className="w-4 h-4 text-accent" />
              </div>
              <div>
                <div className="text-sm font-semibold leading-tight">{s.landing_name || s.name}</div>
                <div className="text-xs text-muted-foreground mt-0.5 leading-snug">{s.description}</div>
              </div>
            </Link>
          );
        })}
      </div>

      {/* Proxy Counsel - flagship row */}
      <Link
        to="/#services"
        className="landing-mega-featured mt-3 flex items-center justify-between gap-3 p-4 rounded-xl"
      >
        <div className="flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-full bg-white flex items-center justify-center flex-shrink-0 overflow-hidden shadow-sm">
            <img src={proxyCounsel.image} alt="" className="w-full h-full object-cover" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold leading-tight">{proxyCounsel.name}</span>
              <span className="landing-mega-featured-badge">
                <Sparkles className="w-2.5 h-2.5" /> Featured
              </span>
            </div>
            <div className="text-xs text-muted-foreground mt-0.5 leading-snug">{proxyCounsel.description}</div>
          </div>
        </div>
        <ArrowRight className="w-4 h-4 text-accent flex-shrink-0" />
      </Link>
    </div>
  );
}
