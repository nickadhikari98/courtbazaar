import React from "react";
import { Link } from "react-router-dom";
import {
  Lock, KeyRound, UploadCloud, Database, ClipboardList, ShieldCheck, BadgeCheck, ArrowRight,
} from "lucide-react";
import { UtilityBar, LandingNav, LandingFooter } from "@/components/landing";
import ComingSoonBadge from "@/components/shared/ComingSoonBadge";
import usePageSEO from "@/hooks/usePageSEO";
import useStructuredData, { breadcrumbSchema } from "@/hooks/useStructuredData";

const facets = [
  {
    icon: Lock,
    title: "Data Encryption",
    status: "live",
    desc: "All traffic between your browser and CourtBazaar is encrypted in transit over HTTPS/TLS.",
  },
  {
    icon: KeyRound,
    title: "Role-Based Access",
    status: "live",
    desc: "Every account has a defined role (advocate, vendor, admin, etc.) and every route enforces it server-side — access isn't just hidden in the UI, it's checked on every request.",
  },
  {
    icon: UploadCloud,
    title: "Secure Uploads",
    status: "live",
    desc: "Documents you upload are transferred securely and stored with access-controlled cloud storage, never on a public path.",
  },
  {
    icon: Database,
    title: "Cloud Storage",
    status: "live",
    desc: "Files are held in managed cloud object storage rather than on individual servers, with per-document access control.",
  },
  {
    icon: ClipboardList,
    title: "Audit Logging",
    status: "live",
    desc: "Key account and platform events are recorded to an audit trail for accountability and investigation.",
  },
  {
    icon: ShieldCheck,
    title: "Data Privacy",
    status: "live",
    desc: "Personal and case data is handled per our Privacy Policy — collection, use, and retention are all documented.",
    link: { to: "/legal/privacy", label: "Read our Privacy Policy" },
  },
  {
    icon: BadgeCheck,
    title: "Independent Security Audit",
    status: "soon",
    desc: "A formal third-party security assessment is planned but not yet completed.",
  },
  {
    icon: BadgeCheck,
    title: "Compliance Certifications",
    status: "soon",
    desc: "We do not currently hold formal certifications (e.g. ISO 27001, SOC 2). We will publish them here if and when obtained.",
  },
];

export default function Security() {
  usePageSEO({
    title: "Security",
    description: "How CourtBazaar protects your documents and data — encryption, access control, secure storage, and audit logging.",
    path: "/security",
  });
  useStructuredData("security-breadcrumb", breadcrumbSchema([{ label: "Security" }]));

  return (
    <div className="min-h-screen bg-background">
      <UtilityBar />
      <LandingNav />

      <section className="landing-section pb-0">
        <div className="landing-container text-center max-w-2xl mx-auto">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-accent/10 mb-4">
            <ShieldCheck className="w-7 h-7 text-accent" strokeWidth={2} />
          </div>
          <h1 className="landing-section-title">Security at CourtBazaar</h1>
          <p className="landing-section-subtitle mt-3">
            How we protect the documents and data that pass through our platform.
          </p>
        </div>
      </section>

      <section className="landing-section">
        <div className="landing-container grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {facets.map((f) => (
            <div key={f.title} className="landing-premium-card flex flex-col h-full overflow-hidden">
              {f.status === "soon" && <ComingSoonBadge />}
              <div className="landing-premium-card-icon">
                <f.icon className="w-5 h-5 text-accent" strokeWidth={2} />
              </div>
              <h3 className="font-display font-bold text-base">{f.title}</h3>
              <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">{f.desc}</p>
              {f.link && (
                <Link to={f.link.to} className="inline-flex items-center gap-1 text-xs font-bold text-accent mt-auto pt-3 hover:underline">
                  {f.link.label} <ArrowRight className="w-3 h-3" />
                </Link>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="landing-section bg-primary text-white">
        <div className="landing-container text-center max-w-xl mx-auto">
          <h2 className="landing-cta-title">Have a security question or concern?</h2>
          <Link to="/contact" className="inline-block mt-6">
            <span className="inline-flex items-center gap-2 bg-accent hover:bg-accent/90 text-white font-bold px-6 py-3 rounded-lg transition-colors">
              Contact Us <ArrowRight className="w-4 h-4" />
            </span>
          </Link>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
