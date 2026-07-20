import React from "react";
import { Link } from "react-router-dom";

const SIZE_CLASSES = {
  sm: "h-8",
  md: "h-10",
  lg: "h-10 sm:h-12",
};

/* The one branding component every surface reuses — sidebar, auth pages,
   marketing nav, loading screens. Wraps the real approved logo asset
   (/images/cbLogo-navbar.png, previously only used by NavbarLogo.jsx) so no
   page hand-rolls its own icon-in-a-box placeholder.

   The approved asset is a single combined icon+wordmark lockup (no
   separate icon-only file exists), so `variant="icon"` and `variant="full"`
   currently render the same image — this is the one place to swap in a
   standalone icon-mark asset later without touching any call site.
   `variant="wordmark"` is the one case that's genuinely different: a
   text-only render for a context that can't/shouldn't load the image.
   `showTrademark` only affects the wordmark variant for the same reason —
   the "™" is baked into the raster image, so it can't be toggled off the
   image render; it can for the text render.
   `theme` is accepted but unused today — reserved so call sites don't need
   to change if a dark-mode logo variant is introduced later. */
export default function Logo({
  to = "/", variant = "full", size = "md", showTrademark = true, clickable = true, theme, className = "",
  "data-testid": testId = "courtbazaar-logo", ...rest
}) {
  const heightClass = SIZE_CLASSES[size] || SIZE_CLASSES.md;

  const content = variant === "wordmark" ? (
    <span className="font-display font-black text-lg tracking-tight leading-none">
      CourtBazaar{showTrademark ? "™" : ""}
    </span>
  ) : (
    <img
      src="/images/cbLogo-navbar.png"
      alt="CourtBazaar™ - India's Premier Legal Operations & Services Platform"
      className={`${heightClass} w-auto object-contain`}
    />
  );

  const Wrapper = clickable ? Link : "div";
  const wrapperProps = clickable ? { to } : {};

  return (
    <Wrapper {...wrapperProps} {...rest} className={`flex items-center shrink-0 ${className}`} data-testid={testId}>
      {content}
    </Wrapper>
  );
}
