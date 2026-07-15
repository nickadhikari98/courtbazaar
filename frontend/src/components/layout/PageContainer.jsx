import React from "react";
import { cn } from "@/lib/utils";

/**
 * The standard authenticated-page wrapper: max-width + responsive padding.
 * Replaces the literal `p-6 lg:p-10 max-w-7xl mx-auto` that was hand-copied
 * across Dashboard.jsx, AdminDashboard.jsx, and VendorDashboard.jsx —
 * see PRODUCT_DESIGN_SYSTEM.md §3.2.
 */
export default function PageContainer({ className, children, ...props }) {
  return (
    <div className={cn("p-6 lg:p-10 max-w-7xl mx-auto", className)} {...props}>
      {children}
    </div>
  );
}
