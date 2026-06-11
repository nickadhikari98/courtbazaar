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


def neft_csv_for_settlements(settlements: list, source_account: str = "", source_ifsc: str = "") -> str:
    """Generate a NEFT/UPI batch CSV in standard Indian bank H2H bulk-upload format.

    Columns (compatible with SBI Connect / HDFC ENet / ICICI iBizz Corporate bulk upload):
    Payment Type, Beneficiary Code, Beneficiary Name, Beneficiary Account Number,
    Beneficiary IFSC, Amount, Value Date (DD/MM/YYYY), Debit Account Number, Narration,
    Email, Mobile, Reference Number
    """
    buf = io.StringIO()
    w = csv.writer(buf)
    # Header row (NPCI/H2H compatible)
    w.writerow([
        "Payment Type",          # NEFT / IMPS / UPI
        "Beneficiary Code",      # vendor_id
        "Beneficiary Name",      # shop_name
        "Beneficiary Account",   # bank account
        "Beneficiary IFSC",      # IFSC
        "Amount",                # numeric, 2-decimal
        "Value Date",            # DD/MM/YYYY
        "Debit Account",         # company source account (optional)
        "Narration",             # max 30 chars
        "Email",
        "Mobile",
        "Reference",             # settlement_id (max 22 chars)
    ])
    for s in settlements:
        try:
            d = datetime.fromisoformat(s.get("cycle_date"))
            value_date = d.strftime("%d/%m/%Y")
        except Exception:
            value_date = (s.get("cycle_date") or "")
        mode = s.get("payment_mode", "NEFT")
        narration = f"CB-{s.get('settlement_id','')[-10:]}"  # short narration
        w.writerow([
            mode,
            s.get("vendor_id") or "",
            (s.get("shop_name") or "")[:50],
            s.get("bank_account") or "",
            s.get("bank_ifsc") or "",
            f"{float(s.get('amount', 0)):.2f}",
            value_date,
            source_account or "",
            narration[:30],
            s.get("email") or "",
            s.get("mobile") or "",
            (s.get("settlement_id") or "")[:22],
        ])
    return buf.getvalue()


def neft_csv_legacy(settlements: list) -> str:
    """Legacy simple CSV (kept for backward-compat with older tests)."""
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
