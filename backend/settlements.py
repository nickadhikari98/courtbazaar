"""Vendor payout settlement automation (T+1).
Aggregates paid + completed orders into per-vendor settlement batches with NEFT/UPI export."""
import uuid
import csv
import io
from datetime import datetime, timezone, timedelta


def _parse_dt(s):
    if not s:
        return None
    if isinstance(s, str):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    return s


async def run_settlement_cycle(db, cycle_date: str = None, dry_run: bool = False) -> dict:
    """Process T+1 settlements: aggregate yesterday's completed+paid orders per vendor."""
    now = datetime.now(timezone.utc)
    if cycle_date:
        target_date = datetime.fromisoformat(cycle_date).date()
    else:
        target_date = (now - timedelta(days=1)).date()
    start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc).isoformat()
    end = datetime.combine(target_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=timezone.utc).isoformat()

    cursor = db.orders.find({
        "payment_status": "paid",
        "status": {"$in": ["delivered", "completed"]},
        "settlement_id": {"$exists": False},
        "vendor_id": {"$ne": None},
    }, {"_id": 0})

    per_vendor = {}
    async for o in cursor:
        vid = o.get("vendor_id")
        if not vid:
            continue
        per_vendor.setdefault(vid, {"orders": [], "amount": 0.0})
        per_vendor[vid]["orders"].append(o["order_id"])
        per_vendor[vid]["amount"] += float(o.get("pricing", {}).get("vendor_payout", 0))

    settlements_created = []
    for vid, data in per_vendor.items():
        if data["amount"] <= 0:
            continue
        vendor = await db.vendors.find_one({"vendor_id": vid}, {"_id": 0})
        if not vendor:
            continue
        settle_id = f"STL{target_date.strftime('%Y%m%d')}{uuid.uuid4().hex[:6].upper()}"
        doc = {
            "settlement_id": settle_id,
            "vendor_id": vid,
            "shop_name": vendor.get("shop_name"),
            "bank_account": vendor.get("bank_account"),
            "bank_ifsc": vendor.get("bank_ifsc"),
            "has_gst": bool(vendor.get("gst")),
            "gst_number": vendor.get("gst"),
            "cycle_date": target_date.isoformat(),
            "order_ids": data["orders"],
            "order_count": len(data["orders"]),
            "amount": round(data["amount"], 2),
            "payment_mode": "NEFT" if vendor.get("bank_account") else "UPI",
            "status": "queued",
            "created_at": now.isoformat(),
        }
        if not dry_run:
            await db.settlements.insert_one(doc)
            await db.orders.update_many(
                {"order_id": {"$in": data["orders"]}},
                {"$set": {"settlement_id": settle_id}},
            )
            # Mock-notify vendor
            try:
                from notifications import send_email
                vu = await db.users.find_one({"user_id": vid}, {"_id": 0})
                if vu and vu.get("email"):
                    send_email(
                        vu["email"],
                        f"CourtBazaar Settlement {settle_id} — ₹{doc['amount']:.2f}",
                        f"<p>Hi {vu.get('name')},</p><p>Settlement <b>{settle_id}</b> queued for {doc['order_count']} orders. Amount: <b>₹{doc['amount']:.2f}</b> via {doc['payment_mode']}.</p>",
                    )
            except Exception:
                pass
        doc.pop("_id", None)
        settlements_created.append(doc)

    return {
        "cycle_date": target_date.isoformat(),
        "settlements_created": len(settlements_created),
        "total_amount": round(sum(s["amount"] for s in settlements_created), 2),
        "settlements": settlements_created,
        "dry_run": dry_run,
    }


def neft_csv_for_settlements(settlements: list) -> str:
    """Generate a NEFT/UPI batch CSV in standard Indian bank format."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Settlement ID", "Beneficiary Name", "Account Number", "IFSC", "Amount (INR)", "Mode", "Cycle Date", "GST", "Remarks"])
    for s in settlements:
        w.writerow([
            s.get("settlement_id"),
            s.get("shop_name"),
            s.get("bank_account") or "",
            s.get("bank_ifsc") or "",
            f"{s.get('amount', 0):.2f}",
            s.get("payment_mode", "NEFT"),
            s.get("cycle_date", ""),
            s.get("gst_number") or "NON-GST",
            f"CourtBazaar settlement {s.get('order_count', 0)} orders",
        ])
    return buf.getvalue()
