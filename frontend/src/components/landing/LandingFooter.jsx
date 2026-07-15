import React from "react";
import { Link } from "react-router-dom";
import ComingSoonBadge from "@/components/shared/ComingSoonBadge";

const footerColumns = [
  {
    title: "Company",
    links: [
      { label: "Careers", soon: true },
      { label: "Blog", soon: true },
    ],
  },
  {
    title: "Services",
    links: [
      { label: "Printing", to: "#services" },
      { label: "Scanning", to: "#services" },
      { label: "OCR", to: "#services" },
      { label: "E-Filing", to: "#services" },
      { label: "Proxy Counsel", to: "#services" },
      { label: "Packages", to: "/pricing" },
    ],
  },
  {
    title: "Resources",
    links: [
      { label: "About", to: "/about" },
      { label: "Trust Center", to: "/trust" },
      { label: "Security", to: "/security" },
      { label: "Contact", to: "/contact" },
    ],
  },
  {
    title: "Legal",
    links: [
      { label: "Terms", to: "/legal/terms" },
      { label: "Privacy", to: "/legal/privacy" },
      { label: "Refund Policy", to: "/legal/refund" },
      { label: "Cookie Policy", to: "/legal/cookies" },
      { label: "Disclaimer", to: "/legal/disclaimer" },
      { label: "Confidentiality Policy", to: "/legal/confidentiality" },
      { label: "Grievance Policy", to: "/legal/grievance" },
    ],
  },
  {
    title: "Support",
    links: [
      { label: "Help Center", soon: true },
      { label: "Contact Support", to: "/contact" },
      { label: "FAQs", soon: true },
    ],
  },
];

const secondaryLinks = [
  { label: "Privacy", to: "/legal/privacy" },
  { label: "Terms", to: "/legal/terms" },
  { label: "Cookies", to: "/legal/cookies" },
  { label: "Refund", to: "/legal/refund" },
  { label: "Security", to: "/security" },
  { label: "Trust Center", to: "/trust" },
];

const socialLinks = [
  { icon: "f", href: "https://www.facebook.com/share/18wecnfNK8/", label: "Facebook" },
  { icon: "in", href: "https://www.linkedin.com/company/courtbazaar/", label: "LinkedIn" },
  { icon: "X", href: "https://x.com/court_bazaar", label: "X (Twitter)" },
];

function FooterLink({ link }) {
  if (link.soon) {
    return (
      <span className="landing-footer-link landing-footer-link--soon" aria-disabled="true">
        {link.label}
        <ComingSoonBadge variant="inline" label="Soon" className="ml-1.5" />
      </span>
    );
  }
  if (link.to.startsWith("#")) {
    return (
      <a href={link.to} className="landing-footer-link">
        {link.label}
      </a>
    );
  }
  return (
    <Link to={link.to} className="landing-footer-link">
      {link.label}
    </Link>
  );
}

export default function LandingFooter() {
  return (
    <footer id="contact" className="landing-footer">
      <div className="landing-container">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-6 lg:gap-8">
          {/* Logo & Description */}
          <div className="col-span-2 md:col-span-3 lg:col-span-1">
            <Link to="/" className="inline-flex items-center bg-white rounded-lg px-3 py-2 mb-3">
              <img
                src="/images/cbLogo-navbar.png"
                alt="CourtBazaar™ - India's Premier Legal Operations & Services Platform"
                className="h-8 w-auto object-contain"
              />
            </Link>
            <p className="text-white/70 text-sm leading-relaxed">
              India's Legal Operations<br />Network & Services Platform
            </p>
            {/* Social Links */}
            <div className="flex gap-2 mt-3">
              {socialLinks.map((social) => (
                <a
                  key={social.label}
                  href={social.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="landing-footer-social"
                  aria-label={social.label}
                >
                  <span className="text-xs font-bold">{social.icon}</span>
                </a>
              ))}
            </div>
          </div>

          {/* Footer Columns */}
          {footerColumns.map((column) => (
            <div key={column.title}>
              <h4 className="landing-footer-heading">{column.title}</h4>
              <ul className="space-y-1">
                {column.links.map((link) => (
                  <li key={link.label}>
                    <FooterLink link={link} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom Bar */}
        <div className="landing-footer-divider" />
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <p className="text-sm text-white/60 text-center sm:text-left">
            &copy; {new Date().getFullYear()} CourtBazaar&trade; &middot; Powered by LexOrbit Technologies
            <br className="sm:hidden" />
            <span className="hidden sm:inline"> &middot; </span>
            India's First Legal Operations Network &amp; Services Platform
          </p>
          <nav aria-label="Legal links" className="flex flex-wrap justify-center gap-x-4 gap-y-1.5">
            {secondaryLinks.map((link) => (
              <Link key={link.label} to={link.to} className="text-xs text-white/50 hover:text-white/80 transition-colors">
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
      </div>
    </footer>
  );
}
