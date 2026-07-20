"""One-time (but safely rerunnable) backfill: geocode courts missing lat/lng.

The Courts collection (`db.courts`) is the platform's single source of truth
for court data — names, types (`type`), service availability (`serviceable`),
and now coordinates. The canonical schema is unchanged by this script; it
only ever adds three new, nullable fields: `latitude`, `longitude`, and
`geocoded_at`. Nominatim (OpenStreetMap's geocoder) is called ONLY from this
offline script, never from a request path, so page loads never depend on a
third-party geocoding service.

Usage:
    cd backend
    python scripts/import_court_coordinates.py            # writes coordinates
    python scripts/import_court_coordinates.py --dry-run   # report only, no writes

Configuration (env vars, both optional — sensible defaults match Nominatim's
public instance):
    NOMINATIM_URL         default: https://nominatim.openstreetmap.org/search
    NOMINATIM_USER_AGENT  default: CourtBazaarCoordImport/1.0 (contact: platform admin via CourtBazaar app)

Behavior:
- Reads every court in `db.courts` missing `latitude`/`longitude`.
- Geocodes each via Nominatim (~1 req/sec, per Nominatim's usage policy:
  https://operations.osmfoundation.org/policies/nominatim/), with a
  descriptive User-Agent and up to 2 retries with backoff on transient
  failures (timeouts, 429s, 5xxs).
- A match is written (`latitude`, `longitude`, `geocoded_at`) only when
  confident: the court's state name appears in Nominatim's `display_name`.
  Ambiguous matches (state name absent — e.g. a generic/wrong-region hit)
  are NOT written; they're reported separately for manual review instead of
  risking an incorrect pin on the map.
- Never touches any other field, never overwrites a court that already has
  coordinates (those are excluded by the query up front, so reruns are
  idempotent and only ever process courts still missing coordinates).
- True failures (no Nominatim result at all, or repeated request errors) are
  logged to scripts/court_geocode_failures.log for manual follow-up.
- `--dry-run` runs the full geocoding pass and prints the same summary, but
  writes nothing to the database — useful for previewing confidence/failure
  counts before committing.
"""
import argparse
import asyncio
import logging
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")
sys.stdout.reconfigure(line_buffering=True)  # visible progress even when redirected to a file

from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
NOMINATIM_USER_AGENT = os.environ.get(
    "NOMINATIM_USER_AGENT",
    "CourtBazaarCoordImport/1.0 (contact: platform admin via CourtBazaar app)",
)
REQUEST_INTERVAL_SECONDS = 1.1  # Nominatim policy: max 1 req/sec
MAX_RETRIES = 2

LOG_PATH = Path(__file__).resolve().parent / "court_geocode_failures.log"

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("import_court_coordinates")


def clean_state_name(state_name: str) -> str:
    """Strips parenthetical qualifiers (e.g. "Delhi (NCT)" -> "Delhi") that
    match Nominatim's canonical place names but break free-text search when
    left in — Nominatim indexes places by their plain name, not official
    administrative suffixes."""
    return re.sub(r"\s*\([^)]*\)", "", state_name or "").strip()


def build_queries(court: dict) -> list[str]:
    """Query variants to try, in order, until one gets a confident match.

    `district` on this collection is often an internal judicial zone name
    (e.g. "North West", "Central") rather than a place Nominatim indexes, so
    a district-based query alone frequently misses courts that the existing
    free-text `address` field (e.g. "Tis Hazari, Delhi", "CGO Complex, New
    Delhi") geocodes correctly. Try district first (more specific when it
    works), then fall back to address."""
    state_name = clean_state_name(court.get("state_name", ""))
    queries = []

    district_parts = [court["name"]]
    if court.get("district"):
        district_parts.append(court["district"])
    if state_name:
        district_parts.append(state_name)
    district_parts.append("India")
    queries.append(", ".join(district_parts))

    if court.get("address"):
        address_parts = [court["name"], court["address"]]
        if state_name:
            address_parts.append(state_name)
        address_parts.append("India")
        address_query = ", ".join(address_parts)
        if address_query not in queries:
            queries.append(address_query)

    return queries


def geocode(query: str) -> dict | None:
    """Returns the top Nominatim match, or None if not found after retries."""
    params = {"q": query, "format": "json", "limit": 1, "countrycodes": "in"}
    headers = {"User-Agent": NOMINATIM_USER_AGENT}
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.RequestException(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            results = resp.json()
            return results[0] if results else None
        except requests.RequestException as exc:
            if attempt < MAX_RETRIES:
                backoff = 2 * (attempt + 1)
                logger.info(f"  retry {attempt + 1}/{MAX_RETRIES} after error ({exc}); waiting {backoff}s")
                time.sleep(backoff)
            else:
                logger.info(f"  geocoding failed after {MAX_RETRIES} retries: {exc}")
                return None
    return None


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Geocode and report, but write nothing to the database.")
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "courtbazaar")
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    try:
        await client.admin.command("ping")
    except Exception as exc:
        print(f"Cannot reach MongoDB at {mongo_url}: {exc}")
        sys.exit(1)

    missing = await db.courts.find(
        {"$or": [{"latitude": None}, {"latitude": {"$exists": False}}]}
    ).to_list(5000)

    total = len(missing)
    if total == 0:
        print("No courts are missing coordinates. Nothing to do.")
        return

    mode = "DRY RUN (no writes)" if args.dry_run else "LIVE"
    print(f"Found {total} court(s) missing coordinates. Geocoding at ~1 req/sec… [{mode}]\n")

    succeeded = []
    needs_review = []
    failed = []

    for i, court in enumerate(missing, 1):
        queries = build_queries(court)
        state_name_lower = clean_state_name(court.get("state_name", "")).lower()
        print(f"[{i}/{total}] {court['name']} ({court['court_id']})")

        outcome = None  # ("ok", lat, lon) | ("ambiguous", display_name) | None
        for qi, query in enumerate(queries):
            label = "district-based" if qi == 0 else "address-based"
            print(f"  trying {label} query: \"{query}\"")
            result = geocode(query)
            time.sleep(REQUEST_INTERVAL_SECONDS)  # rate-limit every Nominatim call, not just per-court

            if result is None:
                continue

            display_name = result.get("display_name", "")
            confident = bool(state_name_lower) and state_name_lower in display_name.lower()
            if confident:
                outcome = ("ok", float(result["lat"]), float(result["lon"]))
                break
            outcome = ("ambiguous", display_name)  # keep trying other variants, but remember this as a fallback

        if outcome is None:
            failed.append((court, "no Nominatim match"))
            print("  -> FAILED: no match")
        elif outcome[0] == "ambiguous":
            needs_review.append((court, outcome[1]))
            print(f"  -> SKIPPED (ambiguous match, not written): \"{outcome[1]}\"")
        else:
            _, lat, lon = outcome
            try:
                if not args.dry_run:
                    await db.courts.update_one(
                        {"court_id": court["court_id"]},
                        {"$set": {
                            "latitude": lat,
                            "longitude": lon,
                            "geocoded_at": datetime.now(timezone.utc).isoformat(),
                        }},
                    )
                succeeded.append(court)
                print(f"  -> OK: ({lat}, {lon})")
            except Exception as exc:
                # A DB hiccup on one court must not abort the whole batch —
                # every prior write already committed, and this court simply
                # stays "missing coordinates" so the next run retries it.
                failed.append((court, f"database write failed: {exc}"))
                print(f"  -> FAILED: database write error ({exc})")

    print("\n" + "=" * 60)
    print(f"Total processed:       {total}")
    print(f"Successfully geocoded: {len(succeeded)}{' (dry run — not written)' if args.dry_run else ''}")
    print(f"Needs manual review:   {len(needs_review)} (ambiguous match, not written)")
    print(f"Failed (no coords):    {len(failed)}")
    print("=" * 60)

    if failed or needs_review:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n--- Run at {time.strftime('%Y-%m-%d %H:%M:%S')} [{mode}] ---\n")
            for court, reason in failed:
                f.write(f"FAILED  | {court['court_id']} | {court['name']} | {reason}\n")
            for court, display_name in needs_review:
                f.write(f"REVIEW  | {court['court_id']} | {court['name']} | ambiguous match: {display_name}\n")
        print(f"\nDetails logged to {LOG_PATH}")

    if failed:
        print("\nCourts still missing coordinates (rerun this script to retry):")
        for court, reason in failed:
            print(f"  - {court['name']} ({court['court_id']}): {reason}")

    if needs_review:
        print("\nCourts skipped as ambiguous (need manual coordinate entry/verification):")
        for court, display_name in needs_review:
            print(f"  - {court['name']} ({court['court_id']}): closest match was \"{display_name}\"")


if __name__ == "__main__":
    asyncio.run(main())
