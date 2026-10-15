"""scripts/user_deletion_dry_run.py must predict exactly what
audit_log.permanently_delete_users then does — same blockers, same rows
removed — and must not write anything itself. Runs against the throwaway
test DB from conftest.py.
"""
import asyncio
import importlib.util
import os
import sys
import uuid
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
from audit_log import permanently_delete_users  # noqa: E402

_spec = importlib.util.spec_from_file_location("user_deletion_dry_run", BACKEND / "scripts" / "user_deletion_dry_run.py")
dry_run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dry_run)


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _uid(p):
    return f"test_dry_{p}_{uuid.uuid4().hex[:10]}"


async def _snapshot(db):
    return {c: await db[c].count_documents({}) for c in sorted(await db.list_collection_names())}


def test_dry_run_predicts_the_real_delete_and_writes_nothing():
    async def body():
        db = _db()
        try:
            admin = {"user_id": _uid("admin"), "role": "admin"}
            uid = _uid("counsel")
            email = f"{uid}@cbqa.in"
            user = {"user_id": uid, "email": email, "name": "Dry", "role": "advocate", "phone": "9111111111"}
            await db.users.insert_one(dict(user))
            await db.user_sessions.insert_one({"user_id": uid, "session_token": uuid.uuid4().hex})
            await db.proxy_counsel_profiles.insert_one({"user_id": uid, "kyc_status": "approved"})
            await db.availability_slots.insert_many([{"slot_id": _uid("s"), "user_id": uid} for _ in range(3)])
            await db.calendar_events.insert_one({"event_id": _uid("e"), "user_id": uid})
            lead_id = _uid("lead")
            await db.leads.insert_one({"lead_id": lead_id, "converted_user_id": uid})
            await db.lead_documents.insert_one({"lead_id": lead_id, "doc_id": _uid("d"), "storage_path": "x"})
            await db.hearing_requests.insert_one({"hearing_id": _uid("h"), "proxy_counsel_user_id": uid, "status": "completed"})

            target = await dry_run._resolve(db, email)
            before = await _snapshot(db)
            predicted = {k: len(v) for k, v in (await dry_run._would_remove(db, target)).items() if v}
            retained = await dry_run._retained(db, target)
            blockers = await dry_run.financial_blockers(db, target)
            await dry_run._exposure_audit(db)
            assert await _snapshot(db) == before  # the dry run itself wrote nothing

            assert blockers == []
            assert predicted == {"users": 1, "user_sessions": 1, "proxy_counsel_profiles": 1,
                                 "availability_slots": 3, "calendar_events": 1, "leads": 1, "lead_documents": 1}
            assert retained == {"hearing_requests": 1}

            result = await permanently_delete_users(db, [uid], admin)
            assert result["deleted"] == [uid]
            after = await _snapshot(db)
            actually_removed = {c: before[c] - after.get(c, 0) for c in before if before[c] - after.get(c, 0) > 0}
            assert actually_removed == predicted
        finally:
            db.client.close()
    asyncio.run(body())


def test_dry_run_reports_the_same_blockers_as_the_endpoint():
    async def body():
        db = _db()
        try:
            uid = _uid("busy")
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@cbqa.in", "role": "client", "wallet_balance": 10.0})
            target = await dry_run._resolve(db, uid)
            predicted = await dry_run.financial_blockers(db, target)
            result = await permanently_delete_users(db, [uid], {"user_id": _uid("admin"), "role": "admin"})
            assert result["skipped"] == [{"user_id": uid, "reason": "; ".join(predicted)}]
        finally:
            db.client.close()
    asyncio.run(body())
