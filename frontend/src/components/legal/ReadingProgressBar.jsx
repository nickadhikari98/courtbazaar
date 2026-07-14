import React, { useEffect, useState } from "react";

/* Thin fixed bar tracking how far the reader has scrolled through the
   document — same idea as Stripe/Notion/Vercel/GitHub Docs. Purely visual;
   recomputed on scroll/resize, no layout impact on the page itself. */
export default function ReadingProgressBar() {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      const scrollTop = window.scrollY;
      const docHeight = document.documentElement.scrollHeight - window.innerHeight;
      const pct = docHeight > 0 ? Math.min(100, Math.max(0, (scrollTop / docHeight) * 100)) : 0;
      setProgress(pct);
    };
    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    window.addEventListener("resize", handleScroll);
    return () => {
      window.removeEventListener("scroll", handleScroll);
      window.removeEventListener("resize", handleScroll);
    };
  }, []);

  return (
    <div className="sticky top-16 z-30 h-1 w-full bg-slate-100" aria-hidden="true">
      <div className="h-full bg-accent transition-[width] duration-150 ease-out" style={{ width: `${progress}%` }} />
    </div>
  );
}
