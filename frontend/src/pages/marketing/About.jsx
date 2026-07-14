import React from "react";
import { Link } from "react-router-dom";
import {
  Target, Eye, Check, Cpu, ShieldCheck, Zap, Lock as LockIcon, Handshake, Award, Users2,
  Building2, Landmark, Scale, ArrowRight, MapPinned, MapPin,
} from "lucide-react";
import { UtilityBar, LandingNav, LandingFooter } from "@/components/landing";
import ComingSoonBadge from "@/components/shared/ComingSoonBadge";
import { companyInfo } from "@/config/companyInfo";
import usePageSEO from "@/hooks/usePageSEO";
import useStructuredData, { breadcrumbSchema } from "@/hooks/useStructuredData";

const whatWeDo = [
  "Printout Services",
  "Photocopy Services",
  "Scanning Services",
  "OCR & Bookmarking",
  "E-Filing Services",
  "Litigation Support Package Plans",
  "Proxy Counsel Discovery & Engagement",
  "Verified Professional and Vendor Network",
];

const coreValues = [
  { icon: Cpu, label: "Technology", desc: "Purpose-built tools for the operational side of legal work." },
  { icon: ShieldCheck, label: "Transparency", desc: "Clear pricing and status at every step of an order." },
  { icon: Zap, label: "Speed", desc: "Fast turnaround so filing deadlines are never the bottleneck." },
  { icon: LockIcon, label: "Confidentiality", desc: "Client documents handled with strict access controls." },
  { icon: Handshake, label: "Reliability", desc: "A vetted network you can depend on, order after order." },
  { icon: Award, label: "Trust", desc: "Built with and for the legal community, not around it." },
  { icon: Users2, label: "Professional Network", desc: "Advocates, vendors, and partners working on one platform." },
];

const coverage = [
  { icon: Landmark, label: "Delhi District Courts" },
  { icon: Building2, label: "Delhi High Court" },
  { icon: Scale, label: "Supreme Court of India" },
  { icon: MapPinned, label: "Future Expansion", soon: true },
];

const stats = [
  { label: "Legal Services", value: "6+" },
  { label: "Court Coverage", value: "3" },
  { label: "Platform Type", value: "Technology Enabled" },
  { label: "Availability", value: "Mon–Sat" },
  { label: "Professional Network", value: "Growing" },
];

const timeline = [
  { year: "2026", label: "CourtBazaar Founded" },
  { label: "Legal Operations Platform" },
  { label: "Vendor Network" },
  { label: "Proxy Counsel" },
  { label: "Nationwide Expansion", soon: true },
];

export default function About() {
  usePageSEO({
    title: "About Us",
    description: "CourtBazaar is India's first legal operations network and services platform — connecting advocates, law firms, and vendors on one platform.",
    path: "/about",
  });
  useStructuredData("about-breadcrumb", breadcrumbSchema([{ label: "About Us" }]));

  return (
    <div className="min-h-screen bg-background">
      <UtilityBar />
      <LandingNav />

      {/* Hero + Mission / Vision */}
      <section className="landing-section pb-0">
        <div className="landing-container grid lg:grid-cols-[1fr_360px] gap-10 lg:gap-12 items-start">
          <div>
            <div className="cb-overline text-accent mb-3">Welcome to CourtBazaar</div>
            <h1 className="landing-section-title text-left">India's First Legal Operations Network &amp; Services Platform</h1>
            <p className="landing-section-subtitle mt-4 text-left">
              CourtBazaar is India's First Legal Operations Network & Services Platform, built with a vision to
              simplify and modernise the operational side of litigation and legal practice.
            </p>
            <p className="text-muted-foreground mt-4 text-base leading-relaxed">
              We understand that legal professionals spend a significant amount of their valuable time managing
              administrative and operational tasks such as printing, photocopy/Xerox, scanning, OCR &amp;
              Bookmarking, e-filing, document preparation, and coordinating with multiple service providers.
              These activities often reduce productivity and create unnecessary inefficiencies.
            </p>
            <p className="text-muted-foreground mt-4 text-base leading-relaxed">
              CourtBazaar is established to bridge this gap by creating a trusted technology-driven ecosystem
              that connects advocates, law firms, and legal professionals with reliable legal operations
              services and professional networks through one integrated platform.
            </p>
          </div>
          <div className="space-y-5">
            <div className="landing-premium-card">
              <div className="landing-premium-card-icon">
                <Target className="w-5 h-5 text-accent" strokeWidth={2} />
              </div>
              <h3 className="font-display font-bold text-lg mb-2">Our Mission</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">
                To simplify legal operations through technology, trusted networks, and efficient workflows by
                creating a reliable and accessible ecosystem for advocates, law firms, and legal professionals.
              </p>
            </div>
            <div className="landing-premium-card">
              <div className="landing-premium-card-icon">
                <Eye className="w-5 h-5 text-accent" strokeWidth={2} />
              </div>
              <h3 className="font-display font-bold text-lg mb-2">Our Vision</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">
                To become India's most trusted Legal Operations Network & Services Platform and build the
                operating system for litigation support services by connecting the legal ecosystem through
                technology, transparency, and operational excellence.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* What We Do */}
      <section className="landing-section">
        <div className="landing-container max-w-4xl mx-auto">
          <div className="landing-premium-card sm:p-8">
            <h3 className="font-display font-bold text-lg mb-1">What We Do</h3>
            <p className="text-sm text-muted-foreground mb-5">
              CourtBazaar provides a comprehensive suite of legal operations and litigation support services,
              including:
            </p>
            <ul className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-2.5">
              {whatWeDo.map((item) => (
                <li key={item} className="flex items-start gap-2 text-sm text-foreground">
                  <Check className="w-4 h-4 text-emerald-500 flex-shrink-0 mt-0.5" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <p className="text-sm text-muted-foreground mt-5">
              Our objective is to help legal professionals focus on practising law while we simplify and
              streamline the operational aspects of their work.
            </p>
          </div>
        </div>
      </section>

      {/* Why CourtBazaar / Core Values */}
      <section className="landing-section bg-slate-50">
        <div className="landing-container">
          <div className="landing-section-header">
            <h2 className="landing-section-title">Why CourtBazaar</h2>
            <p className="landing-section-subtitle">The principles behind how we operate.</p>
          </div>
          <div className="flex flex-wrap justify-center gap-x-6 gap-y-8 md:grid md:grid-cols-4 md:gap-6">
            {coreValues.map((v) => (
              <div key={v.label} className="w-[45%] sm:w-[28%] md:w-auto text-center">
                <div className="w-14 h-14 rounded-2xl bg-white border border-slate-200 flex items-center justify-center mx-auto mb-3 shadow-sm">
                  <v.icon className="w-6 h-6 text-accent" strokeWidth={1.75} />
                </div>
                <h4 className="font-display font-bold text-sm">{v.label}</h4>
                <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">{v.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Coverage + Journey */}
      <section className="landing-section bg-slate-50">
        <div className="landing-container grid lg:grid-cols-2 gap-10 lg:gap-12 items-start">
          <div>
            <h2 className="landing-subsection-title mb-5">Coverage</h2>
            <div className="grid grid-cols-2 gap-4">
              {coverage.map((c) => (
                <div key={c.label} className="landing-premium-card text-center overflow-hidden">
                  {c.soon && <ComingSoonBadge />}
                  <c.icon className="w-6 h-6 text-accent mx-auto mb-2" strokeWidth={1.75} />
                  <p className="text-sm font-semibold">{c.label}</p>
                </div>
              ))}
            </div>
          </div>
          <div>
            <h2 className="landing-subsection-title mb-5">Our Journey</h2>
            <ol className="space-y-0">
              {timeline.map((t, i) => (
                <li key={t.label} className="flex gap-4">
                  <div className="flex flex-col items-center">
                    <span className={`w-3 h-3 rounded-full flex-shrink-0 ${t.soon ? "bg-slate-300" : "bg-accent"}`} />
                    {i < timeline.length - 1 && <span className="w-px flex-1 bg-slate-200 my-1" />}
                  </div>
                  <div className="pb-6">
                    {t.year && <span className="text-xs font-bold text-accent uppercase tracking-wide">{t.year}</span>}
                    <p className={`font-display font-bold text-sm mt-0.5 flex items-center gap-1.5 ${t.soon ? "text-muted-foreground" : ""}`}>
                      {t.label} {t.soon && <ComingSoonBadge variant="inline" />}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      {/* Stats + Company Details */}
      <section className="landing-section">
        <div className="landing-container">
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
            {stats.map((s) => (
              <div key={s.label} className="landing-premium-card text-center">
                <div className="font-display font-black text-2xl text-primary">{s.value}</div>
                <div className="text-xs text-muted-foreground mt-1 font-medium">{s.label}</div>
              </div>
            ))}
          </div>

          <div className="mt-8 max-w-3xl mx-auto">
            <div className="landing-premium-card sm:p-8">
              <h3 className="font-display font-bold text-lg mb-4">Company Details</h3>
              <div className="grid sm:grid-cols-2 gap-6">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1">Company Name</p>
                  <p className="text-sm text-foreground">{companyInfo.brandName}</p>
                  <p className="text-sm text-muted-foreground">Powered by {companyInfo.legalName}</p>
                </div>
                <div>
                  <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1">Registered Office</p>
                  <p className="text-sm text-foreground flex items-start gap-1.5">
                    <MapPin className="w-4 h-4 text-accent flex-shrink-0 mt-0.5" />
                    <span>{companyInfo.officeAddress.value}</span>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="landing-section bg-primary text-white">
        <div className="landing-container text-center max-w-xl mx-auto">
          <h2 className="landing-cta-title">Need Legal Operations Support?</h2>
          <Link to="/register" className="inline-block mt-6">
            <span className="inline-flex items-center gap-2 bg-accent hover:bg-accent/90 text-white font-bold px-6 py-3 rounded-lg transition-colors">
              Get Started <ArrowRight className="w-4 h-4" />
            </span>
          </Link>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
