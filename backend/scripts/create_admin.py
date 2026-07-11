"""One-time bootstrap: create the first real admin account.

Production no longer auto-seeds any demo/admin credentials on startup (see
seed_initial_data() in server.py). Run this manually, once, on a real
deployment to create the first admin login:

    cd backend
    python scripts/create_admin.py

It prompts for email/name/password interactively so the password never
appears in shell history, a script argument, or a log line.
"""
import asyncio
import getpass
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

from motor.motor_asyncio import AsyncIOMotorClient
import bcrypt

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


async def main():
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "courtbazaar")
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    try:
        await client.admin.command("ping")
    except Exception as exc:
        print(f"Cannot reach MongoDB at {mongo_url}: {exc}")
        sys.exit(1)

    email = input("Admin email: ").strip().lower()
    if not EMAIL_RE.match(email):
        print("Invalid email address.")
        sys.exit(1)

    if await db.users.find_one({"email": email}):
        print(f"A user with email {email} already exists.")
        sys.exit(1)

    name = input("Admin name: ").strip() or "Platform Admin"

    password = getpass.getpass("Admin password (min 10 chars): ")
    if len(password) < 10:
        print("Password must be at least 10 characters.")
        sys.exit(1)
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.")
        sys.exit(1)

    admin_id = f"user_{uuid.uuid4().hex[:12]}"
    await db.users.insert_one({
        "user_id": admin_id,
        "email": email,
        "name": name,
        "role": "admin",
        "password_hash": hash_password(password),
        "phone": None,
        "verified": True,
        "wallet_balance": 0.0,
        "subscription": "enterprise",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    print(f"Admin account created: {email} ({admin_id})")


if __name__ == "__main__":
    asyncio.run(main())
