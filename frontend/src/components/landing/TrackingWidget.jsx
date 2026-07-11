import React, { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Search } from "lucide-react";

export default function TrackingWidget({ className = "" }) {
  const [trackingId, setTrackingId] = useState("");

  const handleTrack = (e) => {
    e.preventDefault();
    if (!trackingId.trim()) return;
    toast.info("Order tracking is coming soon. We'll notify you as soon as it's live.");
  };

  return (
    <form onSubmit={handleTrack} className={`landing-tracking-widget ${className}`}>
      <Search className="w-4 h-4 text-muted-foreground flex-shrink-0 ml-1" />
      <Input
        value={trackingId}
        onChange={(e) => setTrackingId(e.target.value)}
        placeholder="Enter Tracking ID"
        className="border-0 shadow-none h-8 focus-visible:ring-0 px-2"
      />
      <Button type="submit" size="sm" className="bg-primary hover:bg-primary/90 font-bold h-9 px-4 flex-shrink-0">
        Track
      </Button>
    </form>
  );
}
