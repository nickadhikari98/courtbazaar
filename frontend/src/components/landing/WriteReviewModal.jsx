import React, { useEffect, useId, useState } from "react";
import { toast } from "sonner";
import { Star, UploadCloud, X, RefreshCw } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { submitReview } from "@/lib/reviewsApi";

const MAX_PHOTO_SIZE = 5 * 1024 * 1024; // 5MB
// Kept in sync with the backend's ALLOWED_UPLOAD_CONTENT_TYPES (server.py) —
// webp isn't accepted there, so it's not offered here either.
const ALLOWED_PHOTO_TYPES = ["image/jpeg", "image/png"];

export default function WriteReviewModal({ open, onOpenChange }) {
  const [rating, setRating] = useState(5);
  const [hovered, setHovered] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [photo, setPhoto] = useState(null);
  const [photoPreview, setPhotoPreview] = useState(null);
  const [name, setName] = useState("");
  const [court, setCourt] = useState("");
  const [reviewText, setReviewText] = useState("");
  const photoInputId = useId();

  // Preview URL is session-only, never persisted — revoke on unmount so we
  // don't leak blob memory (mirrors FieldKit's FileField cleanup pattern).
  useEffect(() => () => {
    if (photoPreview) URL.revokeObjectURL(photoPreview);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handlePhotoChange = (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!ALLOWED_PHOTO_TYPES.includes(file.type)) {
      toast.error("Please upload a JPG or PNG image.");
      return;
    }
    if (file.size > MAX_PHOTO_SIZE) {
      toast.error("Image must be under 5MB.");
      return;
    }
    setPhoto(file);
    setPhotoPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(file);
    });
  };

  const removePhoto = () => {
    setPhotoPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setPhoto(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!rating) {
      toast.error("Please select a rating before submitting.");
      return;
    }
    if (!name.trim() || !reviewText.trim()) {
      toast.error("Please fill in your name and review before submitting.");
      return;
    }
    setSubmitting(true);
    try {
      const { message } = await submitReview({
        name: name.trim(),
        organization: court.trim() || undefined,
        rating,
        review: reviewText.trim(),
        photo,
      });
      toast.success(message || "Thank you. Your review has been submitted for approval.");
      setRating(5);
      setName("");
      setCourt("");
      setReviewText("");
      removePhoto();
      onOpenChange(false);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "We couldn't submit your review. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[calc(100%-1.5rem)] sm:w-full sm:max-w-md max-h-[90dvh] overflow-y-auto cb-scroll">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">Write a Review</DialogTitle>
          <DialogDescription>Share your experience with CourtBazaar™.</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="flex items-start gap-5 sm:gap-8">
            {/* Photo - compact circular uploader, sits beside the rating instead of its own tall row */}
            <div className="flex-shrink-0">
              <label className="text-sm font-semibold text-foreground block mb-1.5">Photo</label>
              {photo ? (
                <div className="relative w-16 h-16">
                  <img src={photoPreview} alt="" className="w-16 h-16 rounded-full object-cover border border-emerald-200" />
                  <div className="absolute -bottom-1 -right-1 flex gap-0.5">
                    <label
                      htmlFor={photoInputId}
                      className="p-1 rounded-full bg-white border border-slate-200 shadow-sm text-emerald-700 hover:bg-emerald-50 cursor-pointer transition-colors"
                      aria-label="Replace photo"
                    >
                      <RefreshCw className="w-3 h-3" />
                    </label>
                    <button
                      type="button"
                      onClick={removePhoto}
                      className="p-1 rounded-full bg-white border border-slate-200 shadow-sm text-red-600 hover:bg-red-50 transition-colors"
                      aria-label="Remove photo"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              ) : (
                <label
                  htmlFor={photoInputId}
                  className="flex items-center justify-center w-16 h-16 rounded-full border-2 border-dashed border-slate-200 cursor-pointer hover:border-accent/50 hover:bg-accent/[0.03] transition-colors"
                  aria-label="Upload a photo (optional)"
                >
                  <UploadCloud className="w-5 h-5 text-accent" />
                </label>
              )}
              <input
                id={photoInputId}
                type="file"
                className="sr-only"
                accept="image/jpeg,image/png,image/webp"
                onChange={handlePhotoChange}
              />
              <p className="text-2xs text-muted-foreground/70 text-center mt-1 w-16">Max 5MB</p>
            </div>

            <div className="flex-1 pt-0.5">
              <label className="text-sm font-semibold text-foreground block mb-2">Your Rating</label>
              <div className="flex gap-1">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    type="button"
                    onMouseEnter={() => setHovered(n)}
                    onMouseLeave={() => setHovered(0)}
                    onClick={() => setRating(n)}
                    className="p-0.5 transition-transform duration-150 ease-out active:scale-90"
                    aria-label={`${n} star`}
                    aria-pressed={n <= rating}
                  >
                    <Star
                      className={`w-7 h-7 transition-all duration-200 ease-out ${
                        n <= (hovered || rating)
                          ? "fill-accent text-accent scale-110 drop-shadow-[0_2px_5px_rgba(217,119,6,0.4)]"
                          : "text-slate-300 scale-100"
                      }`}
                    />
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div>
            <label className="text-sm font-semibold text-foreground block mb-1.5">Full Name</label>
            <Input placeholder="Enter your name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>

          <div>
            <label className="text-sm font-semibold text-foreground block mb-1.5">Court</label>
            <Input placeholder="e.g. Delhi High Court" value={court} onChange={(e) => setCourt(e.target.value)} />
          </div>

          <div>
            <label className="text-sm font-semibold text-foreground block mb-1.5">Your Review</label>
            <Textarea placeholder="Tell us about your experience..." rows={4} value={reviewText} onChange={(e) => setReviewText(e.target.value)} required />
          </div>

          <DialogFooter className="pt-3">
            <Button type="submit" disabled={submitting} className="bg-accent hover:bg-accent/90 font-bold w-full sm:w-auto">
              {submitting ? "Submitting..." : "Submit Review"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
