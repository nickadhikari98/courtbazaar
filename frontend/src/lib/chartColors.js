/* Shared chart color sequence — was independently hardcoded as the same
   5-hex-value array in both AdminDashboard.jsx and SuperAdminConsole.jsx
   (see DESIGN_SYSTEM_AUDIT.md §2.C). Not sourced from the --chart-1..5 CSS
   tokens because those use different hues (teal/gold/dark-cyan) than what's
   actually rendered here — swapping to them would visibly change existing
   charts. This just removes the duplicated literal; the color values
   themselves are unchanged from what was already live. */
/* eslint-disable no-restricted-syntax -- this file IS the canonical token
   definition the "no hardcoded hex" rule exists to point people at; the
   values have to live somewhere literal. */
export const CHART_COLORS = ["#0F172A", "#D97706", "#10b981", "#3b82f6", "#a855f7"];
export const CHART_COLORS_EXTENDED = [...CHART_COLORS, "#ec4899", "#06b6d4", "#f59e0b"];
