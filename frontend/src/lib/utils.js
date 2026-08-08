import { clsx } from "clsx";
import { twMerge } from "tailwind-merge"

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

/* Resolves the literal string "today" to the current local date in
   YYYY-MM-DD form; any other value (or undefined) passes through unchanged.
   Shared by every date-bound field in the "Join as..." forms. */
export function resolveDateBound(bound) {
  if (bound === "today") return new Date().toLocaleDateString("en-CA");
  return bound;
}

/* "3h ago" / "2d ago" style relative time — was a local helper duplicated
   nowhere else until HearingActivityPreview needed it too; lifted here
   rather than copied a second time. */
export function timeAgo(iso) {
  if (!iso) return "";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}
