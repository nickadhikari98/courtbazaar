import React from "react";
import { Link } from "react-router-dom";
import { PlayCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const tabClassName = cn(
  "fixed right-0 top-36 sm:top-20 z-40 flex items-center gap-1.5 px-2 py-2",
  "bg-primary hover:bg-primary/90 font-bold text-primary-foreground text-xs",
  "shadow-lg transition-colors"
);
const tabStyle = { writingMode: "vertical-rl", transform: "rotate(180deg)" };

/* Persistent "Take a Tour" trigger, fixed to the right edge of the viewport
   as a vertical side tab (text reads bottom-to-top) instead of an inline nav
   button — same click behavior as before (onTakeTour callback, or a
   `?tour=1` link fallback when the callback isn't supplied). */
export default function TourSideTab({ onTakeTour }) {
  if (onTakeTour) {
    return (
      <button type="button" onClick={onTakeTour} className={tabClassName} style={tabStyle}>
        Take a Tour <PlayCircle className="w-3.5 h-3.5" />
      </button>
    );
  }
  return (
    <Link to="/?tour=1" className={tabClassName} style={tabStyle}>
      Take a Tour <PlayCircle className="w-3.5 h-3.5" />
    </Link>
  );
}
