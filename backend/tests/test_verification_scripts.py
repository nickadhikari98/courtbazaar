"""The two one-time verification scripts, run against the conftest's throwaway
DB with stand-in records (same ids as production, nothing else). Covers dry
run (no writes), refused applies, every skip/abort reason, and that an apply
writes only the intended fields.
"""
import asyncio
import importlib.util
import os
import sys
import unittest.mock

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(BACKEND, "scripts", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


revoke = _load("revoke_tested_proxycouncel_verification")
backfill = _load("backfill_verification_source")
VERIFIED = {"kyc_status": "approved", "bar_council_verified": True}
PROFILE_EXTRA = {"bio": "keep", "pricing": {"district": {"morning": 900.0}}, "courts": ["c1"],
                 "availability_mode": True, "updated_at": "old"}


def _db():
    return AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "courtbazaar")]


def _sync(fn):
    """Runs fn(db) in a fresh event loop with a client created inside it."""
    async def go():
        return await fn(_db())
    return asyncio.run(go())


def _run(mod, *argv):
    async def go():
        with unittest.mock.patch.object(sys, "argv", ["script", *argv]):
            return await mod.main()
    return asyncio.run(go())


def _ids():
    return [revoke.TARGET_USER_ID] + [u for u, _l, _n in backfill.ALLOWLIST]


async def _reset(db):
    ids = _ids()
    await db.users.delete_many({"user_id": {"$in": ids}})
    await db.proxy_counsel_profiles.delete_many({"user_id": {"$in": ids}})
    await db.leads.delete_many({"converted_user_id": {"$in": ids}})
    await db.audit_log.delete_many({"details.target_user_id": {"$in": ids}})


async def _seed(db):
    await _reset(db)
    await db.users.insert_one({"user_id": revoke.TARGET_USER_ID, "name": revoke.EXPECTED_NAME})
    await db.proxy_counsel_profiles.insert_one({"user_id": revoke.TARGET_USER_ID, **VERIFIED, **PROFILE_EXTRA})
    await db.leads.insert_one({"lead_id": revoke.EXPECTED_LEAD_ID, "role_applied_for": "proxy_counsel",
                               "status": "rejected", "converted_user_id": revoke.TARGET_USER_ID})
    for user_id, lead_id, name in backfill.ALLOWLIST:
        await db.users.insert_one({"user_id": user_id, "name": name})
        await db.proxy_counsel_profiles.insert_one({"user_id": user_id, **VERIFIED, **PROFILE_EXTRA})
        await db.leads.insert_one({"lead_id": lead_id, "role_applied_for": "proxy_counsel",
                                   "status": "approved", "converted_user_id": user_id})


async def _profiles(db):
    return {p["user_id"]: p for p in await db.proxy_counsel_profiles.find(
        {"user_id": {"$in": _ids()}}, {"_id": 0}).to_list(10)}


@pytest.fixture
def db():
    _sync(_seed)
    yield
    _sync(_reset)


def _profiles_now():
    return _sync(_profiles)


# --- revoke_tested_proxycouncel_verification -------------------------------

def test_revoke_dry_run_writes_nothing(db, capsys):
    before = _profiles_now()
    assert _run(revoke) == 0
    assert _profiles_now() == before
    assert "Dry run: no changes made." in capsys.readouterr().out


def test_revoke_apply_needs_exact_confirmation(db):
    before = _profiles_now()
    assert _run(revoke, "--apply") == 2
    assert _run(revoke, "--apply", "--confirm-user-id", "user_wrong") == 2
    assert _profiles_now() == before


def test_revoke_apply_changes_only_the_three_fields_on_the_target(db):
    # Seeded profile has no verification_source: the missing-source case.
    assert "verification_source" not in _profiles_now()[revoke.TARGET_USER_ID]
    before = _profiles_now()
    assert _run(revoke, "--apply", "--confirm-user-id", revoke.TARGET_USER_ID) == 0
    after = _profiles_now()
    t_before, t_after = before[revoke.TARGET_USER_ID], after[revoke.TARGET_USER_ID]
    assert t_after["kyc_status"] == "rejected" and t_after["bar_council_verified"] is False
    assert {k for k in t_before if t_before[k] != t_after.get(k)} == {"kyc_status", "bar_council_verified", "updated_at"}
    assert {u: p for u, p in after.items() if u != revoke.TARGET_USER_ID} == \
           {u: p for u, p in before.items() if u != revoke.TARGET_USER_ID}
    assert _run(revoke) == 1, "a second run must abort: nothing left to revoke"


@pytest.mark.parametrize("mutation", [
    ("leads", {"lead_id": revoke.EXPECTED_LEAD_ID}, {"status": "approved"}),
    ("leads", {"lead_id": revoke.EXPECTED_LEAD_ID}, {"converted_user_id": "user_someone_else"}),
    ("users", {"user_id": revoke.TARGET_USER_ID}, {"name": "Someone Else"}),
    ("users", {"user_id": revoke.TARGET_USER_ID}, {"deleted": True}),
    ("proxy_counsel_profiles", {"user_id": revoke.TARGET_USER_ID}, {"bar_council_verified": False}),
])
def test_revoke_aborts_on_any_mismatch(db, mutation):
    coll, flt, change = mutation
    _sync(lambda d: d[coll].update_one(flt, {"$set": change}))
    before = _profiles_now()
    assert _run(revoke, "--apply", "--confirm-user-id", revoke.TARGET_USER_ID) == 1
    assert _profiles_now() == before


@pytest.mark.parametrize("source", [
    {"type": "admin"},
    {"type": "lead", "lead_id": "lead_some_other_application"},
    None,
    "lead",
    {"type": "lead", "lead_id": revoke.EXPECTED_LEAD_ID, "extra": "unexpected"},
])
def test_revoke_refuses_any_verification_source_but_this_lead(db, capsys, source):
    """An admin's independent verification (or anything else unexpected) must
    never be revoked by the script, even with --apply and confirmation."""
    _sync(lambda d: d.proxy_counsel_profiles.update_one(
        {"user_id": revoke.TARGET_USER_ID}, {"$set": {"verification_source": source}}))
    before = _profiles_now()
    assert _run(revoke, "--apply", "--confirm-user-id", revoke.TARGET_USER_ID) == 1
    assert _profiles_now() == before
    assert "refusing to revoke" in capsys.readouterr().out


def test_revoke_allowed_when_source_is_exactly_this_lead(db):
    _sync(lambda d: d.proxy_counsel_profiles.update_one(
        {"user_id": revoke.TARGET_USER_ID}, {"$set": {"verification_source": dict(revoke.EXPECTED_SOURCE)}}))
    before = _profiles_now()[revoke.TARGET_USER_ID]
    assert _run(revoke, "--apply", "--confirm-user-id", revoke.TARGET_USER_ID) == 0
    after = _profiles_now()[revoke.TARGET_USER_ID]
    assert after["kyc_status"] == "rejected" and after["bar_council_verified"] is False
    assert {k for k in before if before[k] != after.get(k)} == {"kyc_status", "bar_council_verified", "updated_at"}
    assert after["verification_source"] == revoke.EXPECTED_SOURCE


def test_revoke_aborts_if_another_proxy_application_is_approved(db):
    _sync(lambda d: d.leads.insert_one({"lead_id": "lead_other_approved", "role_applied_for": "proxy_counsel",
                                        "status": "approved", "converted_user_id": revoke.TARGET_USER_ID}))
    before = _profiles_now()
    assert _run(revoke, "--apply", "--confirm-user-id", revoke.TARGET_USER_ID) == 1
    assert _profiles_now() == before


# --- backfill_verification_source ------------------------------------------

def test_backfill_dry_run_reports_all_eligible_and_writes_nothing(db, capsys):
    before = _profiles_now()
    assert _run(backfill) == 0
    out = capsys.readouterr().out
    assert _profiles_now() == before
    assert "Summary: 3 eligible, 0 skipped, 0 updated (dry run: no changes made)." in out


@pytest.mark.parametrize("label,coll,flt,change", [
    ("deactivated", "users", {"user_id": "user_1043859e9824"}, {"$set": {"deleted": True}}),
    ("name mismatch", "users", {"user_id": "user_1043859e9824"}, {"$set": {"name": "Other"}}),
    ("source already set", "proxy_counsel_profiles", {"user_id": "user_1043859e9824"}, {"$set": {"verification_source": {"type": "admin"}}}),
    ("not verified", "proxy_counsel_profiles", {"user_id": "user_1043859e9824"}, {"$set": {"kyc_status": "rejected"}}),
    ("lead not approved", "leads", {"lead_id": "lead_1273623cebbe"}, {"$set": {"status": "rejected"}}),
    ("lead linked elsewhere", "leads", {"lead_id": "lead_1273623cebbe"}, {"$set": {"converted_user_id": "user_x"}}),
])
def test_backfill_skips_any_record_failing_validation(db, capsys, label, coll, flt, change):
    _sync(lambda d: d[coll].update_one(flt, change))
    assert _run(backfill) == 0
    out = capsys.readouterr().out
    assert "SKIP     user_1043859e9824" in out, f"{label}: not skipped"
    assert "Summary: 2 eligible, 1 skipped" in out


def test_backfill_skips_multiple_applications_and_admin_audit_evidence(db, capsys):
    _sync(lambda d: d.leads.insert_one({"lead_id": "lead_second", "role_applied_for": "proxy_counsel",
                                        "status": "rejected", "converted_user_id": "user_a30f64eea1a9"}))
    _sync(lambda d: d.audit_log.insert_one({"action": "practice.approve_kyc", "details": {"target_user_id": "user_d5a6ff2cbd29"}}))
    assert _run(backfill) == 0
    out = capsys.readouterr().out
    assert "SKIP     user_a30f64eea1a9" in out and "ambiguous" in out
    assert "SKIP     user_d5a6ff2cbd29" in out and "independently verified" in out
    assert "Summary: 1 eligible, 2 skipped" in out


def test_backfill_apply_needs_matching_confirm_count(db):
    before = _profiles_now()
    assert _run(backfill, "--apply") == 2
    assert _run(backfill, "--apply", "--confirm-count", "2") == 2
    assert _profiles_now() == before


def test_backfill_apply_sets_only_verification_source_on_eligible_records(db, capsys):
    _sync(lambda d: d.users.update_one({"user_id": "user_d5a6ff2cbd29"}, {"$set": {"deleted": True}}))  # one skipped
    before = _profiles_now()
    assert _run(backfill, "--apply", "--confirm-count", "2") == 0
    after = _profiles_now()
    assert "Summary: 2 eligible, 1 skipped, 2 updated." in capsys.readouterr().out
    for user_id, lead_id, _n in backfill.ALLOWLIST:
        changed = {k for k in set(before[user_id]) | set(after[user_id]) if before[user_id].get(k) != after[user_id].get(k)}
        if user_id == "user_d5a6ff2cbd29":
            assert changed == set(), "skipped record must not change"
        else:
            assert changed == {"verification_source"}
            assert after[user_id]["verification_source"] == {"type": "lead", "lead_id": lead_id}
    assert after[revoke.TARGET_USER_ID] == before[revoke.TARGET_USER_ID], "non-allowlisted record untouched"
