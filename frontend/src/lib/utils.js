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
