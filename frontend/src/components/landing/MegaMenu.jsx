import React from "react";
import { Link } from "react-router-dom";
import {
  Printer, Copy, ScanLine, FileText, Landmark, Building2, ArrowRight, Sparkles,
} from "lucide-react";

const menuRows = [
  [
    { icon: Printer, name: "Print-Out Service", description: "Fast, high quality court document printing" },
    { icon: Copy, name: "Photocopy", description: "Bulk & urgent photocopying across Delhi courts" },
    { icon: ScanLine, name: "Scanning", description: "High resolution scanning, quick turnaround" },
  ],
  [
    { icon: FileText, name: "OCR + Bookmarking", description: "Searchable, filing-ready PDFs" },
    { icon: Landmark, name: "E-Filing District Court", description: "Delhi District Court e-filing support" },
    { icon: Building2, name: "E-Filing High Court", description: "Delhi High Court e-filing support" },
  ],
];

const proxyCounsel = {
  image: "/images/illustrations/proxy-counsel-badge.png",
  name: "Proxy Counsel",
  description: "Find and connect with verified proxy counsels across Delhi",
};

export default function MegaMenu() {
  return (
    <div className="landing-mega-menu">
      <div className="space-y-1">
        {menuRows.map((row, i) => (
          <div key={i} className="grid grid-cols-3 gap-1">
            {row.map((s) => (
              <Link
                key={s.name}
                to="#services"
                className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors"
              >
                <div className="w-9 h-9 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
                  <s.icon className="w-4 h-4 text-accent" />
                </div>
                <div>
                  <div className="text-sm font-semibold leading-tight">{s.name}</div>
                  <div className="text-xs text-muted-foreground mt-0.5 leading-snug">{s.description}</div>
                </div>
              </Link>
            ))}
          </div>
        ))}
      </div>

      {/* Proxy Counsel - flagship row */}
      <Link
        to="#services"
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
