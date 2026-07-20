import React, { useCallback, useEffect, useState } from "react";
import { useSearchParams, useLocation } from "react-router-dom";
import {
  Clock, Network, Activity, Shield, BadgeCheck, ShieldCheck, Mic,
} from "lucide-react";

import MarketingLayout from "@/components/layout/MarketingLayout";
import { listPublicServices, formatServicePrice } from "@/lib/servicesApi";
import {
  HeroSection,
  ServiceCard,
  FeaturedServiceCard,
  StepItem,
  TrustBadge,
  PricingSection,
  CoverageSection,
  ReviewsSection,
  ProductTour,
  PrintOutIcon,
  PhotocopyIcon,
  ScanningIcon,
  OcrBookmarkIcon,
  EFilingDistrictIcon,
  EFilingHighIcon,
  SelectServiceIcon,
  UploadDocIcon,
  ReviewPayIcon,
  ProcessingIcon,
  DeliveredIcon,
} from "@/components/landing";

/* ===== DATA CONSTANTS ===== */

// Presentation-only lookup — bespoke illustration + accent color per curated
// landing service. The service list itself (which ids appear, name, price,
// description, order) comes from the backend (`visibility.landing`, see
// court_seed.py) so Landing/MegaMenu/Pricing/Dashboard never drift again;
// this map only decides *how* a known id is drawn, with a generic fallback
// for anything visible on landing that isn't in this bespoke set yet.
const LANDING_ILLUSTRATIONS = {
  svc_bw_print: { icon: PrintOutIcon, color: "amber" },
  svc_bw_photocopy: { icon: PhotocopyIcon, color: "blue" },
  svc_scanning: { icon: ScanningIcon, color: "emerald" },
  svc_ocr: { icon: OcrBookmarkIcon, color: "purple" },
  svc_efile_district: { icon: EFilingDistrictIcon, color: "rose" },
  svc_efile_hc: { icon: EFilingHighIcon, color: "cyan" },
  svc_steno_hearing: { icon: Mic, color: "orange" },
};

const proxyCounselService = {
  image: "/images/illustrations/proxy-counsel-badge.png",
  name: "Counsel / Proxy Counsel",
  description: "Find and connect with verified proxy counsels across India — briefed, reliable, and ready to appear on your behalf.",
  cta: "Book Now",
  startingPrice: "₹Starting from 499/appearance",
};

const howItWorksSteps = [
  {
    number: 1,
    icon: SelectServiceIcon,
    title: "Select Service",
    description: "Choose the service you need",
  },
  {
    number: 2,
    icon: UploadDocIcon,
    title: "Upload Documents",
    description: "Upload your files securely",
  },
  {
    number: 3,
    icon: ReviewPayIcon,
    title: "Review & Pay",
    description: "Review order details and make payment",
  },
  {
    number: 4,
    icon: ProcessingIcon,
    title: "We Process",
    description: "Our team processes your request",
  },
  {
    number: 5,
    icon: DeliveredIcon,
    title: "Delivered",
    description: "Get your documents delivered on time",
  },
];

const trustBadges = [
  { icon: Clock, label: "Time Saving", description: "Save hours of your valuable time" },
  { icon: Network, label: "Reliable Network", description: "Verified vendors and trusted partners" },
  { icon: Activity, label: "Real-time Tracking", description: "Track your orders in real-time" },
  { icon: Shield, label: "Secure & Confidential", description: "Your documents are 100% safe with us" },
  { icon: BadgeCheck, label: "Best Prices", description: "Transparent pricing with no hidden costs" },
];

/* ===== LANDING PAGE ===== */

export default function Landing() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const [tourRun, setTourRun] = useState(false);
  const [tourStep, setTourStep] = useState(0);
  const [coreServices, setCoreServices] = useState([]);

  useEffect(() => {
    listPublicServices("landing")
      .then((services) => setCoreServices(services.map((s) => {
        const presentation = LANDING_ILLUSTRATIONS[s.service_id] || { icon: PrintOutIcon, color: "amber" };
        return {
          key: s.service_id,
          icon: presentation.icon,
          name: s.landing_name || s.name,
          description: s.description,
          color: presentation.color,
          startingPrice: formatServicePrice(s),
        };
      })))
      .catch(() => setCoreServices([]));
  }, []);

  useEffect(() => {
    if (searchParams.get("tour") === "1") {
      setTourStep(0);
      setTourRun(true);
      const next = new URLSearchParams(searchParams);
      next.delete("tour");
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Deep-link support for in-page anchors like /#services (used by the nav's
  // mega menu) — runs after ScrollToTop's top-reset, so it always scrolls
  // down from the top rather than racing it.
  useEffect(() => {
    const hash = location.hash?.slice(1);
    if (!hash) return;
    const id = requestAnimationFrame(() => {
      document.getElementById(hash)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return () => cancelAnimationFrame(id);
  }, [location.hash]);

  const handleTakeTour = useCallback(() => {
    setTourStep(0);
    setTourRun(true);
  }, []);

  return (
    <MarketingLayout navProps={{ onTakeTour: handleTakeTour }}>
      {/* Guided Tour */}
      <ProductTour
        run={tourRun}
        stepIndex={tourStep}
        onStepChange={setTourStep}
        onEnd={() => setTourRun(false)}
      />

      {/* Hero Section */}
      <HeroSection />

      {/* Core Services */}
      <section id="services" className="landing-section">
        <div className="landing-container">
          <div className="landing-section-header">
            <h2 className="landing-section-title">Our Core Services</h2>
            <p className="landing-section-subtitle">
              Everything you need to manage your legal operations efficiently
            </p>
          </div>
          <div className="lg:grid lg:grid-cols-[1fr_300px] xl:grid-cols-[1fr_340px] lg:gap-7 lg:items-stretch">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-7">
              {coreServices.map(({ key, ...service }) => (
                <ServiceCard key={key} {...service} />
              ))}
            </div>
            <FeaturedServiceCard
              {...proxyCounselService}
              vertical
              className="mt-7 lg:mt-0"
            />
          </div>
        </div>
      </section>

      {/* Pricing */}
      <PricingSection />

      {/* How It Works */}
      <section id="how" className="landing-section bg-slate-50">
        <div className="landing-container">
          <div className="landing-section-header">
            <h2 className="landing-section-title">How It Works</h2>
            <p className="landing-section-subtitle">
              Simple, Transparent and Efficient
            </p>
          </div>
          <div className="flex flex-wrap justify-center gap-x-6 gap-y-8 md:grid md:grid-cols-5 md:gap-6 lg:gap-8">
            {howItWorksSteps.map((step, i) => (
              <div key={step.number} className="w-[45%] sm:w-[28%] md:w-auto">
                <StepItem
                  {...step}
                  showConnector={i < howItWorksSteps.length - 1}
                />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Trust Section */}
      <section className="landing-trust-section">
        <div className="landing-container">
          <div className="flex flex-col items-center mb-11">
            <div className="w-14 h-14 rounded-2xl bg-accent/15 border border-accent/30 flex items-center justify-center mb-4">
              <ShieldCheck className="w-7 h-7 text-accent" strokeWidth={1.75} />
            </div>
            <h2 className="text-center font-display font-bold text-3xl sm:text-4xl tracking-tight leading-tight">
              Why Legal Professionals Trust CourtBazaar™?
            </h2>
          </div>
          <div className="flex flex-wrap justify-center gap-x-6 gap-y-8 md:grid md:grid-cols-5 md:gap-6">
            {trustBadges.map((badge) => (
              <div key={badge.label} className="w-[45%] sm:w-[28%] md:w-auto">
                <TrustBadge {...badge} />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Court Coverage */}
      <CoverageSection />

      {/* Reviews / Testimonials */}
      <ReviewsSection />
    </MarketingLayout>
  );
}
