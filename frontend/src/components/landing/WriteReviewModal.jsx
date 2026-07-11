import React, { useState } from "react";
import { toast } from "sonner";
import { Star } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export default function WriteReviewModal({ open, onOpenChange }) {
  const [rating, setRating] = useState(0);
  const [hovered, setHovered] = useState(0);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!rating) {
      toast.error("Please select a rating before submitting.");
      return;
    }
    setSubmitting(true);
    setTimeout(() => {
      setSubmitting(false);
      toast.success("Thank you for your review! It will appear after moderation.");
      setRating(0);
      onOpenChange(false);
    }, 500);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">Write a Review</DialogTitle>
          <DialogDescription>Share your experience with CourtBazaar.</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm font-semibold text-foreground block mb-2">Your Rating</label>
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  onMouseEnter={() => setHovered(n)}
                  onMouseLeave={() => setHovered(0)}
                  onClick={() => setRating(n)}
                  className="p-0.5"
                  aria-label={`${n} star`}
                >
                  <Star
                    className={`w-7 h-7 transition-colors ${
                      n <= (hovered || rating) ? "fill-accent text-accent" : "text-slate-300"
                    }`}
                  />
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-sm font-semibold text-foreground block mb-1.5">Advocate Name</label>
            <Input placeholder="Enter your name" required />
          </div>

          <div>
            <label className="text-sm font-semibold text-foreground block mb-1.5">Court</label>
            <Input placeholder="e.g. Delhi High Court" />
          </div>

          <div>
            <label className="text-sm font-semibold text-foreground block mb-1.5">Your Review</label>
            <Textarea placeholder="Tell us about your experience..." rows={4} required />
          </div>

          <DialogFooter className="pt-2">
            <Button type="submit" disabled={submitting} className="bg-accent hover:bg-accent/90 font-bold w-full sm:w-auto">
              {submitting ? "Submitting..." : "Submit Review"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
