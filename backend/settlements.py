"""Settlement engine — the one bank-payout mechanism every earning role
plugs into. Two origins write into the same db.settlements collection/shape:
  - `run_settlement_cycle` below: automated T+1 batch for vendor orders
    (settlement_type="vendor_payout", unchanged logic from before).
  - `POST /earnings/withdraw` (server.py): a user-initiated withdrawal of
    their existing wallet_balance (settlement_type="withdrawal").
`payee_type`/`payee_id` are the generalized identity fields; `vendor_id` is
kept as-is (never removed) as the vendor-specific alias so none of the
existing vendor settlement admin/export/reporting code needs to change.

Status transitions (queued -> paid | failed) go through
workflow.StateMachine — the first settlement-side use of the same engine
already wired for leads (Lead->Professional) and hearings."""
import uuid
import csv
import io
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException

from workflow import StateMachine, IllegalTransition

SETTLEMENT_TRANSITIONS = {
    ("queued", "mark_paid"): "paid",
    ("queued", "mark_failed"): "failed",
}


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
            "settlement_type": "vendor_payout",
            "payee_type": "vendor",
            "payee_id": vid,
            "vendor_id": vid,  # kept as the pre-existing vendor-specific alias
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
                from notifications import send_email, record_notification_event
                vu = await db.users.find_one({"user_id": vid}, {"_id": 0})
                if vu and vu.get("email"):
                    send_email(
                        vu["email"],
                        f"CourtBazaar Settlement {settle_id} — ₹{doc['amount']:.2f}",
                        f"<p>Hi {vu.get('name')},</p><p>Settlement <b>{settle_id}</b> queued for {doc['order_count']} orders. Amount: <b>₹{doc['amount']:.2f}</b> via {doc['payment_mode']}.</p>",
                    )
                if vu:
                    await record_notification_event(
                        db, vid, "settlement_queued", "Settlement queued",
                        f"₹{doc['amount']:.2f} queued for payout via {doc['payment_mode']}.",
                        "settlement", settle_id,
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


def _make_settlement_hook(db, send_email_fn):
    async def hook(entity: dict, from_status: str, to_status: str, actor: Optional[dict]) -> None:
        payee_id = entity.get("payee_id") or entity.get("vendor_id")
        payee = await db.users.find_one({"user_id": payee_id}) if payee_id else None

        if to_status == "failed" and entity.get("settlement_type") == "withdrawal" and payee:
            # The wallet was already debited when the withdrawal was
            # requested (server.py's /earnings/withdraw) — refund it since
            # the actual bank transfer didn't go through.
            new_balance = payee.get("wallet_balance", 0) + entity["amount"]
            await db.users.update_one({"user_id": payee_id}, {"$set": {"wallet_balance": new_balance}})
            await db.wallet_transactions.insert_one({
                "user_id": payee_id, "amount": entity["amount"], "type": "credit",
                "description": f"Withdrawal {entity['settlement_id']} failed — refunded",
                "context_type": "withdrawal_refund", "related_entity_id": entity["settlement_id"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        if not payee:
            return
        from notifications import record_notification_event
        if to_status == "paid":
            if payee.get("email"):
                send_email_fn(
                    payee["email"], f"CourtBazaar Settlement {entity['settlement_id']} — Paid",
                    f"<p>Hi {payee.get('name')},</p><p>Settlement <b>{entity['settlement_id']}</b> "
                    f"for ₹{entity['amount']:.2f} has been paid.</p>",
                )
            await record_notification_event(
                db, payee_id, "settlement_paid", "Settlement paid",
                f"₹{entity['amount']:.2f} has been paid out.", "settlement", entity["settlement_id"],
            )
        elif to_status == "failed":
            await record_notification_event(
                db, payee_id, "settlement_failed", "Settlement failed",
                f"Settlement {entity['settlement_id']} could not be processed.", "settlement", entity["settlement_id"],
            )
    return hook


async def change_settlement_status(db, send_email_fn, settlement_id: str, action: str, admin_user: dict,
                                    utr: str = "", reason: str = "") -> dict:
    settlement = await db.settlements.find_one({"settlement_id": settlement_id})
    if not settlement:
        raise HTTPException(404, "Settlement not found")
    sm = StateMachine(SETTLEMENT_TRANSITIONS, _make_settlement_hook(db, send_email_fn))
    try:
        to_status = await sm.apply(settlement, settlement["status"], action, admin_user)
    except IllegalTransition:
        raise HTTPException(400, "Invalid settlement status transition")

    update: dict = {"status": to_status}
    if to_status == "paid":
        update.update({"paid_at": datetime.now(timezone.utc).isoformat(), "utr": utr, "paid_by": admin_user["user_id"]})
    elif to_status == "failed":
        update["failure_reason"] = reason or "Unknown"
    await db.settlements.update_one({"settlement_id": settlement_id}, {"$set": update})

    if to_status == "failed" and settlement.get("order_ids"):
        await db.orders.update_many({"order_id": {"$in": settlement["order_ids"]}}, {"$unset": {"settlement_id": ""}})
    return {"ok": True, "status": to_status}
    return buf.getvalue()
