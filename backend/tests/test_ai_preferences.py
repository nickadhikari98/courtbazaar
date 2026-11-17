"""Chat preferences (GET/PATCH /ai/preferences) and the profile fields and
photo added to the existing profile endpoints."""
import asyncio
import os
import sys
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    monkeypatch.setattr(server, "db", client[os.environ["DB_NAME"]])
    yield
    client.close()


async def _new_user():
    user = {"user_id": f"user_pref_{uuid.uuid4().hex[:8]}", "email": f"{uuid.uuid4().hex[:8]}@example.com", "name": "Pref", "role": "client"}
    await server.db.users.insert_one(dict(user))
    return user


def test_defaults_for_a_new_user_and_updates_are_per_owner():
    async def body():
        a, b = await _new_user(), await _new_user()
        try:
            assert await server.ai_preferences_get(user=a) == {"answer_language": "auto", "transcript_width": "narrow", "theme": "system"}
            got = await server.ai_preferences_update(server.AIPreferences(answer_language="hi", transcript_width="wide"), user=a)
            assert got == {"answer_language": "hi", "transcript_width": "wide", "theme": "system"}
            got = await server.ai_preferences_update(server.AIPreferences(theme="dark"), user=a)
            assert got["answer_language"] == "hi" and got["theme"] == "dark"  # a partial update keeps the rest
            assert (await server.ai_preferences_get(user=b))["answer_language"] == "auto"  # another user's are untouched
            with pytest.raises(HTTPException) as exc:
                await server.ai_preferences_update(server.AIPreferences(), user=a)
            assert exc.value.status_code == 400
        finally:
            await server.db.users.delete_many({"user_id": {"$in": [a["user_id"], b["user_id"]]}})
    asyncio.run(body())


def test_unknown_keys_and_values_are_rejected():
    with pytest.raises(ValidationError):
        server.AIPreferences(font="serif")
    with pytest.raises(ValidationError):
        server.AIPreferences(answer_language="fr")
    with pytest.raises(ValidationError):
        server.AIPreferences(transcript_width="huge")


def test_preferences_need_a_signed_in_owner():
    client = TestClient(server.app)
    assert client.get("/api/ai/preferences").status_code == 401
    assert client.patch("/api/ai/preferences", json={"theme": "dark"}).status_code == 401


def test_profile_takes_display_name_and_work_type():
    with pytest.raises(ValidationError):
        server.UserProfile(work_type="Astronaut")
    with pytest.raises(ValidationError):
        server.UserProfile(display_name="x" * 41)

    async def body():
        user = await _new_user()
        try:
            out = await server.update_profile(server.UserProfile(display_name="JD", work_type="Law student"), user=user)
            assert (out["display_name"], out["work_type"], out["name"]) == ("JD", "Law student", "Pref")
        finally:
            await server.db.users.delete_many({"user_id": user["user_id"]})
    asyncio.run(body())


def test_avatar_upload_goes_through_storage_and_is_served_as_a_fresh_signed_link(monkeypatch):
    stored = {}
    monkeypatch.setattr(server, "put_object", lambda path, data, ct: stored.update(path=path, ct=ct) or {"path": path, "size": len(data)})
    monkeypatch.setattr(server, "presigned_download_url", lambda path, **kw: f"https://signed.example/{path}")

    def upload(name, ctype, data=b"img"):
        return server.upload_avatar(file=SimpleNamespace(filename=name, content_type=ctype, read=_reader(data)), user=user)

    def _reader(data):
        async def read():
            return data
        return read

    async def body():
        global user
        user = await _new_user()
        try:
            out = await upload("me.webp", "image/webp")
            assert stored["path"].startswith(f"{server.APP_NAME}/avatars/{user['user_id']}/") and stored["ct"] == "image/webp"
            assert out["avatar_url"] == f"https://signed.example/{stored['path']}"
            me = await server.auth_me(user=dict(await server.db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})))
            assert me["avatar_url"] == f"https://signed.example/{stored['path']}"
            for name, ctype in (("me.gif", "image/gif"), ("me.pdf", "application/pdf"), ("me.png", "text/html")):
                with pytest.raises(HTTPException) as exc:
                    await upload(name, ctype)
                assert exc.value.status_code == 400
            with pytest.raises(HTTPException):
                await upload("big.png", "image/png", b"x" * (server.MAX_UPLOAD_SIZE_BYTES + 1))
        finally:
            await server.db.users.delete_many({"user_id": user["user_id"]})
    asyncio.run(body())
