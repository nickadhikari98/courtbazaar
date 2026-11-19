"""One-time fix for ONE record: withdraw public visibility of the
Tested-ProxyCouncel counsel, whose proxy counsel application was approved and
later rejected before leads._withdraw_lead_verification existed (so the
rejection never revoked the verification it had granted).

Changes exactly three fields on exactly one proxy_counsel_profiles row —
kyc_status -> "rejected", bar_council_verified -> False, updated_at — the same
thing practice.revoke_verification does. About, pricing, availability and
every other field are left as they are; nothing is deleted.

    cd backend
    python scripts/revoke_tested_proxycouncel_verification.py                 # dry run (default): checks + shows the change
    python scripts/revoke_tested_proxycouncel_verification.py --apply --confirm-user-id user_74654b56c744

Refuses to change anything unless ALL of these hold for the target:
  - the users row exists, is named "Tested-ProxyCouncel" and isn't deactivated
  - lead lead_5bde64f266d4 is a proxy_counsel lead converted to the target and is "rejected"
  - no proxy_counsel lead for this account is currently "approved"
  - the profile is currently verified (kyc_status approved + bar_council_verified True)
  - its verification_source is missing (pre-tracking) or exactly
    {"type": "lead", "lead_id": "lead_5bde64f266d4"}: an admin's (or any
    other) verification is never revoked
The update itself is also conditioned on that verified state and source, so a
concurrent change makes it a no-op instead of overwriting something unexpected.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

TARGET_USER_ID = "user_74654b56c744"  # Tested-ProxyCouncel, from GET /api/public/proxy-counsels on 2026-11-06
EXPECTED_NAME = "Tested-ProxyCouncel"
EXPECTED_LEAD_ID = "lead_5bde64f266d4"  # its rejected application (admin leads list, 2026-11-06)
EXPECTED_SOURCE = {"type": "lead", "lead_id": EXPECTED_LEAD_ID}  # same key order leads.py writes
CHANGED_FIELDS = ("kyc_status", "bar_council_verified", "updated_at")


def _arg(name):
    for i, a in enumerate(sys.argv):
        if a == name and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


async def main() -> int:
    apply = "--apply" in sys.argv
    if apply and _arg("--confirm-user-id") != TARGET_USER_ID:
        print(f"Refusing: --apply needs --confirm-user-id {TARGET_USER_ID}")
        return 2

    db_name = os.environ.get("DB_NAME", "courtbazaar")
    db = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[db_name]
    print(f"Database: {db_name}   Target: {TARGET_USER_ID} / {EXPECTED_LEAD_ID}   Mode: {'APPLY' if apply else 'dry run'}")

    user = await db.users.find_one({"user_id": TARGET_USER_ID}, {"_id": 0, "name": 1, "deleted": 1})
    profile = await db.proxy_counsel_profiles.find_one({"user_id": TARGET_USER_ID}, {"_id": 0})
    leads = await db.leads.find(
        {"converted_user_id": TARGET_USER_ID, "role_applied_for": "proxy_counsel"},
        {"_id": 0, "lead_id": 1, "status": 1},
    ).to_list(20)

    problems = []
    if not user:
        problems.append("no users row for target")
    elif user.get("name") != EXPECTED_NAME:
        problems.append(f"users.name is {user.get('name')!r}, expected {EXPECTED_NAME!r}")
    elif user.get("deleted"):
        problems.append("account is deactivated")
    expected_lead = next((l for l in leads if l.get("lead_id") == EXPECTED_LEAD_ID), None)
    if not expected_lead:
        problems.append(f"lead {EXPECTED_LEAD_ID} is not a proxy_counsel lead converted to target (found: {leads})")
    elif expected_lead.get("status") != "rejected":
        problems.append(f"lead {EXPECTED_LEAD_ID} status is {expected_lead.get('status')!r}, expected 'rejected'")
    if any(l.get("status") == "approved" for l in leads):
        problems.append(f"a proxy_counsel lead for target is still approved: {leads}")
    if not profile:
        problems.append("no proxy_counsel_profiles row for target")
    elif not (profile.get("kyc_status") == "approved" and profile.get("bar_council_verified") is True):
        problems.append(f"profile not currently verified (kyc_status={profile.get('kyc_status')!r}, "
                        f"bar_council_verified={profile.get('bar_council_verified')!r}) - nothing to revoke")
    if profile and "verification_source" in profile and profile["verification_source"] != EXPECTED_SOURCE:
        # Only a verification this application granted (or one predating
        # source tracking) may be revoked — never an admin's, another lead's,
        # or anything of unexpected shape.
        problems.append(f"verification_source is {profile['verification_source']!r}, "
                        f"not {EXPECTED_SOURCE!r} - refusing to revoke")

    print(f"Leads for target: {leads}")
    if problems:
        print("ABORT, no changes made:\n  - " + "\n  - ".join(problems))
        return 1

    now = datetime.now(timezone.utc).isoformat()
    print("Change (only these fields):")
    print(f"  kyc_status:           {profile.get('kyc_status')!r} -> 'rejected'")
    print(f"  bar_council_verified: {profile.get('bar_council_verified')!r} -> False")
    print(f"  updated_at:           {profile.get('updated_at')!r} -> {now!r}")
    if not apply:
        print("Dry run: no changes made.")
        return 0

    result = await db.proxy_counsel_profiles.update_one(
        {"user_id": TARGET_USER_ID, "kyc_status": "approved", "bar_council_verified": True,
         "$or": [{"verification_source": {"$exists": False}}, {"verification_source": EXPECTED_SOURCE}]},
        {"$set": {"kyc_status": "rejected", "bar_council_verified": False, "updated_at": now}},
    )
    after = await db.proxy_counsel_profiles.find_one({"user_id": TARGET_USER_ID}, {"_id": 0})
    untouched = all(after.get(k) == v for k, v in profile.items() if k not in CHANGED_FIELDS)
    print(f"Updated {result.modified_count} row. Other fields unchanged: {untouched}")
    return 0 if result.modified_count == 1 and untouched else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
