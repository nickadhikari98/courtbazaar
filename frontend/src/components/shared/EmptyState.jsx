import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const SIZES = {
  sm: { padding: "p-8", icon: "w-8 h-8 mb-2", title: "font-display font-bold" },
  md: { padding: "p-10", icon: "w-10 h-10 mb-3", title: "font-display font-bold" },
  lg: { padding: "p-10", icon: "w-12 h-12 mb-3", title: "font-display font-bold text-lg" },
};

/* The dashed-border "nothing here" card, hand-duplicated across every list/tab
   page in the app (orders, hearings, templates, deliveries...) with drifting
   icon sizes and padding. `size` covers the three weights that actually occur
   (compact tab panels, default list pages, full dashboard sections) — not
   speculative, just what was already there. Icon/title/description/action are
   all optional so this also covers plain-text-only cards (no icon) and
   error/retry cards (action slot). */
export default function EmptyState({
  icon: Icon,
  iconClassName = "text-muted-foreground",
  title,
  description,
  action,
  size = "md",
  className = "",
  testId,
}) {
  const s = SIZES[size] || SIZES.md;
  return (
    <Card className={cn("border-dashed border-2", className)} data-testid={testId}>
      <CardContent className={cn(s.padding, "text-center")}>
        {Icon && <Icon className={cn(s.icon, "mx-auto", iconClassName)} strokeWidth={1.5} />}
        {title && <div className={s.title}>{title}</div>}
        {description && <p className="text-sm text-muted-foreground mt-1 max-w-sm mx-auto">{description}</p>}
        {action && <div className="mt-3">{action}</div>}
      </CardContent>
    </Card>
  );
}
