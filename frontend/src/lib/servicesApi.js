import { api } from "./api";

/* Single read path for every surface that shows a curated service list —
   Landing, MegaMenu, Dashboard quick-tiles, Pricing — instead of each one
   maintaining its own hardcoded array. `surface` is a visibility key
   (landing|marketplace|sidebar) mirroring db.services' `visibility` object. */
export async function listPublicServices(surface) {
  const { data } = await api.get("/services/public", { params: { surface } });
  return data;
}

/** "₹499/file", "₹1,999/file" — shared by every surface that renders a
    service's starting price from raw base_price/unit fields. */
export function formatServicePrice(service) {
  const amount = Number.isInteger(service.base_price)
    ? service.base_price.toLocaleString("en-IN")
    : service.base_price.toFixed(2);
  const unitSuffix = (service.unit || "").replace(/^per\s+/i, "/");
  return `₹${amount}${unitSuffix}`;
}
