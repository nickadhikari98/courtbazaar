import React from "react";
import { toast } from "sonner";
import {
  Mail, Clock, Handshake, MessageSquareWarning, Newspaper, HeadphonesIcon,
  MapPin, Copy, Navigation, ExternalLink, ArrowRight, Landmark,
} from "lucide-react";
import MarketingLayout from "@/components/layout/MarketingLayout";
import ConfigRequiredBadge from "@/components/legal/ConfigRequiredBadge";
import ContactMap from "@/components/legal/ContactMap";
import { companyInfo } from "@/config/companyInfo";
import usePageSEO from "@/hooks/usePageSEO";
import useStructuredData, { breadcrumbSchema } from "@/hooks/useStructuredData";

function ContactCard({ icon: Icon, title, description, email, needsConfig }) {
  return (
    <div className="landing-premium-card flex flex-col h-full">
      <div className="landing-premium-card-icon">
        <Icon className="w-5 h-5 text-accent" strokeWidth={2} />
      </div>
      <h3 className="font-display font-bold text-base">{title}</h3>
      <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">{description}</p>
      <div className="mt-auto pt-4">
        {needsConfig ? (
          <ConfigRequiredBadge />
        ) : (
          <a href={`mailto:${email}`} className="text-sm font-semibold text-accent hover:underline">
            {email}
          </a>
        )}
      </div>
    </div>
  );
}

export default function Contact() {
  usePageSEO({
    title: "Contact Us",
    description: "Get in touch with CourtBazaar™ for support, partnerships, or general enquiries.",
    path: "/contact",
  });
  useStructuredData("contact-breadcrumb", breadcrumbSchema([{ label: "Contact Us" }]));

  const { lat, lng } = companyInfo.officeCoordinates;

  const copyAddress = async () => {
    const text = companyInfo.officeAddress.needsConfig
      ? "Okhla, New Delhi, India"
      : companyInfo.officeAddress.value;
    await navigator.clipboard.writeText(text);
    toast.success("Address copied to clipboard.");
  };

  return (
    <MarketingLayout>
      <section className="landing-section pb-0">
        <div className="landing-container text-center max-w-2xl mx-auto">
          <div className="cb-overline text-accent mb-3">Get in Touch</div>
          <h1 className="landing-section-title">Contact Us</h1>
          <p className="landing-section-subtitle mt-3">
            We would be delighted to hear from you. Whether you have a query, require support, wish to
            partner with us, or would like to know more about our services, please feel free to get in touch.
          </p>
        </div>
      </section>

      {/* Contact cards */}
      <section className="landing-section">
        <div className="landing-container grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          <ContactCard
            icon={Mail}
            title="General Enquiries"
            description="Questions about CourtBazaar™ or how our platform works."
            email={companyInfo.generalEmail.value}
            needsConfig={companyInfo.generalEmail.needsConfig}
          />
          <ContactCard
            icon={HeadphonesIcon}
            title="Support"
            description="Order help, account issues, or anything platform-related."
            email={companyInfo.supportEmail.value}
            needsConfig={companyInfo.supportEmail.needsConfig}
          />
          <ContactCard
            icon={Handshake}
            title="Partnerships"
            description="Vendor, advocate, or business partnership enquiries."
            email={companyInfo.partnershipEmail.value}
            needsConfig={companyInfo.partnershipEmail.needsConfig}
          />
          <ContactCard
            icon={Newspaper}
            title="Media"
            description="Press and media enquiries."
            email={companyInfo.mediaEmail.value}
            needsConfig={companyInfo.mediaEmail.needsConfig}
          />
          <ContactCard
            icon={MessageSquareWarning}
            title="Grievance Officer"
            description="Formal complaints and grievances, per our Grievance Policy."
            email={companyInfo.grievanceOfficer.email}
            needsConfig={companyInfo.grievanceOfficer.needsConfig}
          />
          <div className="landing-premium-card flex flex-col h-full">
            <div className="landing-premium-card-icon">
              <Clock className="w-5 h-5 text-accent" strokeWidth={2} />
            </div>
            <h3 className="font-display font-bold text-base">Business Hours</h3>
            <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">{companyInfo.businessHours.value}</p>
            <div className="mt-auto pt-4">
              {companyInfo.businessHours.needsConfig && <ConfigRequiredBadge label="Exact hours pending" />}
            </div>
          </div>
        </div>
      </section>

      {/* Office + map */}
      <section className="landing-section bg-slate-50">
        <div className="landing-container grid lg:grid-cols-2 gap-8 items-start">
          <div>
            <h2 className="landing-subsection-title mb-2">Our Office</h2>
            <div className="flex items-start gap-2 text-sm text-muted-foreground mt-3">
              <MapPin className="w-4 h-4 text-accent flex-shrink-0 mt-0.5" />
              {companyInfo.officeAddress.needsConfig ? (
                <div>
                  <span>Okhla, New Delhi, India</span>
                  <div className="mt-1.5">
                    <ConfigRequiredBadge label="Exact address pending" />
                  </div>
                </div>
              ) : (
                <span>{companyInfo.officeAddress.value}</span>
              )}
            </div>
            <div className="flex flex-wrap gap-2.5 mt-5">
              <button type="button" onClick={copyAddress} className="legal-action-btn">
                <Copy className="w-3.5 h-3.5" /> Copy Address
              </button>
              <a
                href={`https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`}
                target="_blank"
                rel="noopener noreferrer"
                className="legal-action-btn"
              >
                <Navigation className="w-3.5 h-3.5" /> Get Directions
              </a>
              <a
                href={`https://www.google.com/maps?q=${lat},${lng}`}
                target="_blank"
                rel="noopener noreferrer"
                className="legal-action-btn"
              >
                <ExternalLink className="w-3.5 h-3.5" /> Open in Google Maps
              </a>
            </div>

            <div className="mt-8">
              <h3 className="font-display font-bold text-sm mb-3">Operating Area</h3>
              <p className="text-xs text-muted-foreground mb-2">Currently serving:</p>
              <ul className="space-y-1.5">
                {companyInfo.operatingCourts.map((court) => (
                  <li key={court} className="flex items-center gap-2 text-sm text-foreground">
                    <Landmark className="w-3.5 h-3.5 text-accent flex-shrink-0" />
                    {court}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <ContactMap />
        </div>

        {/* CTA */}
        <div className="landing-container text-center max-w-xl mx-auto mt-14 pt-10 border-t border-slate-200">
          <h2 className="landing-cta-title">Need assistance?</h2>
          <p className="text-muted-foreground mt-2">Our support team is ready to assist.</p>
          <p className="text-xs text-muted-foreground/80 mt-1">Average response: within one business day.</p>
          <a href={`mailto:${companyInfo.supportEmail.value}`} className="inline-block mt-6">
            <span className="inline-flex items-center gap-2 bg-accent hover:bg-accent/90 text-white font-bold px-6 py-3 rounded-lg transition-colors">
              Contact Support <ArrowRight className="w-4 h-4" />
            </span>
          </a>
        </div>
      </section>
    </MarketingLayout>
  );
}
