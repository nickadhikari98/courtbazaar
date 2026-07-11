import React, { useState } from "react";
import { Star, PenLine } from "lucide-react";
import { Button } from "@/components/ui/button";
import WriteReviewModal from "./WriteReviewModal";

const testimonials = [
  {
    name: "Adv. Priya Mehta",
    court: "Delhi High Court",
    text: "Civil & Commercial Litigation. The platform is extremely easy to use. Uploading documents took less than a minute, and the team handled scanning, bookmarking, and document preparation efficiently. This service is particularly useful for busy advocates managing multiple matters.",
  },
  {
    name: "Adv. Arjun Verma",
    court: "Delhi High Court",
    text: "High Court Practitioner. What I appreciate most is the convenience. CourtBazaar combines printing, photocopying, OCR, and filing assistance in one place. It reduces coordination with multiple vendors and helps me focus on legal work rather than administrative tasks.",
  },
  {
    name: "Adv. Neha Gupta",
    court: "Delhi High Court",
    text: "Independent Advocate. As a young practitioner, I need cost-effective solutions. CourtBazaar's package pricing is transparent and affordable. The chamber delivery option is a major advantage and saves valuable time during busy filing periods.",
  },
];

function Stars({ count = 5 }) {
  return (
    <div className="flex gap-0.5">
      {Array.from({ length: count }).map((_, i) => (
        <Star key={i} className="w-4 h-4 fill-accent text-accent" />
      ))}
    </div>
  );
}

export default function ReviewsSection() {
  const [writeOpen, setWriteOpen] = useState(false);

  return (
    <section id="reviews" className="landing-section bg-slate-50">
      <div className="landing-container">
        <div className="landing-section-header">
          <p className="font-display font-bold text-xl sm:text-2xl text-accent mb-2">
            Trusted by India's Legal Community
          </p>
          <h2 className="landing-section-title">From the Bar to the Bench.</h2>
          <p className="landing-section-subtitle">
            Real feedback from advocates who use CourtBazaar every day.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {testimonials.map((t) => (
            <div key={t.name} className="landing-review-card">
              <Stars />
              <p className="text-sm text-slate-700 leading-relaxed mt-4">"{t.text}"</p>
              <div className="mt-5 pt-4 border-t border-slate-100">
                <div className="font-display font-bold text-sm">{t.name}</div>
                <div className="text-xs text-muted-foreground mt-0.5">{t.court}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="text-center mt-10">
          <Button
            onClick={() => setWriteOpen(true)}
            variant="outline"
            className="font-bold border-2"
          >
            <PenLine className="w-4 h-4 mr-2" />
            Write a Review
          </Button>
        </div>
      </div>

      <WriteReviewModal open={writeOpen} onOpenChange={setWriteOpen} />
    </section>
  );
}
