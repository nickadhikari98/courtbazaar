"""One-time backfill: populate proxy_counsel_profiles from already-approved
leads that predate leads.py's _derive_practice_profile_patch (see
_activate_professional). Before that fix, approving a proxy_counsel lead
created a blank profile row and never carried over what the applicant typed
into the lead form (years of practice, practice areas, language, court) —
new approvals now backfill automatically, but any counsel approved earlier
is stuck with an empty customer-facing profile until this runs once.

    cd backend
    python scripts/backfill_practice_profiles.py [--dry-run]

Only touches a profile if practice_areas/courts/languages/experience_years
are ALL still empty — a counsel who already visited their own Practice page
and filled these in themselves is left untouched, matching the same
non-destructive intent as the inline fix in _activate_professional.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

from motor.motor_asyncio import AsyncIOMotorClient

import practice as practice_svc
from leads import _derive_practice_profile_patch, _resolve_court_names_to_ids


def _profile_is_blank(profile: dict) -> bool:
    return (
        not profile.get("practice_areas")
        and not profile.get("courts")
        and not profile.get("languages")
        and not profile.get("experience_years")
    )


async def main():
    dry_run = "--dry-run" in sys.argv
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "courtbazaar")
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    try:
        await client.admin.command("ping")
    except Exception as exc:
        print(f"Cannot reach MongoDB at {mongo_url}: {exc}")
        sys.exit(1)

    leads = await db.leads.find(
        {"role_applied_for": "proxy_counsel", "status": "approved", "converted_user_id": {"$ne": None}},
        {"_id": 0, "lead_id": 1, "full_name": 1, "converted_user_id": 1, "form_data": 1},
    ).to_list(10000)

    updated, skipped_filled, skipped_empty = 0, 0, 0
    for lead in leads:
        user_id = lead["converted_user_id"]
        profile = await db.proxy_counsel_profiles.find_one({"user_id": user_id}, {"_id": 0})
        if not profile or not _profile_is_blank(profile):
            skipped_filled += 1
            continue

        patch = _derive_practice_profile_patch(lead.get("form_data") or {})
        if not patch:
            skipped_empty += 1
            continue
        if patch.get("courts"):
            patch["courts"] = await _resolve_court_names_to_ids(db, patch["courts"])

        print(f"{'[dry-run] ' if dry_run else ''}Backfilling {lead.get('full_name') or user_id}: {patch}")
        if not dry_run:
            await practice_svc.update_profile(db, user_id, patch)
        updated += 1

    print(f"\nDone. {updated} profile(s) {'would be ' if dry_run else ''}updated, "
          f"{skipped_filled} already had data, {skipped_empty} had nothing derivable from their lead form.")


if __name__ == "__main__":
    asyncio.run(main())
