/* Classes for NegotiationModule's "Open Discussion & Documents" button
   (D2, mobile). The Button base is whitespace-nowrap + fixed h-8, so on a
   phone this ~233px label overran its ~171px column (and a 375px viewport by
   ~18px). Let it wrap instead: min-h-8 + py-1 keeps a single-line button
   exactly 32px tall, and the width stays content-sized, so wherever the
   label fits (tablet/desktop) it renders exactly as before. Kept in its own
   module so the class contract is testable without loading the page. */
export const ASSIGNMENT_CTA_CLASS = "font-bold whitespace-normal h-auto min-h-8 py-1 text-left";
