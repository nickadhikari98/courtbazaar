"""Vendor SLA computation + leaderboard scoring."""
from datetime import datetime, timezone
from typing import List, Dict


def _parse_dt(s):
    if not s:
        return None
    if isinstance(s, str):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    return s


async def compute_vendor_sla(db, vendor_id: str) -> Dict:
    """Compute SLA metrics for a single vendor."""
    orders = await db.orders.find({"vendor_id": vendor_id}, {"_id": 0}).to_list(2000)
    total = len(orders)
    completed = [o for o in orders if o.get("status") in ("delivered", "completed")]
    cancelled = [o for o in orders if o.get("status") == "cancelled"]
    completion_rate = (len(completed) / total * 100) if total else 0
    cancellation_rate = (len(cancelled) / total * 100) if total else 0

    # Average turnaround: created_at -> delivered timeline entry
    turnarounds = []
    on_time_count = 0
    sla_window_hours_default = 24
    for o in completed:
        ca = _parse_dt(o.get("created_at"))
        deliv = None
        for t in (o.get("timeline") or []):
            if t.get("status") in ("delivered", "completed"):
                deliv = _parse_dt(t.get("at"))
                break
        if ca and deliv:
            diff_h = (deliv - ca).total_seconds() / 3600
            turnarounds.append(diff_h)
            # SLA window: max of urgent (8h) / standard (24h) / heavy (48h)
            sla_h = 8 if o.get("urgent") else sla_window_hours_default
            if diff_h <= sla_h:
                on_time_count += 1

    avg_tat = sum(turnarounds) / len(turnarounds) if turnarounds else 0
    on_time_rate = (on_time_count / len(turnarounds) * 100) if turnarounds else 100

    # Rating + revenue
    rated = [o for o in orders if o.get("rating")]
    avg_rating = (sum(o["rating"] for o in rated) / len(rated)) if rated else 0
    revenue = sum(float(o.get("pricing", {}).get("vendor_payout", 0)) for o in completed)

    # Dispute proxy: low-rated orders (rating <= 2)
    disputes = sum(1 for o in rated if o["rating"] <= 2)
    dispute_rate = (disputes / len(rated) * 100) if rated else 0

    # Composite score (out of 100)
    score = (
        (on_time_rate * 0.35) +
        (completion_rate * 0.25) +
        ((avg_rating / 5) * 100 * 0.25) +
        ((100 - dispute_rate) * 0.15)
    )

    return {
        "vendor_id": vendor_id,
        "total_orders": total,
        "completed": len(completed),
        "cancelled": len(cancelled),
        "completion_rate": round(completion_rate, 1),
        "cancellation_rate": round(cancellation_rate, 1),
        "avg_turnaround_hours": round(avg_tat, 1),
        "on_time_rate": round(on_time_rate, 1),
        "avg_rating": round(avg_rating, 2),
        "rated_orders": len(rated),
        "disputes": disputes,
        "dispute_rate": round(dispute_rate, 1),
        "revenue": round(revenue, 2),
        "sla_score": round(score, 1),
    }


def sla_grade(score: float) -> str:
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    return "D"


async def leaderboard(db, limit: int = 50) -> List[Dict]:
    vendors = await db.vendors.find({"kyc_status": "approved"}, {"_id": 0}).to_list(500)
    out = []
    for v in vendors:
        sla = await compute_vendor_sla(db, v["vendor_id"])
        out.append({
            "vendor_id": v["vendor_id"],
            "shop_name": v.get("shop_name"),
            "city": (v.get("address") or "").split(",")[-1].strip() if v.get("address") else "",
            "court_count": len(v.get("court_ids", [])),
            "sponsored": v.get("sponsored", False),
            **sla,
            "grade": sla_grade(sla["sla_score"]),
        })
    out.sort(key=lambda x: (-x["sla_score"], -x["total_orders"]))
    return out[:limit]
