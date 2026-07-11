import React, { useState } from "react";
import { MapPin, Mail, Briefcase, Scale, Printer, FileCog, Bike } from "lucide-react";
import RoleSelectModal from "./join/RoleSelectModal";
import {
  proxyCounselSections, counselSections, vendorSections, partnerSections, agentSections,
} from "./join/roleFormData";

const vendorRoles = [
  { key: "vendor", label: "Join as Vendor", icon: Printer, description: "Printing, photocopy & scanning services" },
  { key: "partner", label: "Join as Partner", icon: FileCog, description: "E-filing services for advocates" },
  { key: "agent", label: "Join as Agent", icon: Bike, description: "In-court document delivery & collection" },
];

const vendorForms = {
  vendor: { title: "Join as Printing Vendor", description: "Partner with CourtBazaar and grow your business.", sections: vendorSections },
  partner: { title: "Join as E-Filing Partner", description: "Provide e-filing services to advocates across India.", sections: partnerSections },
  agent: { title: "Join as Court Premises Delivery Partner", description: "Document delivery & collection within court premises. No vehicle required.", sections: agentSections },
};

const counselRoles = [
  { key: "counsel", label: "Join as Counsel", icon: Scale, description: "Empanel as an advocate on CourtBazaar" },
  { key: "proxyCounsel", label: "Join as Proxy Counsel", image: "/images/illustrations/proxy-counsel-badge.png", description: "Appear on behalf of advocates across Delhi courts" },
];

const counselForms = {
  counsel: { title: "Join as Counsel", description: "Empanel with CourtBazaar and receive briefed matters.", sections: counselSections },
  proxyCounsel: { title: "Join as Proxy Counsel", description: "Fill in your details to become a verified Proxy Counsel on CourtBazaar.", sections: proxyCounselSections },
};

export default function UtilityBar({
  location = "Delhi, India",
  email = "support@courtbazaar.com"
}) {
  const [vendorOpen, setVendorOpen] = useState(false);
  const [counselOpen, setCounselOpen] = useState(false);

  return (
    <div className="landing-utility-bar">
      <div className="landing-container flex items-center justify-between h-9">
        <div className="flex items-center gap-5">
          <span className="landing-utility-link">
            <MapPin className="w-3.5 h-3.5" strokeWidth={2} />
            <span>{location}</span>
          </span>
          <a href={`mailto:${email}`} className="landing-utility-link">
            <Mail className="w-3.5 h-3.5" strokeWidth={2} />
            <span>{email}</span>
          </a>
        </div>
        <div className="hidden sm:flex items-center gap-3">
          <button
            type="button"
            onClick={() => setVendorOpen(true)}
            className="landing-utility-cta"
          >
            <Briefcase className="w-3.5 h-3.5" strokeWidth={2} />
            <span>Join as Vendor / Delievery Partner / E-filling Agent</span>
          </button>
          <button
            type="button"
            onClick={() => setCounselOpen(true)}
            className="landing-utility-cta landing-utility-cta--highlight"
          >
            <Scale className="w-3.5 h-3.5" strokeWidth={2} />
            <span>Join as Counsel / Proxy Counsel</span>
          </button>
        </div>
      </div>

      <RoleSelectModal
        open={vendorOpen}
        onOpenChange={setVendorOpen}
        heading="Select Your Role"
        subheading="Choose how you'd like to partner with CourtBazaar."
        roles={vendorRoles}
        forms={vendorForms}
      />
      <RoleSelectModal
        open={counselOpen}
        onOpenChange={setCounselOpen}
        heading="Select Your Role"
        subheading="Choose how you'd like to join CourtBazaar's legal network."
        roles={counselRoles}
        forms={counselForms}
      />
    </div>
  );
}
