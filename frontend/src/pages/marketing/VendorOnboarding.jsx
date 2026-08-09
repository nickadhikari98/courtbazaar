import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowRight, TrendingUp, ShieldCheck, Wallet, Users, CheckCircle2 } from "lucide-react";
import Logo from "@/components/shared/Logo";

const benefits = [
  { icon: TrendingUp, t: "Steady order flow", d: "Get matched to advocates across India needing your services daily." },
  { icon: ShieldCheck, t: "KYC & trust badge", d: "Verified vendors get prioritised in auto-matching." },
  { icon: Wallet, t: "Daily settlements", d: "T+1 vendor payout. GST-compliant invoices auto-generated." },
  { icon: Users, t: "No marketing spend", d: "We bring advocates to you. Just focus on quality." },
];

export default function VendorOnboarding() {
  return (
    <div className="min-h-screen bg-background">
      <nav className="sticky top-0 z-30 bg-white/80 backdrop-blur-xl border-b border-border">
        <div className="max-w-7xl mx-auto px-6 lg:px-10 h-16 flex items-center justify-between">
          <Logo size="sm" data-testid="vendor-landing-logo" />
          <Link to="/register"><Button className="bg-primary font-bold" data-testid="vendor-cta-nav">Apply Now <ArrowRight className="w-4 h-4 ml-1" /></Button></Link>
        </div>
      </nav>

      <section className="max-w-7xl mx-auto px-6 lg:px-10 py-16 lg:py-24">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div>
            <div className="cb-overline text-accent">For Print shops & service providers</div>
            <h1 className="font-display font-black text-5xl lg:text-6xl tracking-tighter mt-3 leading-[0.95]">
              Grow your court-shop income with CourtBazaar™.
            </h1>
            <p className="mt-5 text-lg text-muted-foreground font-medium">
              Photocopy. Print. Bind. Stamp. Notarize. We bring 12,400+ advocates straight to your shop. Daily payouts. Zero marketing cost.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link to="/register"><Button size="lg" className="bg-accent h-14 px-8 font-bold" data-testid="vendor-cta-primary">Register your shop <ArrowRight className="w-4 h-4 ml-2" /></Button></Link>
              <Link to="/login"><Button size="lg" variant="outline" className="border-2 h-14 px-8 font-bold" data-testid="vendor-cta-login">Vendor login</Button></Link>
            </div>
            <div className="mt-8 flex flex-wrap gap-4 text-sm font-semibold">
              <div className="flex items-center gap-2"><CheckCircle2 className="w-5 h-5 text-emerald-600" /> 1,200+ shops onboarded</div>
              <div className="flex items-center gap-2"><CheckCircle2 className="w-5 h-5 text-emerald-600" /> ₹2.4Cr+ paid out</div>
            </div>
          </div>
          <div className="aspect-square rounded-3xl overflow-hidden border border-border relative">
            <img src="https://images.unsplash.com/photo-1516409590654-e8d51fc2d25c?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200" alt="" className="w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-primary/40 to-transparent"></div>
          </div>
        </div>
      </section>

      <section className="bg-primary text-white py-20">
        <div className="max-w-7xl mx-auto px-6 lg:px-10">
          <div className="cb-overline text-accent">Why join</div>
          <h2 className="font-display font-black text-4xl lg:text-5xl tracking-tighter mt-2">Built for India's court vendors.</h2>
          <div className="mt-10 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {benefits.map((b) => (
              <div key={b.t}>
                <div className="w-12 h-12 rounded-xl bg-accent/20 text-accent flex items-center justify-center mb-3"><b.icon className="w-6 h-6" /></div>
                <div className="font-display font-bold text-xl">{b.t}</div>
                <div className="text-white/70 font-medium text-sm mt-1">{b.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="max-w-7xl mx-auto px-6 lg:px-10 py-20">
        <div className="bg-accent text-white rounded-3xl p-10 lg:p-14">
          <h2 className="font-display font-black text-4xl tracking-tighter leading-tight">Onboarding in 3 steps.</h2>
          <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              ["01", "Register", "Sign up with phone or email. Choose 'Vendor' role."],
              ["02", "Complete KYC", "PAN, GST, Aadhaar, bank details. Map your courts & services."],
              ["03", "Start earning", "Approved in 24 hrs. Orders auto-route to your dashboard."],
            ].map(([n, t, d]) => (
              <div key={n}>
                <div className="font-display font-black text-5xl">{n}</div>
                <div className="font-display font-bold text-2xl mt-2">{t}</div>
                <div className="text-white/80 mt-1 text-sm font-medium">{d}</div>
              </div>
            ))}
          </div>
          <Link to="/register"><Button size="lg" className="mt-8 bg-white text-accent hover:bg-white/90 h-14 px-8 font-bold" data-testid="vendor-cta-bottom">Apply now <ArrowRight className="w-4 h-4 ml-2" /></Button></Link>
        </div>
      </section>
    </div>
  );
}
