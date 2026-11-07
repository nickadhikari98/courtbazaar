"""Test helper: make a counsel a valid target for a new hearing request.

hearings.create_hearing_request (and the targeted path of
counsel_matching.discover_candidates) only accept a counsel who passes
counsel_matching.verified_counsel_query() — the same gate as the public
listing — so a real target always has a verified profile. Sets only the two
verification flags, leaving any profile fields a test already set (e.g.
negotiation_enabled, pricing) as they are.
"""
import counsel_matching


async def verify_counsel(db, user_id):
    await db.proxy_counsel_profiles.update_one(
        {"user_id": user_id}, {"$set": counsel_matching.verified_counsel_query()}, upsert=True,
    )
