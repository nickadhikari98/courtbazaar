import React from "react";
import { Link } from "react-router-dom";

export default function NavbarLogo({ to = "/", className = "" }) {
  return (
    <Link to={to} className={`flex items-center h-10 sm:h-12 shrink-0 ${className}`}>
      <img
        src="/images/cbLogo-navbar.png"
        alt="CourtBazaar™ - India's Premier Legal Operations & Services Platform"
        className="h-full w-auto object-contain"
      />
    </Link>
  );
}
