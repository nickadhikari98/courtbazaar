import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

// Browsers restore the previous scroll position on back/forward navigation
// by default, which fights the reset below — hand scroll position management
// entirely to this component instead.
if (typeof window !== "undefined" && "scrollRestoration" in window.history) {
  window.history.scrollRestoration = "manual";
}

/* Resets scroll to the top on every route change (navbar links, footer
   links, internal <Link>s, and browser back/forward), so a new page never
   opens mid-scroll from wherever the previous page was left.

   A hash in the new URL does NOT by itself mean "leave scroll alone" — a
   route change to e.g. /pricing#basic carries a hash that Pricing.jsx uses
   only to pick which package to display, not as a scroll target, so it must
   still reset to top like any other navigation. Only a hash change on the
   SAME pathname (e.g. the mega menu's #services link while already on that
   page) is a genuine in-page anchor jump and is left untouched here.

   Pages that DO want to land mid-document on a hash (e.g.
   /legal/terms#payments) handle that themselves in a mount-time effect
   (LegalPageLayout) that runs after this one and scrolls to the section —
   so resetting to top first here doesn't break that, it just makes the
   transition start from the top instead of opening already scrolled down. */
export default function ScrollToTop() {
  const { pathname, hash } = useLocation();
  const prevPathname = useRef(pathname);

  useEffect(() => {
    const pathnameChanged = prevPathname.current !== pathname;
    prevPathname.current = pathname;

    if (hash && !pathnameChanged) return;
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }, [pathname, hash]);

  return null;
}
