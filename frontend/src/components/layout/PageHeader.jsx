import React from "react";
import { cn } from "@/lib/utils";

/**
 * The overline + h1 (+ optional description) shape hand-copied near-identically
 * across ~30 admin/customer/vendor pages — see DESIGN_SYSTEM_AUDIT.md §2/§7
 * "Section headers." Renders a plain, unstyled wrapper div (no default
 * margin) so it drops into both a bare top-level position and inside an
 * existing flex/justify-between row alongside an action button.
 *
 * `eyebrowIcon` is an optional icon component for headers like
 * "🏆 Admin · Performance" that prefix the overline with an icon.
 * `titleClassName` covers the few pages whose h1 needs an extra size/margin
 * modifier (e.g. `lg:text-4xl` or `mb-6`) instead of the plain default.
 */
export default function PageHeader({
  eyebrow,
  eyebrowIcon: EyebrowIcon,
  title,
  description,
  titleClassName,
  className,
}) {
  return (
    <div className={className}>
      <div className={cn("cb-overline text-accent", EyebrowIcon && "flex items-center gap-1.5")}>
        {EyebrowIcon && <EyebrowIcon className="w-3 h-3" />}
        {eyebrow}
      </div>
      <h1 className={cn("font-display font-black text-3xl tracking-tighter mt-1", titleClassName)}>
        {title}
      </h1>
      {description && <p className="text-muted-foreground font-medium mt-1">{description}</p>}
    </div>
  );
}
