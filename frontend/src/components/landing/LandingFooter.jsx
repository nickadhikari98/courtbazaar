import React from "react";
import { Link } from "react-router-dom";
import { Mail, Phone, MapPin } from "lucide-react";

const footerColumns = [
  {
    title: "Services",
    links: [
      { label: "Print-Out Service", to: "#services" },
      { label: "Photocopy Services", to: "#services" },
      { label: "Scanning Services", to: "#services" },
      { label: "OCR & Bookmarking", to: "#services" },
      { label: "E-Filing Services", to: "#services" },
      { label: "Proxy Counsel", to: "#services" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "About Us", to: "/about" },
      { label: "How It Works", to: "#how" },
      { label: "Plans & Pricing", to: "#pricing" },
      { label: "Our Network", to: "/network" },
      { label: "Contact Us", to: "/contact" },
    ],
  },
  {
    title: "Legal",
    links: [
      { label: "Privacy Policy", to: "/privacy" },
      { label: "Terms & Conditions", to: "/terms" },
      { label: "Refund Policy", to: "/refund" },
      { label: "KYC Policy", to: "/kyc" },
      { label: "Data Retention Policy", to: "/data-retention" },
    ],
  },
];

const contactInfo = [
  { icon: Mail, label: "support@courtbazaar.com", href: "mailto:support@courtbazaar.com" },
  { icon: MapPin, label: "Delhi, India" },
];

const socialLinks = [
  { icon: "f", href: "https://www.facebook.com/share/18wecnfNK8/", label: "Facebook" },
  { icon: "in", href: "https://www.linkedin.com/company/courtbazaar/", label: "LinkedIn" },
  { icon: "X", href: "https://x.com/court_bazaar", label: "X (Twitter)" },
];

export default function LandingFooter() {
  return (
    <footer id="contact" className="landing-footer">
      <div className="landing-container">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-6 lg:gap-8">
          {/* Logo & Description */}
          <div className="col-span-2 md:col-span-3 lg:col-span-1">
            <Link to="/" className="inline-flex items-center bg-white rounded-lg px-3 py-2 mb-3">
              <img
                src="/images/cbLogo-navbar.png"
                alt="CourtBazaar - India's Premier Legal Operations & Services Platform"
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
                    {link.to.startsWith("#") ? (
                      <a href={link.to} className="landing-footer-link">
                        {link.label}
                      </a>
                    ) : (
                      <Link to={link.to} className="landing-footer-link">
                        {link.label}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}

          {/* Contact Us */}
          <div>
            <h4 className="landing-footer-heading">Contact Us</h4>
            <ul className="space-y-2">
              {contactInfo.map((item) => (
                <li key={item.label} className="flex items-start gap-2 text-sm">
                  <item.icon className="w-4 h-4 text-accent mt-0.5 flex-shrink-0" />
                  {item.href ? (
                    <a href={item.href} className="text-white/80 hover:text-white transition-colors">
                      {item.label}
                    </a>
                  ) : (
                    <span className="text-white/80">{item.label}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="landing-footer-divider" />
        <div className="text-center text-sm text-white/60">
          <p>&copy; {new Date().getFullYear()} LexOrbit Technologies. All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
}
