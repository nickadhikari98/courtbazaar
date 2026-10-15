"""READ-ONLY dry run for permanently deleting users (Admin → Users
"Delete selected" / POST /admin/users/bulk-delete).

For each target account it reports, without changing anything:
  - whether it can be deleted, or exactly why not (the same
    audit_log.financial_blockers the endpoint enforces, plus self/admin);
  - how many rows the delete WOULD remove, per collection;
  - how many financial/legal rows are RETAINED (left pointing at the
    deleted user_id).
With --backup-dir it also writes every row that would be removed to JSON,
so a deletion can be reversed by re-inserting them.

--exposure-audit reports, for the whole database, what is visible to
clients today: deactivated accounts that still have approved counsel /
vendor profiles, and profiles with no users row at all (orphans).

It never writes to the database and never imports server.py (whose import
starts the background schedulers). The connection is never read from
backend/.env: pass the database explicitly.

    cd backend
    # connection string from an env var so it isn't in shell history
    set PROD_MONGO_URL=...            (PowerShell: $env:PROD_MONGO_URL = "...")
    python scripts/user_deletion_dry_run.py --mongo-url-env PROD_MONGO_URL --db courtbazaar \\
        --email someone@example.com --user-id user_abc123 \\
        [--file targets.txt] [--backup-dir ./deletion_backup] [--exposure-audit] [--json report.json]

targets.txt: one email or user_id per line (# comments allowed).
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from audit_log import PROFILE_COLLECTIONS, _norm_email, financial_blockers  # noqa: E402

# Rows a delete keeps on purpose (financial / legal / history), and the
# fields that point at the user in each.
RETAINED = {
    "orders": ["user_id", "vendor_id"],
    "hearing_requests": ["requesting_user_id", "proxy_counsel_user_id", "target_advocate_id"],
    "escrow_transactions": ["payer_user_id", "payee_user_id"],
    "payment_transactions": ["user_id"],
    "wallet_transactions": ["user_id"],
    "settlements": ["payee_id", "vendor_id"],
    "audit_log": ["user_id"],
    "professional_ratings": ["rated_user_id", "rated_by_user_id"],
    "hearing_messages": ["sender_user_id"],
    "notification_events": ["user_id"],
    "files": ["user_id"],
    "matters": ["user_id"],
    "support_tickets": ["user_id"],
    "ai_conversations": ["user_id"],
}


async def _resolve(db, token: str):
    token = token.strip()
    if "@" in token:
        return await db.users.find_one({"email": {"$in": [token, _norm_email(token)]}}, {"_id": 0, "password_hash": 0})
    return await db.users.find_one({"user_id": token}, {"_id": 0, "password_hash": 0})


async def _would_remove(db, user):
    """Mirrors audit_log.permanently_delete_users' delete set."""
    uid = user["user_id"]
    rows = {
        "users": [user],
        "user_sessions": await db.user_sessions.find({"user_id": uid}, {"_id": 0}).to_list(1000),
    }
    for coll in PROFILE_COLLECTIONS:
        rows[coll] = await db[coll].find({"user_id": uid}, {"_id": 0}).to_list(1000)
    lead_q = [{"converted_user_id": uid}]
    if user.get("email"):
        lead_q.append({"email_normalized": _norm_email(user["email"])})
    leads = await db.leads.find({"$or": lead_q}, {"_id": 0}).to_list(50)
    lead_ids = [lead["lead_id"] for lead in leads]
    rows["leads"] = leads
    rows["lead_documents"] = await db.lead_documents.find({"lead_id": {"$in": lead_ids}}, {"_id": 0}).to_list(500)
    rows["lead_status_history"] = await db.lead_status_history.find({"lead_id": {"$in": lead_ids}}, {"_id": 0}).to_list(500)
    return rows


async def _retained(db, user):
    uid = user["user_id"]
    vendor_ids = [uid] + [v["vendor_id"] for v in await db.vendors.find({"user_id": uid}, {"_id": 0, "vendor_id": 1}).to_list(20)
                          if v.get("vendor_id")]
    out = {}
    for coll, fields in RETAINED.items():
        ids = vendor_ids if coll in ("orders", "settlements") else [uid]
        n = await db[coll].count_documents({"$or": [{f: {"$in": ids}} for f in fields]})
        if n:
            out[coll] = n
    return out


async def _exposure_audit(db):
    """What clients can see right now, before any code fix is deployed."""
    report = {}
    deactivated = {u["user_id"] for u in await db.users.find({"deleted": True}, {"_id": 0, "user_id": 1}).to_list(100000)}
    approved_counsel = await db.proxy_counsel_profiles.find(
        {"kyc_status": "approved", "bar_council_verified": True}, {"_id": 0, "user_id": 1}).to_list(100000)
    approved_vendors = await db.vendors.find({"kyc_status": "approved"}, {"_id": 0, "user_id": 1, "vendor_id": 1}).to_list(100000)
    report["deactivated_accounts"] = len(deactivated)
    report["deactivated_but_listed_counsel"] = sorted(p["user_id"] for p in approved_counsel if p["user_id"] in deactivated)
    report["deactivated_but_listed_vendors"] = sorted(v.get("vendor_id") for v in approved_vendors if v.get("user_id") in deactivated)

    for coll in ("proxy_counsel_profiles", "vendors"):
        ids = [r.get("user_id") for r in await db[coll].find({}, {"_id": 0, "user_id": 1}).to_list(100000) if r.get("user_id")]
        live = {u["user_id"] for u in await db.users.find({"user_id": {"$in": ids}}, {"_id": 0, "user_id": 1}).to_list(len(ids) or 1)}
        report[f"{coll}_orphans"] = sorted(i for i in ids if i not in live)
    report["deleted_accounts_entries"] = await db.deleted_accounts.count_documents({})
    return report


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--mongo-url", help="Mongo connection string (prefer --mongo-url-env)")
    src.add_argument("--mongo-url-env", help="Name of an env var holding the connection string")
    ap.add_argument("--db", required=True, help="Database name, e.g. courtbazaar")
    ap.add_argument("--email", action="append", default=[])
    ap.add_argument("--user-id", action="append", default=[])
    ap.add_argument("--file", help="One email or user_id per line")
    ap.add_argument("--acting-admin-id", help="Admin who will run the delete (reported as a self-delete if targeted)")
    ap.add_argument("--backup-dir", help="Write every row that would be removed to JSON here")
    ap.add_argument("--exposure-audit", action="store_true")
    ap.add_argument("--json", help="Also write the full report to this file")
    args = ap.parse_args()

    url = args.mongo_url or os.environ.get(args.mongo_url_env or "")
    if not url:
        ap.error(f"env var {args.mongo_url_env} is empty")
    targets = list(args.email) + list(args.user_id)
    if args.file:
        targets += [ln.strip() for ln in Path(args.file).read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.strip().startswith("#")]
    if not targets and not args.exposure_audit:
        ap.error("give targets (--email/--user-id/--file) and/or --exposure-audit")

    client = AsyncIOMotorClient(url)
    db = client[args.db]
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "db": args.db, "mode": "READ-ONLY dry run",
              "targets": []}
    totals = {"deletable": 0, "blocked": 0, "not_found": 0}
    try:
        for token in dict.fromkeys(targets):
            user = await _resolve(db, token)
            if not user:
                report["targets"].append({"target": token, "status": "NOT FOUND"})
                totals["not_found"] += 1
                continue
            reasons = []
            if args.acting_admin_id and user["user_id"] == args.acting_admin_id:
                reasons.append("You cannot delete your own account")
            if user.get("role") == "admin":
                reasons.append("Admin accounts cannot be deleted")
            reasons += await financial_blockers(db, user)
            remove = await _would_remove(db, user)
            entry = {
                "target": token, "user_id": user["user_id"], "email": user.get("email"), "name": user.get("name"),
                "role": user.get("role"), "deactivated": bool(user.get("deleted")),
                "status": "BLOCKED" if reasons else "DELETABLE", "blocked_because": reasons,
                "would_remove": {k: len(v) for k, v in remove.items() if v},
                "retained": await _retained(db, user),
                "recorded_identities": {"email": _norm_email(user.get("email")),
                                           "phones": [p for p in [user.get("phone"), *(user.get("alt_phones") or [])] if p]},
            }
            report["targets"].append(entry)
            totals["blocked" if reasons else "deletable"] += 1
            if args.backup_dir and not reasons:
                out = Path(args.backup_dir)
                out.mkdir(parents=True, exist_ok=True)
                (out / f"{user['user_id']}.json").write_text(json.dumps(remove, indent=2, default=str), encoding="utf-8")
        report["totals"] = totals
        if args.exposure_audit:
            report["exposure_audit"] = await _exposure_audit(db)
    finally:
        client.close()

    for t in report["targets"]:
        if t["status"] == "NOT FOUND":
            print(f"- {t['target']}: NOT FOUND")
            continue
        print(f"- {t['email']} ({t['user_id']}, {t['role']}{', deactivated' if t['deactivated'] else ''}): {t['status']}")
        for r in t["blocked_because"]:
            print(f"    blocked: {r}")
        print(f"    would remove: {t['would_remove']}")
        print(f"    retained:     {t['retained'] or '{}'}")
    if targets:
        print(f"TOTAL deletable={totals['deletable']} blocked={totals['blocked']} not_found={totals['not_found']}")
    if args.exposure_audit:
        print("EXPOSURE AUDIT:", json.dumps(report["exposure_audit"], indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"report written to {args.json}")
    if args.backup_dir:
        print(f"backups (deletable targets only) written to {args.backup_dir}")


if __name__ == "__main__":
    asyncio.run(main())
