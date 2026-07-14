import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ChevronDown, LogIn, Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import NavbarLogo from "./NavbarLogo";
import MegaMenu from "./MegaMenu";
import TourSideTab from "./TourSideTab";

const navLinks = [
  { label: "Home", to: "/" },
  { label: "How It Works", to: "#how" },
  { label: "Package Plans", to: "#pricing" },
  { label: "Counsel / Proxy Counsel", to: "#services" },
  { label: "Courts Coverage", to: "#coverage" },
  { label: "About Us", to: "/about" },
  { label: "Contact Us", to: "/contact" },
];

export default function LandingNav({ onTakeTour }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 10);
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <>
    <nav className={cn("landing-nav", scrolled && "scrolled")}>
      <div className="landing-nav-container">
        {/* Logo */}
        <NavbarLogo />

        {/* Desktop Nav */}
        <div className="hidden lg:flex items-center gap-1">
          {/* Services Mega Menu */}
          <div className="relative group">
            <button className="landing-nav-link flex items-center gap-1 px-3 py-2">
              Services <ChevronDown className="w-3.5 h-3.5" />
            </button>
            <MegaMenu />
          </div>

          {navLinks.slice(1).map((link) => (
            <a
              key={link.label}
              href={link.to}
              className="landing-nav-link px-3 py-2"
            >
              {link.label}
            </a>
          ))}
        </div>

        {/* Auth Buttons */}
        <div className="hidden lg:flex items-center gap-2">
          <Link to="/login">
            <Button
              className="bg-accent hover:bg-accent/90 active:bg-accent text-white font-bold rounded-lg shadow-sm hover:shadow-lg hover:-translate-y-0.5 active:translate-y-0 active:shadow-sm transition-all duration-200"
            >
              Login <LogIn className="w-4 h-4 ml-1" />
            </Button>
          </Link>
        </div>

        {/* Mobile Menu Button */}
        <button
          className="lg:hidden p-2"
          onClick={() => setMobileOpen(!mobileOpen)}
        >
          {mobileOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>

      {/* Mobile Menu */}
      {mobileOpen && (
        <div className="lg:hidden border-t border-border bg-white p-4">
          <div className="space-y-2">
            {navLinks.map((link) => (
              <a
                key={link.label}
                href={link.to}
                className="block py-2 font-semibold text-foreground"
                onClick={() => setMobileOpen(false)}
              >
                {link.label}
              </a>
            ))}
            <Link to="/login" onClick={() => setMobileOpen(false)}>
              <Button className="w-full bg-accent hover:bg-accent/90 active:bg-accent text-white font-bold rounded-lg shadow-sm hover:shadow-lg active:shadow-sm transition-all duration-200 mt-2">
                Login <LogIn className="w-4 h-4 ml-1" />
              </Button>
            </Link>
          </div>
        </div>
      )}
    </nav>
    {!mobileOpen && <TourSideTab onTakeTour={onTakeTour} />}
    </>
  );
}
