import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Scale, ArrowRight, CheckCircle2, Zap, ShieldCheck, MapPin, Clock,
  Printer, FileText, Gavel, Stamp, Package, BookOpen, Building2, Sparkles, Truck, Star
} from "lucide-react";

const services = [
  { icon: Printer, name: "Photocopy & Print", color: "bg-amber-50", iconColor: "text-amber-700" },
  { icon: BookOpen, name: "Binding & Court Sets", color: "bg-emerald-50", iconColor: "text-emerald-700" },
  { icon: Gavel, name: "E-Filing Services", color: "bg-blue-50", iconColor: "text-blue-700" },
  { icon: FileText, name: "Legal Typing", color: "bg-rose-50", iconColor: "text-rose-700" },
  { icon: Stamp, name: "Notary & Stamps", color: "bg-purple-50", iconColor: "text-purple-700" },
  { icon: Package, name: "Court Bundle Prep", color: "bg-orange-50", iconColor: "text-orange-700" },
  { icon: Truck, name: "Court Runners", color: "bg-cyan-50", iconColor: "text-cyan-700" },
  { icon: Sparkles, name: "AI Doc Intelligence", color: "bg-yellow-50", iconColor: "text-yellow-700" },
];

const stats = [
  { value: "1,200+", label: "Verified Vendors" },
  { value: "850+", label: "Courts Covered" },
  { value: "28", label: "States & UTs" },
  { value: "30s", label: "To Place an Order" },
];

const testimonials = [
  { name: "Adv. Rajesh Khanna", court: "Delhi High Court", text: "Sent a 400-page paper book from Bengaluru to Delhi HC in under 24 hours. CourtBazaar changed my practice." },
  { name: "M/s Sinha & Associates", court: "Bombay HC", text: "We file at 7 courts simultaneously. The vendor network and AI defect checker save us 20+ hours every week." },
  { name: "Adv. Meera Iyer", court: "Madras HC", text: "From OCR to court delivery, one dashboard. The pricing transparency and GST invoices are gold." },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-background">
      {/* Nav */}
      <nav className="sticky top-0 z-30 bg-white/80 backdrop-blur-xl border-b border-border">
        <div className="max-w-7xl mx-auto px-6 lg:px-10 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5" data-testid="landing-logo">
            <div className="w-9 h-9 bg-primary rounded-lg flex items-center justify-center">
              <Scale className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="font-display font-black text-lg tracking-tight leading-none">CourtBazaar</div>
              <div className="text-[9px] uppercase tracking-[0.2em] text-muted-foreground font-bold">India</div>
            </div>
          </Link>
          <div className="hidden md:flex items-center gap-7 text-sm font-semibold text-muted-foreground">
            <a href="#services" className="hover:text-foreground">Services</a>
            <a href="#how" className="hover:text-foreground">How it Works</a>
            <a href="#coverage" className="hover:text-foreground">Court Coverage</a>
            <Link to="/vendor-signup" className="hover:text-foreground" data-testid="nav-become-vendor">For Vendors</Link>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/login"><Button variant="ghost" className="font-semibold" data-testid="nav-login-btn">Login</Button></Link>
            <Link to="/register">
              <Button className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold" data-testid="nav-signup-btn">
                Get Started <ArrowRight className="w-4 h-4 ml-1" />
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 cb-grain opacity-40"></div>
        <div className="max-w-7xl mx-auto px-6 lg:px-10 pt-16 pb-20 lg:pt-28 lg:pb-32 relative">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
            <div className="lg:col-span-7 space-y-7">
              <Badge className="bg-accent/10 text-accent border-0 px-3 py-1 font-bold tracking-wide" data-testid="hero-badge">
                <Zap className="w-3 h-3 mr-1" /> INDIA'S #1 LEGAL OPERATIONS NETWORK
              </Badge>
              <h1 className="font-display font-black text-5xl sm:text-6xl lg:text-7xl leading-[0.95] tracking-tighter">
                Every court service.<br/>
                <span className="text-accent">One advocate dashboard.</span>
              </h1>
              <p className="text-lg sm:text-xl text-muted-foreground max-w-2xl font-medium leading-relaxed">
                Upload documents from anywhere in India, choose a court, and get photocopy, binding, e-filing, notary, stamping & delivery handled by verified vendors at <strong className="text-foreground">the target court</strong>. Place an order in 30 seconds.
              </p>
              <div className="flex flex-wrap gap-3">
                <Link to="/register">
                  <Button size="lg" className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold h-14 px-8 text-base shadow-lg" data-testid="hero-cta-primary">
                    Start as Advocate <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </Link>
                <Link to="/vendor-signup">
                  <Button variant="outline" size="lg" className="font-bold h-14 px-8 text-base border-2" data-testid="hero-cta-vendor">
                    List Your Shop
                  </Button>
                </Link>
              </div>
              <div className="flex flex-wrap items-center gap-6 pt-4">
                <div className="flex items-center gap-2 text-sm">
                  <ShieldCheck className="w-5 h-5 text-emerald-600" />
                  <span className="font-semibold">KYC Verified Vendors</span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                  <span className="font-semibold">GST Compliant Invoices</span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <Clock className="w-5 h-5 text-emerald-600" />
                  <span className="font-semibold">Real-time Tracking</span>
                </div>
              </div>
            </div>
            <div className="lg:col-span-5 relative">
              <div className="relative rounded-3xl overflow-hidden border border-border shadow-2xl aspect-[4/5]">
                <img src="https://images.unsplash.com/photo-1739512267566-7b2f3a2d29af?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200" alt="Indian Court" className="w-full h-full object-cover" />
                <div className="absolute inset-0 bg-gradient-to-t from-primary/60 via-transparent to-transparent"></div>
                <div className="absolute bottom-6 left-6 right-6 bg-white/95 backdrop-blur-xl rounded-2xl p-5 shadow-lg">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-2.5 h-2.5 bg-emerald-500 rounded-full live-dot"></div>
                    <span className="cb-overline text-emerald-700">Live order</span>
                  </div>
                  <div className="font-display font-bold text-lg leading-tight">Paper book → Patiala House Court</div>
                  <div className="text-xs text-muted-foreground mt-1 font-medium">Vendor: Sharma Xerox · ETA 14 min · ₹847</div>
                </div>
              </div>
              {/* floating badge */}
              <div className="absolute -top-4 -left-4 bg-white border border-border rounded-xl px-4 py-3 shadow-xl">
                <div className="text-2xl font-display font-black">4.9 <Star className="inline w-5 h-5 text-accent fill-accent -mt-1" /></div>
                <div className="text-xs text-muted-foreground font-semibold">12,400+ Advocates</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="border-y border-border bg-secondary/30">
        <div className="max-w-7xl mx-auto px-6 lg:px-10 py-10 grid grid-cols-2 md:grid-cols-4 gap-6">
          {stats.map((s) => (
            <div key={s.label} className="text-center" data-testid={`stat-${s.label.toLowerCase().replace(/\s+/g, '-')}`}>
              <div className="font-display font-black text-4xl lg:text-5xl text-primary tracking-tighter">{s.value}</div>
              <div className="cb-overline mt-1">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Services Bento */}
      <section id="services" className="max-w-7xl mx-auto px-6 lg:px-10 py-20 lg:py-28">
        <div className="max-w-3xl mb-12">
          <div className="cb-overline text-accent">Marketplace categories</div>
          <h2 className="font-display font-black text-4xl lg:text-5xl mt-3 tracking-tighter">
            Every court support service, in one tap.
          </h2>
          <p className="mt-4 text-muted-foreground text-lg font-medium">
            From a single black & white photocopy to a 600-page paper book, we orchestrate the entire workflow with verified local vendors at every court.
          </p>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {services.map((s, i) => (
            <div key={s.name} className="bento-card p-6 group cursor-pointer" data-testid={`service-tile-${i}`}>
              <div className={`w-12 h-12 rounded-xl ${s.color} flex items-center justify-center mb-4`}>
                <s.icon className={`w-6 h-6 ${s.iconColor}`} strokeWidth={2} />
              </div>
              <div className="font-display font-bold text-lg leading-tight">{s.name}</div>
              <div className="text-xs text-muted-foreground mt-2 font-semibold group-hover:text-accent transition-colors">
                Browse →
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="bg-primary text-white py-20 lg:py-28">
        <div className="max-w-7xl mx-auto px-6 lg:px-10">
          <div className="max-w-3xl mb-14">
            <div className="cb-overline text-accent">How CourtBazaar works</div>
            <h2 className="font-display font-black text-4xl lg:text-5xl mt-3 tracking-tighter">
              Sit in Bengaluru. File in Delhi.<br/>In 30 seconds.
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
            {[
              { n: "01", t: "Upload", d: "Drag-drop PDFs, docs, scans. AI checks for filing readiness." },
              { n: "02", t: "Pick Court", d: "Choose state → court complex. Cascading from 28 states." },
              { n: "03", t: "Auto Match", d: "Verified vendor at destination court accepts your order." },
              { n: "04", t: "Track & Deliver", d: "Live status. Chamber, court, or pickup. GST invoice." },
            ].map((step) => (
              <div key={step.n} className="space-y-3" data-testid={`step-${step.n}`}>
                <div className="font-display font-black text-6xl text-accent tracking-tighter">{step.n}</div>
                <div className="font-display font-bold text-2xl">{step.t}</div>
                <div className="text-white/70 font-medium">{step.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Coverage */}
      <section id="coverage" className="max-w-7xl mx-auto px-6 lg:px-10 py-20 lg:py-28">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          <div>
            <div className="cb-overline text-accent">Pan-India court coverage</div>
            <h2 className="font-display font-black text-4xl lg:text-5xl mt-3 tracking-tighter">
              Supreme Court to taluk courts. We're there.
            </h2>
            <p className="mt-5 text-muted-foreground text-lg font-medium leading-relaxed">
              From the Supreme Court of India, 25 High Courts, NCLT & DRT benches, to over 700 district courts and consumer forums — CourtBazaar's verified vendor network handles your work at the source.
            </p>
            <div className="mt-8 grid grid-cols-2 gap-4">
              {[
                { label: "Supreme Court", c: "1" },
                { label: "High Courts", c: "25" },
                { label: "District Courts", c: "720+" },
                { label: "NCLT / DRT Benches", c: "42" },
              ].map((x) => (
                <div key={x.label} className="bg-white border border-border rounded-xl p-5">
                  <div className="font-display font-black text-3xl tracking-tighter">{x.c}</div>
                  <div className="cb-overline mt-1">{x.label}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="relative rounded-3xl overflow-hidden aspect-square border border-border">
            <img src="https://images.unsplash.com/photo-1593115057322-e94b77572f20?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200" alt="Court gavel" className="w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-tr from-primary/40 via-transparent to-accent/20"></div>
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="bg-secondary/30 border-y border-border py-20 lg:py-28">
        <div className="max-w-7xl mx-auto px-6 lg:px-10">
          <div className="text-center mb-12">
            <div className="cb-overline text-accent">Trusted by India's legal community</div>
            <h2 className="font-display font-black text-4xl lg:text-5xl mt-3 tracking-tighter">From the bar to the bench.</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {testimonials.map((t, i) => (
              <div key={i} className="bento-card p-7" data-testid={`testimonial-${i}`}>
                <div className="flex gap-0.5 mb-4">
                  {[1,2,3,4,5].map(s => <Star key={s} className="w-4 h-4 text-accent fill-accent" />)}
                </div>
                <p className="text-foreground/90 font-medium leading-relaxed mb-5">"{t.text}"</p>
                <div className="text-sm font-display font-bold">{t.name}</div>
                <div className="text-xs text-muted-foreground font-semibold">{t.court}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-7xl mx-auto px-6 lg:px-10 py-20">
        <div className="bg-primary text-white rounded-3xl p-10 lg:p-16 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-1/2 h-full cb-grain opacity-30"></div>
          <div className="relative max-w-3xl">
            <h2 className="font-display font-black text-4xl lg:text-6xl tracking-tighter leading-[0.95]">
              Your time is worth more than running between courts.
            </h2>
            <p className="mt-6 text-white/80 text-lg font-medium">
              Join 12,400+ advocates and law firms who delegate every court chore to CourtBazaar.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/register">
                <Button size="lg" className="bg-accent hover:bg-accent/90 text-white font-bold h-14 px-8 text-base" data-testid="footer-cta-primary">
                  Start Free <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </Link>
              <Link to="/vendor-signup">
                <Button size="lg" variant="outline" className="border-white text-white bg-transparent hover:bg-white hover:text-primary font-bold h-14 px-8 text-base" data-testid="footer-cta-vendor">
                  Partner as Vendor
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border bg-white py-10">
        <div className="max-w-7xl mx-auto px-6 lg:px-10 flex flex-col md:flex-row justify-between gap-6 text-sm text-muted-foreground">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
              <Scale className="w-4 h-4 text-white" />
            </div>
            <span className="font-display font-black text-base text-foreground">CourtBazaar</span>
            <span className="ml-2">© 2026 · India's Legal Marketplace</span>
          </div>
          <div className="flex flex-wrap gap-5 font-semibold">
            <a href="#" className="hover:text-foreground">Privacy</a>
            <a href="#" className="hover:text-foreground">Terms</a>
            <a href="#" className="hover:text-foreground">GST Compliance</a>
            <a href="#" className="hover:text-foreground">Contact</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
