/* Pricing data — the per-service "Individual Pricing" list used to live here
   too (individualPricing) but now comes from the backend service catalog
   (GET /services/public?surface=landing, same source Landing.jsx/MegaMenu.jsx
   use — see Pricing.jsx) so it can't drift from what's actually on Landing.
   `packages`/`addOnServices` below are a genuinely separate concept
   (subscription bundle economics, not per-service catalog data) and stay
   here unchanged. */

export const packages = [
  {
    slug: "basic",
    name: "Basic",
    tagline: "Digital Filing Ready",
    perPageRate: "₹4/page individually",
    startingPrice: "349",
    savings: "25%",
    features: ["Scanning", "OCR", "Bookmarking", "Filing Ready PDF on Email"],
    tiers: [
      { pages: 100, individual: 400, package: 349, savings: 51, discount: "12.8%" },
      { pages: 200, individual: 800, package: 649, savings: 151, discount: "18.9%" },
      { pages: 300, individual: 1200, package: 949, savings: 251, discount: "20.9%" },
      { pages: 400, individual: 1600, package: 1199, savings: 401, discount: "25.1%" },
      { pages: 500, individual: 2000, package: 1449, savings: 551, discount: "27.6%" },
      { pages: 600, individual: 2400, package: 1699, savings: 701, discount: "29.2%" },
      { pages: 700, individual: 2800, package: 1949, savings: 851, discount: "30.4%" },
      { pages: 800, individual: 3200, package: 2199, savings: 1001, discount: "31.3%" },
      { pages: 900, individual: 3600, package: 2449, savings: 1151, discount: "32.0%" },
      { pages: 1000, individual: 4000, package: 2699, savings: 1301, discount: "32.5%" },
    ],
  },
  {
    slug: "standard",
    name: "Standard",
    tagline: "Print Ready Package",
    perPageRate: "₹6/page individually",
    startingPrice: "499",
    savings: "33%",
    features: ["1 Print Set", "Scanning", "OCR", "Bookmarking", "Filing Ready PDF on Email"],
    badge: "popular",
    tiers: [
      { pages: 100, individual: 600, package: 499, savings: 101, discount: "16.8%" },
      { pages: 200, individual: 1200, package: 949, savings: 251, discount: "20.9%" },
      { pages: 300, individual: 1800, package: 1349, savings: 451, discount: "25.1%" },
      { pages: 400, individual: 2400, package: 1749, savings: 651, discount: "27.1%" },
      { pages: 500, individual: 3000, package: 2099, savings: 901, discount: "30.0%" },
      { pages: 600, individual: 3600, package: 2449, savings: 1151, discount: "32.0%" },
      { pages: 700, individual: 4200, package: 2799, savings: 1401, discount: "33.4%" },
      { pages: 800, individual: 4800, package: 3149, savings: 1651, discount: "34.4%" },
      { pages: 900, individual: 5400, package: 3499, savings: 1901, discount: "35.2%" },
      { pages: 1000, individual: 6000, package: 3849, savings: 2151, discount: "35.9%" },
    ],
  },
  {
    slug: "premium",
    name: "Premium",
    tagline: "Litigation Package",
    perPageRate: "₹8/page individually",
    startingPrice: "649",
    savings: "35%",
    features: ["1 Print Set", "Scanning", "OCR", "Bookmarking", "2 Photocopy Sets", "Filing Ready PDF on Email"],
    badge: "best-value",
    tiers: [
      { pages: 100, individual: 800, package: 649, savings: 151, discount: "18.9%" },
      { pages: 200, individual: 1600, package: 1249, savings: 351, discount: "21.9%" },
      { pages: 300, individual: 2400, package: 1799, savings: 601, discount: "25.0%" },
      { pages: 400, individual: 3200, package: 2349, savings: 851, discount: "26.6%" },
      { pages: 500, individual: 4000, package: 2899, savings: 1101, discount: "27.5%" },
      { pages: 600, individual: 4800, package: 3449, savings: 1351, discount: "28.1%" },
      { pages: 700, individual: 5600, package: 3999, savings: 1601, discount: "28.6%" },
      { pages: 800, individual: 6400, package: 4549, savings: 1851, discount: "28.9%" },
      { pages: 900, individual: 7200, package: 5099, savings: 2101, discount: "29.2%" },
      { pages: 1000, individual: 8000, package: 5649, savings: 2351, discount: "29.4%" },
    ],
  },
];

export const addOnServices = [
  { service: "District Court E-Filing (Delhi)", individual: 499, addOn: 299, savings: 200 },
  { service: "High Court E-Filing (Delhi)", individual: 1999, addOn: 999, savings: 1000 },
  { service: "Supreme Court E-Filing", individual: 3999, addOn: 2999, savings: 1000 },
];

export function formatINR(n) {
  return `₹${n.toLocaleString("en-IN")}`;
}
