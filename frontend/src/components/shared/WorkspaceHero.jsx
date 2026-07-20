import React from "react";

/* The repeated authenticated-page hero shell — bg-primary + cb-grain
   texture, already shared by Landing and (previously, hand-copied) by
   Dashboard.jsx — extracted into one component instead of each page
   re-implementing the div/texture/rounded-corner wrapper by hand.

   `badges` and `actions` stay flexible node/children slots rather than a
   rigid prop shape, since what a given page needs there (capability
   badges, a CTA row, a live-status badge) varies too much page to page to
   usefully constrain. `summary` is the one structured slot — an array of
   short strings rendered as the existing bullet row. */
export default function WorkspaceHero({
  eyebrow, title, badges, summary, actions, className = "", "data-testid": testId = "workspace-hero",
}) {
  return (
    <div className={`relative bg-primary text-white rounded-3xl p-8 lg:p-10 mb-8 overflow-hidden ${className}`} data-testid={testId}>
      <div className="absolute inset-0 cb-grain opacity-30"></div>
      <div className="relative">
        {eyebrow && <div className="cb-overline text-white/60">{eyebrow}</div>}
        <h1 className="font-display font-black text-3xl lg:text-4xl tracking-tighter leading-tight mt-1">{title}</h1>
        {badges && <div className="flex flex-wrap items-center gap-1.5 mt-3">{badges}</div>}
        {summary?.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1.5 text-sm text-white/80 font-medium">
            {summary.map((s, i) => <span key={i}>• {s}</span>)}
          </div>
        )}
        {actions && <div className="mt-6">{actions}</div>}
      </div>
    </div>
  );
}
