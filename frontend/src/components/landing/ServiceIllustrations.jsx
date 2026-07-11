import React from "react";

/* Flat, brand-colored illustration icons for the Core Services grid.
   Navy (#0f172a) + Orange (#D97706) + neutrals only — no new palette colors. */

const NAVY = "#0f172a";
const NAVY_SOFT = "#334155";
const ORANGE = "#D97706";
const PAPER = "#ffffff";
const LINE = "#cbd5e1";

export function PrintOutIcon({ className = "w-14 h-14" }) {
  return (
    <svg viewBox="0 0 64 64" className={className} fill="none">
      <rect x="20" y="12" width="24" height="16" rx="2" fill={PAPER} stroke={LINE} strokeWidth="1.5" />
      <rect x="24" y="17" width="16" height="2" rx="1" fill={LINE} />
      <rect x="24" y="21" width="12" height="2" rx="1" fill={LINE} />
      <rect x="12" y="22" width="40" height="22" rx="4" fill={NAVY} />
      <rect x="16" y="28" width="8" height="4" rx="1.5" fill={ORANGE} />
      <circle cx="44" cy="30" r="2" fill={ORANGE} />
      <rect x="18" y="38" width="28" height="16" rx="2" fill={PAPER} stroke={LINE} strokeWidth="1.5" />
      <rect x="22" y="43" width="20" height="2" rx="1" fill={LINE} />
      <rect x="22" y="47" width="14" height="2" rx="1" fill={ORANGE} />
    </svg>
  );
}

export function PhotocopyIcon({ className = "w-14 h-14" }) {
  return (
    <svg viewBox="0 0 64 64" className={className} fill="none">
      <rect x="10" y="14" width="44" height="10" rx="2" fill={NAVY_SOFT} />
      <rect x="16" y="10" width="12" height="6" rx="1" fill={LINE} />
      <rect x="10" y="24" width="44" height="24" rx="4" fill={NAVY} />
      <rect x="16" y="30" width="14" height="10" rx="1.5" fill={PAPER} />
      <circle cx="40" cy="32" r="2" fill={ORANGE} />
      <circle cx="40" cy="38" r="2" fill={PAPER} opacity="0.5" />
      <rect x="46" y="30" width="4" height="12" rx="1" fill={ORANGE} />
      <rect x="20" y="50" width="24" height="10" rx="2" fill={PAPER} stroke={LINE} strokeWidth="1.5" />
      <rect x="24" y="54" width="16" height="2" rx="1" fill={LINE} />
    </svg>
  );
}

export function ScanningIcon({ className = "w-14 h-14" }) {
  return (
    <svg viewBox="0 0 64 64" className={className} fill="none">
      <rect x="18" y="10" width="24" height="30" rx="2" fill={PAPER} stroke={LINE} strokeWidth="1.5" />
      <rect x="22" y="16" width="16" height="2" rx="1" fill={LINE} />
      <rect x="22" y="20" width="16" height="2" rx="1" fill={LINE} />
      <rect x="22" y="24" width="10" height="2" rx="1" fill={LINE} />
      <rect x="14" y="27" width="36" height="3" rx="1.5" fill={ORANGE} opacity="0.85" />
      <rect x="10" y="42" width="44" height="12" rx="4" fill={NAVY} />
      <rect x="16" y="47" width="10" height="3" rx="1.5" fill={ORANGE} />
      <circle cx="44" cy="48" r="2" fill={PAPER} opacity="0.6" />
    </svg>
  );
}

export function OcrBookmarkIcon({ className = "w-14 h-14" }) {
  return (
    <svg viewBox="0 0 64 64" className={className} fill="none">
      <rect x="14" y="10" width="30" height="40" rx="3" fill={PAPER} stroke={LINE} strokeWidth="1.5" />
      <rect x="20" y="20" width="18" height="2" rx="1" fill={LINE} />
      <rect x="20" y="25" width="18" height="2" rx="1" fill={LINE} />
      <rect x="20" y="30" width="12" height="2" rx="1" fill={LINE} />
      <rect x="20" y="35" width="14" height="2" rx="1" fill={LINE} />
      <path d="M32 10h10v14l-5-3.5L32 24V10Z" fill={ORANGE} />
      {/* corner focus brackets to signal OCR recognition */}
      <path d="M42 42v6h6" stroke={NAVY} strokeWidth="2" fill="none" strokeLinecap="round" />
      <path d="M50 34v-6h-6" stroke={NAVY} strokeWidth="2" fill="none" strokeLinecap="round" />
    </svg>
  );
}

export function EFilingDistrictIcon({ className = "w-14 h-14" }) {
  return (
    <svg viewBox="0 0 64 64" className={className} fill="none">
      <rect x="12" y="14" width="34" height="22" rx="2" fill={NAVY} />
      <rect x="15" y="17" width="28" height="16" rx="1" fill="#1e293b" />
      {/* courthouse glyph on screen */}
      <path d="M29 20l6-3 6 3H29Z" fill={ORANGE} />
      <rect x="30" y="24" width="2.5" height="7" fill={PAPER} opacity="0.85" />
      <rect x="34.5" y="24" width="2.5" height="7" fill={PAPER} opacity="0.85" />
      <rect x="39" y="24" width="2.5" height="7" fill={PAPER} opacity="0.85" />
      <rect x="28" y="31" width="16" height="2" fill={PAPER} opacity="0.85" />
      <path d="M8 38h50l-4 6H12l-4-6Z" fill={NAVY_SOFT} />
      <circle cx="47" cy="44" r="8" fill={ORANGE} />
      <path d="M43.5 44l2.2 2.2L50 41.8" stroke={PAPER} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function EFilingHighIcon({ className = "w-14 h-14" }) {
  return (
    <svg viewBox="0 0 64 64" className={className} fill="none">
      <rect x="12" y="14" width="34" height="22" rx="2" fill={NAVY} />
      <rect x="15" y="17" width="28" height="16" rx="1" fill="#1e293b" />
      {/* grander high-court glyph: dome + wider colonnade */}
      <circle cx="32" cy="19.5" r="3" fill={ORANGE} />
      <path d="M25 22h14l-2 2H27l-2-2Z" fill={ORANGE} />
      <rect x="27" y="24" width="2" height="7" fill={PAPER} opacity="0.85" />
      <rect x="31" y="24" width="2" height="7" fill={PAPER} opacity="0.85" />
      <rect x="35" y="24" width="2" height="7" fill={PAPER} opacity="0.85" />
      <rect x="26" y="31" width="12" height="2" fill={PAPER} opacity="0.85" />
      <path d="M8 38h50l-4 6H12l-4-6Z" fill={NAVY_SOFT} />
      <circle cx="47" cy="44" r="8" fill={ORANGE} />
      <path
        d="M47,38.5 48.29,42.22 52.23,42.3 49.09,44.68 50.23,48.45 47,46.2 43.77,48.45 44.91,44.68 41.77,42.3 45.71,42.22Z"
        fill={PAPER}
      />
    </svg>
  );
}

/* ===== "How It Works" step illustrations — same flat navy/orange language ===== */

export function SelectServiceIcon({ className = "w-9 h-9" }) {
  return (
    <svg viewBox="0 0 64 64" className={className} fill="none">
      <rect x="12" y="12" width="40" height="30" rx="3" fill={PAPER} stroke={LINE} strokeWidth="1.5" />
      <rect x="18" y="19" width="14" height="4" rx="1.5" fill={NAVY_SOFT} />
      <rect x="18" y="27" width="20" height="3" rx="1.5" fill={LINE} />
      <rect x="18" y="32" width="14" height="3" rx="1.5" fill={LINE} />
      <circle cx="44" cy="44" r="12" fill={ORANGE} />
      <path d="M39 44l3.5 3.5L49 40.5" stroke={PAPER} strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function UploadDocIcon({ className = "w-9 h-9" }) {
  return (
    <svg viewBox="0 0 64 64" className={className} fill="none">
      <rect x="16" y="16" width="32" height="38" rx="3" fill={PAPER} stroke={LINE} strokeWidth="1.5" />
      <rect x="22" y="38" width="20" height="2.5" rx="1.25" fill={LINE} />
      <rect x="22" y="43" width="20" height="2.5" rx="1.25" fill={LINE} />
      <rect x="22" y="48" width="13" height="2.5" rx="1.25" fill={LINE} />
      <circle cx="32" cy="24" r="11" fill={NAVY} />
      <path d="M32 30v-10M27 24l5-5 5 5" stroke={ORANGE} strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ReviewPayIcon({ className = "w-9 h-9" }) {
  return (
    <svg viewBox="0 0 64 64" className={className} fill="none">
      <rect x="10" y="14" width="28" height="36" rx="3" fill={PAPER} stroke={LINE} strokeWidth="1.5" />
      <rect x="16" y="21" width="16" height="2.5" rx="1.25" fill={LINE} />
      <rect x="16" y="27" width="16" height="2.5" rx="1.25" fill={LINE} />
      <rect x="16" y="33" width="10" height="2.5" rx="1.25" fill={LINE} />
      <rect x="30" y="38" width="24" height="16" rx="3" fill={NAVY} />
      <rect x="30" y="43" width="24" height="3" fill={NAVY_SOFT} />
      <circle cx="48" cy="49" r="3" fill={ORANGE} />
      <circle cx="46" cy="24" r="12" fill={ORANGE} />
      <path d="M41 24l3.5 3.5L51 20.5" stroke={PAPER} strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ProcessingIcon({ className = "w-9 h-9" }) {
  return (
    <svg viewBox="0 0 64 64" className={className} fill="none">
      <rect x="12" y="18" width="24" height="30" rx="3" fill={PAPER} stroke={LINE} strokeWidth="1.5" />
      <rect x="17" y="25" width="14" height="2.5" rx="1.25" fill={LINE} />
      <rect x="17" y="30" width="14" height="2.5" rx="1.25" fill={LINE} />
      <rect x="17" y="35" width="9" height="2.5" rx="1.25" fill={LINE} />
      <g>
        <circle cx="45" cy="22" r="9" fill={NAVY} />
        <path d="M45 18v-2.5M45 28.5V26M49.5 22H52M38 22h2.5M48.2 18.8l1.7-1.7M40.1 25.9l1.7-1.7M48.2 25.2l1.7 1.7M40.1 18.1l1.7 1.7" stroke={ORANGE} strokeWidth="2" strokeLinecap="round" />
      </g>
      <g>
        <circle cx="40" cy="42" r="13" fill={ORANGE} />
        <path d="M40 36.5v-2M40 49.5v-2M45.5 42H48M32 42h2.5M43.8 37.8l1.5-1.5M34.7 49.3l1.5-1.5M43.8 46.2l1.5 1.5M34.7 34.7l1.5 1.5" stroke={PAPER} strokeWidth="2" strokeLinecap="round" opacity="0.9" />
      </g>
    </svg>
  );
}

export function DeliveredIcon({ className = "w-9 h-9" }) {
  return (
    <svg viewBox="0 0 64 64" className={className} fill="none">
      <path d="M32 12 54 22v22L32 54 10 44V22Z" fill={NAVY} />
      <path d="M32 12 54 22 32 32 10 22Z" fill={NAVY_SOFT} />
      <path d="M32 32v22" stroke={PAPER} strokeWidth="1.5" opacity="0.3" />
      <rect x="26" y="24" width="12" height="10" rx="1.5" fill={ORANGE} opacity="0.9" />
      <circle cx="46" cy="46" r="11" fill={ORANGE} />
      <path d="M41 46l3.5 3.5L51 42.5" stroke={PAPER} strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
