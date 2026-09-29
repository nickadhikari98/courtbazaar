import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CheckCircle2, ArrowRight } from "lucide-react";
import HeroBadge from "./HeroBadge";
import TrackingWidget from "./TrackingWidget";
import InstantLegalHelpWidget from "./InstantLegalHelpWidget";

const quickSteps = [
  { number: "1", label: "Select Service", desc: "Choose the service you need" },
  { number: "2", label: "Upload Documents", desc: "Upload your files securely" },
  { number: "3", label: "Review & Place Order", desc: "Make payment and we'll handle the rest" },
];

const trustPoints = [
  "Trusted Vendors",
  "Verified Partners",
  "Secure & Reliable",
];

export default function HeroSection() {
  const [chatOpen, setChatOpen] = useState(false);
  const [pendingMessage, setPendingMessage] = useState("");
  const [chatPrompt, setChatPrompt] = useState("");
  const openChat = () => {
    setPendingMessage(chatPrompt.trim());
    setChatPrompt("");
    setChatOpen(true);
  };
  return (
    <section id="hero" className="relative overflow-hidden">
      {/* Subtle grain texture */}
      <div className="absolute inset-0 cb-grain opacity-30" />

      <div className="landing-container relative">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-0 lg:min-h-[650px]">

          {/* Left Content */}
          <div className="flex flex-col justify-start pt-6 pb-8 lg:pt-10 lg:pb-20 lg:pr-12 relative z-10">
            {/* Heading Block */}
            <div className="mb-5">
              <div className="mb-4">
                <HeroBadge>India's First Legal Operations Network & Services</HeroBadge>
              </div>
              <h1 className="landing-hero-title">
                Court Work<br />
                Simplified.<br/>
                <span className="text-accent">Delivered</span>
              </h1>
            </div>

            <p className="landing-hero-subtitle mb-7">
              CourtBazaar™ is your one-stop platform for litigation support — from document processing to court assistance. We handle the operational work so you can focus entirely on winning your cases.
            </p>

            {/* Trust Points */}
            <div className="flex flex-wrap items-center gap-4 mb-8">
              {trustPoints.map((point) => (
                <div key={point} className="flex items-center gap-2 text-sm font-medium">
                  <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                  <span>{point}</span>
                </div>
              ))}
            </div>

            {/* CTAs */}
            <div className="flex flex-wrap gap-3">
              <Link to="/register">
                <Button
                  size="lg"
                  className="bg-primary hover:bg-primary/90 font-bold h-12 px-6"
                >
                  Explore Services
                </Button>
              </Link>
              <TrackingWidget />
            </div>
            <div className="mt-4 w-full max-w-sm space-y-2">
              <Input
                value={chatPrompt}
                onChange={(event) => setChatPrompt(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && openChat()}
                placeholder="Describe your situation, legal issue, or service need..."
                aria-label="Describe your situation, legal issue, or service need"
                className="h-10 w-full rounded-lg border-slate-200 bg-white px-3 text-sm shadow-none placeholder:text-slate-400 focus-visible:ring-accent/30"
                data-testid="instant-legal-help-trigger-input"
              />
              <Button
                type="button"
                onClick={openChat}
                className="h-10 w-full rounded-lg bg-accent px-4 text-sm font-semibold text-white shadow-none hover:bg-accent/90 sm:w-auto"
                data-testid="instant-legal-help-launcher"
              >
                Chat with Instant Legal Help →
              </Button>
            </div>
          </div>

          {/* Right Side - Full Image Area */}
          <div className="relative lg:h-auto lg:absolute lg:right-0 lg:top-0 lg:bottom-0 lg:w-1/2">
            {/* Supreme Court Image - fixed-height box on mobile/tablet so it never
                collides with the step card below it; absolute-fill on desktop
                (unchanged) where the step card floats over it instead. */}
            <div
              className="relative h-[260px] sm:h-[340px] lg:h-full lg:absolute lg:inset-0 rounded-2xl lg:rounded-none lg:rounded-l-3xl overflow-hidden"
              style={{
                backgroundImage: `url('/images/illustrations/Supreme Court illustration.avif')`,
                backgroundSize: 'contain',
                backgroundPosition: 'right 0px top 70px',
                backgroundRepeat: 'no-repeat',
              }}
            >
              {/* Soft white gradient overlay from left */}
              <div
                className="absolute inset-0"
                style={{
                  background: 'linear-gradient(to right, rgba(250,250,250,0.95) 0%, rgba(250,250,250,0.4) 30%, rgba(250,250,250,0.1) 60%, transparent 100%)',
                }}
              />
            </div>

            {/* 3-Step Workflow Card — normal document flow directly below the
                image on mobile/tablet (guarantees no overlap); reverts to the
                original floating overlay pinned to the image's bottom edge
                at lg: and up. */}
            <div className="relative mt-4 lg:mt-0 lg:absolute lg:bottom-5 lg:left-3 lg:right-3 bg-white rounded-xl shadow-xl border border-slate-100 p-4 lg:p-5">
              <h3 className="font-display font-bold text-sm lg:text-base text-center mb-4">
                Place Your Order in 3 Simple Steps
              </h3>
              <div className="grid grid-cols-3 gap-2">
                {quickSteps.map((step, i) => (
                  <div key={step.number} className="relative text-center">
                    {i < quickSteps.length - 1 && (
                      <div className="hidden sm:block absolute top-[18px] lg:top-5 left-[calc(50%+20px)] w-[calc(100%-24px)] border-t-2 border-dashed border-accent/40 z-0">
                        <ArrowRight className="w-3 h-3 text-accent/60 absolute -right-0.5 -top-[7px]" />
                      </div>
                    )}
                    <div className="relative z-10 w-10 h-10 lg:w-11 lg:h-11 rounded-full bg-accent border-2 border-accent flex items-center justify-center mx-auto mb-2 shadow-sm shadow-accent/30">
                      <span className="font-display font-bold text-sm text-white">
                        {step.number}
                      </span>
                    </div>
                    <p className="font-semibold text-xs lg:text-sm">{step.label}</p>
                    <p className="text-2xs lg:text-xs text-muted-foreground mt-0.5 hidden sm:block leading-tight">
                      {step.desc}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
      <InstantLegalHelpWidget open={chatOpen} onClose={() => setChatOpen(false)} initialMessage={pendingMessage} />
    </section>
  );
}
