import React, { useEffect, useRef, useState } from "react";
import { Star, PenLine, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import WriteReviewModal from "./WriteReviewModal";
import { listApprovedReviews } from "@/lib/reviewsApi";

// Fallback shown only until at least one admin-approved review exists —
// once real reviews are live, these are replaced entirely (see
// ReviewsSection's effect below). Not a permanent display; kept only so the
// section isn't empty on a fresh install with zero approved reviews yet.
const FALLBACK_TESTIMONIALS = [
  {
    name: "Adv. Priya Mehta",
    court: "Delhi High Court",
    text: "Civil & Commercial Litigation. The platform is extremely easy to use. Uploading documents took less than a minute, and the team handled scanning, bookmarking, and document preparation efficiently. This service is particularly useful for busy advocates managing multiple matters.",
    photoUrl: null,
    rating: 5,
  },
  {
    name: "Adv. Arjun Verma",
    court: "Delhi High Court",
    text: "High Court Practitioner. What I appreciate most is the convenience. CourtBazaar combines printing, photocopying, OCR, and filing assistance in one place. It reduces coordination with multiple vendors and helps me focus on legal work rather than administrative tasks.",
    photoUrl: null,
    rating: 5,
  },
  {
    name: "Adv. Neha Gupta",
    court: "Delhi High Court",
    text: "Independent Advocate. As a young practitioner, I need cost-effective solutions. CourtBazaar's package pricing is transparent and affordable. The chamber delivery option is a major advantage and saves valuable time during busy filing periods.",
    photoUrl: null,
    rating: 5,
  },
];

const AUTO_SCROLL_INTERVAL_MS = 4000;

function Stars({ count = 5 }) {
  return (
    <div className="flex gap-0.5">
      {Array.from({ length: count }).map((_, i) => (
        <Star key={i} className="w-4 h-4 fill-accent text-accent" />
      ))}
    </div>
  );
}

/* Reserves the same circular slot a real uploaded review photo will occupy —
   shows a placeholder avatar until `photoUrl` is present, so swapping in
   real photos later is a pure data change with zero layout change. */
function ReviewAvatar({ photoUrl, name }) {
  if (photoUrl) {
    return <img src={photoUrl} alt={name} className="w-12 h-12 rounded-full object-cover flex-shrink-0" />;
  }
  return (
    <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center flex-shrink-0">
      <UserRound className="w-6 h-6 text-slate-400" strokeWidth={1.75} />
    </div>
  );
}

export default function ReviewsSection() {
  const [writeOpen, setWriteOpen] = useState(false);
  const [paused, setPaused] = useState(false);
  const [approvedReviews, setApprovedReviews] = useState(null); // null = not loaded yet
  const trackRef = useRef(null);

  const loadApprovedReviews = () => {
    listApprovedReviews()
      .then((reviews) => setApprovedReviews(reviews.map((r) => ({
        id: r.review_id,
        name: r.name,
        court: r.organization || r.designation || "",
        text: r.review,
        photoUrl: r.photo_url,
        rating: r.rating,
      }))))
      .catch(() => setApprovedReviews([])); // fail-soft: fall back to placeholders, not an error state
  };

  useEffect(() => { loadApprovedReviews(); }, []);

  // Real approved reviews replace the placeholders entirely once at least
  // one exists; until then (fresh install, or fetch still pending/failed)
  // the placeholders keep the section from looking empty.
  const testimonials = approvedReviews && approvedReviews.length > 0 ? approvedReviews : FALLBACK_TESTIMONIALS;

  // Auto-advance one card at a time; smooth via native scroll-snap, wraps
  // back to the start at the end. Pauses on hover/focus and whenever the
  // write-review modal is open.
  useEffect(() => {
    if (paused || writeOpen || testimonials.length <= 1) return undefined;
    const id = setInterval(() => {
      const el = trackRef.current;
      if (!el) return;
      const card = el.querySelector("[data-review-card]");
      const step = card ? card.getBoundingClientRect().width + 24 /* gap-6 */ : el.clientWidth;
      const atEnd = el.scrollLeft + el.clientWidth >= el.scrollWidth - 4;
      el.scrollTo({ left: atEnd ? 0 : el.scrollLeft + step, behavior: "smooth" });
    }, AUTO_SCROLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [paused, writeOpen, testimonials.length]);

  return (
    <section id="reviews" className="landing-section bg-slate-50">
      <div className="landing-container">
        <div className="landing-section-header">
          <p className="font-display font-bold text-xl sm:text-2xl text-accent mb-2">
            Trusted by India's Legal Community
          </p>
          <h2 className="landing-section-title">From the Bar to the Bench.</h2>
          <p className="landing-section-subtitle">
            Real feedback from advocates who use CourtBazaar™ every day.
          </p>
        </div>

        <div
          ref={trackRef}
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
          onFocus={() => setPaused(true)}
          onBlur={() => setPaused(false)}
          className="landing-review-track flex gap-6 overflow-x-auto cb-scroll snap-x snap-mandatory scroll-smooth pb-2 -mx-6 px-6 sm:mx-0 sm:px-0"
        >
          {testimonials.map((t) => (
            <div
              key={t.id || t.name}
              data-review-card
              className="landing-review-card snap-start flex-shrink-0 flex flex-col w-[85%] sm:w-[calc(50%-12px)] lg:w-[calc(33.333%-16px)]"
            >
              <Stars count={t.rating || 5} />
              <p className="text-sm text-slate-700 leading-relaxed mt-4 flex-1 line-clamp-5">"{t.text}"</p>
              <div className="mt-auto pt-4 border-t border-slate-100 flex items-center gap-3">
                <ReviewAvatar photoUrl={t.photoUrl} name={t.name} />
                <div>
                  <div className="font-display font-bold text-sm">{t.name}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">{t.court}</div>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="text-center mt-10">
          <Button
            onClick={() => setWriteOpen(true)}
            className="bg-accent hover:bg-accent/90 active:bg-accent text-white font-bold rounded-lg shadow-sm hover:shadow-lg hover:-translate-y-0.5 active:translate-y-0 active:shadow-sm transition-all duration-200"
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
