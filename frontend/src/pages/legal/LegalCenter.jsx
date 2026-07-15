import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Search, ArrowRight, FileText, ShieldCheck, RotateCcw, Truck, Cookie, AlertTriangle,
  Lock, Database, MessageSquareWarning, Store, Scale, Users, FileUp, Scale3d,
} from "lucide-react";
import { UtilityBar, LandingNav, LandingFooter } from "@/components/landing";
import Breadcrumb from "@/components/legal/Breadcrumb";
import ComplianceBanner from "@/components/legal/ComplianceBanner";
import { legalDocsList } from "@/content/legal";
import usePageSEO from "@/hooks/usePageSEO";
import useStructuredData, { breadcrumbSchema } from "@/hooks/useStructuredData";

const ICONS = {
  terms: FileText,
  privacy: ShieldCheck,
  refund: RotateCcw,
  delivery: Truck,
  cookies: Cookie,
  disclaimer: AlertTriangle,
  confidentiality: Lock,
  "data-retention": Database,
  grievance: MessageSquareWarning,
  "vendor-terms": Store,
  "advocate-terms": Scale,
  "counsel-terms": Users,
  "efiling-terms": FileUp,
};

function formatUpdated(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString("en-IN", { month: "short", year: "numeric" });
}

export default function LegalCenter() {
  const [query, setQuery] = useState("");

  usePageSEO({
    title: "Legal Center",
    description: "CourtBazaar™'s legal policies, user agreements, privacy commitments, and compliance documents.",
    path: "/legal",
  });
  useStructuredData("legal-center-breadcrumb", breadcrumbSchema([{ label: "Legal Center" }]));

  const filtered = useMemo(() => {
    if (!query.trim()) return legalDocsList;
    const q = query.toLowerCase();
    return legalDocsList.filter(
      (doc) => doc.title.toLowerCase().includes(q) || doc.summary?.toLowerCase().includes(q)
    );
  }, [query]);

  return (
    <div className="min-h-screen bg-background">
      <UtilityBar />
      <LandingNav />

      <section className="landing-section pb-0">
        <div className="landing-container">
          <Breadcrumb items={[{ label: "Legal Center" }]} />

          <div className="mt-6 max-w-3xl">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-accent/10 mb-4">
              <Scale3d className="w-7 h-7 text-accent" strokeWidth={2} />
            </div>
            <h1 className="landing-section-title text-left">Legal Center</h1>
            <p className="text-muted-foreground mt-4 text-base leading-relaxed">
              This page contains CourtBazaar™'s legal policies, user agreements, privacy commitments, operational
              policies, and compliance documents. We encourage every user, advocate, vendor, and partner to
              review the applicable policies before using our platform.
            </p>
          </div>

          <div className="mt-6 max-w-3xl">
            <ComplianceBanner />
          </div>

          <div className="mt-8 max-w-md">
            <div className="legal-search-box">
              <Search className="w-4 h-4 text-muted-foreground flex-shrink-0" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search policies (e.g. refund, cookies, vendor)…"
                aria-label="Search legal policies"
              />
            </div>
          </div>
        </div>
      </section>

      <section className="landing-section">
        <div className="landing-container">
          {filtered.length === 0 ? (
            <p className="text-muted-foreground">No policies match "{query}".</p>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {filtered.map((doc) => {
                const Icon = ICONS[doc.slug] || FileText;
                return (
                  <Link key={doc.slug} to={`/legal/${doc.slug}`} className="legal-center-card group">
                    <div className="legal-center-card-icon">
                      <Icon className="w-5 h-5 text-accent" strokeWidth={2} />
                    </div>
                    <h3 className="font-display font-bold text-base mt-3">{doc.title}</h3>
                    <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed line-clamp-2">{doc.summary}</p>
                    <div className="flex items-center justify-between mt-4">
                      {doc.lastUpdated && (
                        <span className="text-xs text-muted-foreground/70 font-medium">
                          Updated {formatUpdated(doc.lastUpdated)}
                        </span>
                      )}
                      <span className="inline-flex items-center gap-1 text-xs font-bold text-accent opacity-0 group-hover:opacity-100 transition-opacity">
                        View <ArrowRight className="w-3.5 h-3.5" />
                      </span>
                    </div>
                  </Link>
                );
              })}
            </div>
          )}

          <div className="mt-10 pt-8 border-t border-slate-200 flex flex-wrap gap-3">
            <Link to="/about" className="legal-action-btn">
              About Us <ArrowRight className="w-3.5 h-3.5" />
            </Link>
            <Link to="/contact" className="legal-action-btn">
              Contact Us <ArrowRight className="w-3.5 h-3.5" />
            </Link>
            <Link to="/security" className="legal-action-btn">
              Security <ArrowRight className="w-3.5 h-3.5" />
            </Link>
            <Link to="/trust" className="legal-action-btn">
              Trust Center <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
