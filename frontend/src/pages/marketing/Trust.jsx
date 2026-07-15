import React from "react";
import { Link } from "react-router-dom";
import {
  Activity, ShieldCheck, Lock, ClipboardCheck, FileStack, BadgeCheck, HeadphonesIcon, Clock, ArrowRight,
} from "lucide-react";
import MarketingLayout from "@/components/layout/MarketingLayout";
import { companyInfo } from "@/config/companyInfo";
import usePageSEO from "@/hooks/usePageSEO";
import useStructuredData, { breadcrumbSchema } from "@/hooks/useStructuredData";

const facets = [
  {
    icon: Activity,
    title: "Platform Status",
    value: "Operational",
    desc: "CourtBazaar's core services are up and running.",
  },
  {
    icon: ShieldCheck,
    title: "Security",
    desc: "Encryption in transit, role-based access control, and secure document storage.",
    link: { to: "/security", label: "View Security" },
  },
  {
    icon: Lock,
    title: "Privacy",
    desc: "What we collect, how we use it, and your rights over your data.",
    link: { to: "/legal/privacy", label: "View Privacy Policy" },
  },
  {
    icon: ClipboardCheck,
    title: "Compliance",
    value: "In Progress",
    desc: "Formal certifications are not yet obtained — we'll publish them here once complete.",
  },
  {
    icon: FileStack,
    title: "Document Handling",
    desc: "How uploaded case documents are stored, accessed, and retained.",
    link: { to: "/legal/confidentiality", label: "View Confidentiality Policy" },
  },
  {
    icon: BadgeCheck,
    title: "Vendor Verification",
    desc: "Every vendor and delivery partner goes through a document-based onboarding review before joining the network.",
  },
  {
    icon: HeadphonesIcon,
    title: "Support SLA",
    value: "Within 1 business day",
    desc: "Our typical response time for support enquiries.",
  },
  {
    icon: Clock,
    title: "Business Hours",
    value: companyInfo.businessHours.value,
    desc: "When our support team is actively available.",
  },
];

export default function Trust() {
  usePageSEO({
    title: "Trust Center",
    description: "CourtBazaar's Trust Center — platform status, security, privacy, compliance, and document handling.",
    path: "/trust",
  });
  useStructuredData("trust-breadcrumb", breadcrumbSchema([{ label: "Trust Center" }]));

  return (
    <MarketingLayout>
      <section className="landing-section pb-0">
        <div className="landing-container text-center max-w-2xl mx-auto">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-accent/10 mb-4">
            <BadgeCheck className="w-7 h-7 text-accent" strokeWidth={2} />
          </div>
          <h1 className="landing-section-title">Trust Center</h1>
          <p className="landing-section-subtitle mt-3">
            A single place to see how CourtBazaar handles security, privacy, and compliance.
          </p>
        </div>
      </section>

      <section className="landing-section">
        <div className="landing-container grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {facets.map((f) => (
            <div key={f.title} className="landing-premium-card flex flex-col h-full">
              <div className="landing-premium-card-icon">
                <f.icon className="w-5 h-5 text-accent" strokeWidth={2} />
              </div>
              <h3 className="font-display font-bold text-base">{f.title}</h3>
              {f.value && <p className="text-xs font-bold text-accent mt-1">{f.value}</p>}
              <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">{f.desc}</p>
              {f.link && (
                <Link to={f.link.to} className="inline-flex items-center gap-1 text-xs font-bold text-accent mt-auto pt-2.5 hover:underline">
                  {f.link.label} <ArrowRight className="w-3 h-3" />
                </Link>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="landing-section bg-slate-50">
        <div className="landing-container max-w-3xl mx-auto text-center">
          <h2 className="landing-subsection-title mb-4">Explore Our Policies</h2>
          <Link to="/legal" className="inline-flex items-center gap-2 text-sm font-bold text-accent hover:underline">
            Visit the Legal Center <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>
    </MarketingLayout>
  );
}
