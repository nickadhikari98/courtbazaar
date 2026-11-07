"""One-time backfill, DRY RUN by default: record that an explicit, reviewed
list of legacy Proxy Counsel profiles was verified by their application, so a
future rejection of that application revokes it (see
leads._withdraw_lead_verification). Profiles verified before
`verification_source` existed have none, and are otherwise left visible when
their application is rejected.

    cd backend
    python scripts/backfill_verification_source.py                       # dry run: validate + report
    python scripts/backfill_verification_source.py --apply --confirm-count N

Writes ONLY proxy_counsel_profiles.verification_source = {"type": "lead",
"lead_id": ...} for allowlisted records that pass every check below. KYC
status, bar council verification, other profile fields, pricing,
availability and roles are never touched. `--confirm-count` must equal the
number of records the run finds eligible, so an unexpected change since the
reviewed dry run aborts instead of writing.

A record is SKIPPED (and reported) unless all of these hold:
  - users row exists, has the expected name, and isn't deactivated
  - its proxy_counsel_profiles row exists, is currently verified, and has no
    verification_source yet
  - the allowlisted lead is a proxy_counsel lead converted to this user and
    currently "approved"
  - it's the only proxy_counsel lead converted to this user
  - no admin practice.approve_kyc / practice.verify_bar_council audit entry
    targets this user (that would be independent verification evidence)
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# (user_id, lead_id, expected users.name) — from the read-only production
# audit on 2026-11-06. NOT confirmed application-sourced: review the dry run.
ALLOWLIST = [
    ("user_a30f64eea1a9", "lead_bb22411f5019", "Jaydip Gavare"),
    # user_1043859e9824 (Temp-JD) excluded: profile created 5 days before lead approval, source unproven.
    ("user_d5a6ff2cbd29", "lead_646da4df651b", "Himanshu Adhikari"),
]
ADMIN_VERIFY_ACTIONS = ["practice.approve_kyc", "practice.verify_bar_council"]


def _arg(name):
    for i, a in enumerate(sys.argv):
        if a == name and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


async def _check(db, user_id, lead_id, expected_name):
    """Returns a list of reasons to skip; empty means eligible."""
    reasons = []
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "name": 1, "deleted": 1})
    if not user:
        return ["no users row"]
    if user.get("name") != expected_name:
        reasons.append(f"users.name is {user.get('name')!r}, expected {expected_name!r}")
    if user.get("deleted"):
        reasons.append("account is deactivated")
    profile = await db.proxy_counsel_profiles.find_one({"user_id": user_id}, {"_id": 0})
    if not profile:
        reasons.append("no proxy_counsel_profiles row")
    else:
        if "verification_source" in profile:
            reasons.append(f"verification_source already set: {profile['verification_source']!r}")
        if not (profile.get("kyc_status") == "approved" and profile.get("bar_council_verified") is True):
            reasons.append(f"not currently verified (kyc_status={profile.get('kyc_status')!r}, "
                           f"bar_council_verified={profile.get('bar_council_verified')!r})")
    leads = await db.leads.find({"converted_user_id": user_id, "role_applied_for": "proxy_counsel"},
                                {"_id": 0, "lead_id": 1, "status": 1}).to_list(20)
    lead = next((l for l in leads if l["lead_id"] == lead_id), None)
    if not lead:
        reasons.append(f"lead {lead_id} is not a proxy_counsel lead converted to this user (found: {leads})")
    elif lead.get("status") != "approved":
        reasons.append(f"lead {lead_id} status is {lead.get('status')!r}, expected 'approved'")
    if len(leads) > 1:
        reasons.append(f"{len(leads)} proxy_counsel leads converted to this user, ambiguous: {leads}")
    admin_events = await db.audit_log.count_documents(
        {"action": {"$in": ADMIN_VERIFY_ACTIONS}, "details.target_user_id": user_id})
    if admin_events:
        reasons.append(f"{admin_events} admin verification audit entr(y/ies): independently verified")
    return reasons


async def main() -> int:
    apply = "--apply" in sys.argv
    db_name = os.environ.get("DB_NAME", "courtbazaar")
    db = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[db_name]
    print(f"Database: {db_name}   Mode: {'APPLY' if apply else 'dry run'}   Allowlist: {len(ALLOWLIST)} record(s)\n")

    eligible, skipped = [], []
    for user_id, lead_id, name in ALLOWLIST:
        reasons = await _check(db, user_id, lead_id, name)
        if reasons:
            skipped.append((user_id, lead_id, name, reasons))
            print(f"SKIP     {user_id} ({name}) / {lead_id}")
            for r in reasons:
                print(f"           - {r}")
        else:
            eligible.append((user_id, lead_id, name))
            print(f"ELIGIBLE {user_id} ({name}) / {lead_id}: would set verification_source = "
                  f"{{'type': 'lead', 'lead_id': '{lead_id}'}}")

    updated = 0
    if apply:
        confirm = _arg("--confirm-count")
        if confirm != str(len(eligible)):
            print(f"\nRefusing to apply: --confirm-count must be {len(eligible)} (the eligible count from this run), got {confirm!r}.")
            return 2
        for user_id, lead_id, _name in eligible:
            result = await db.proxy_counsel_profiles.update_one(
                {"user_id": user_id, "verification_source": {"$exists": False},
                 "kyc_status": "approved", "bar_council_verified": True},
                {"$set": {"verification_source": {"type": "lead", "lead_id": lead_id}}},
            )
            updated += result.modified_count
            if not result.modified_count:
                print(f"NOT UPDATED {user_id}: state changed since validation")

    print(f"\nSummary: {len(eligible)} eligible, {len(skipped)} skipped, "
          f"{updated} updated{'' if apply else ' (dry run: no changes made)'}.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
