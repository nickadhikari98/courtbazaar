"""Daily Instant Legal Help limits, one usage_daily record per identity per day.

  guest (no login)  5 messages / day, keyed by a salted hash of the client IP
  registered free   30 messages / day
  paid              unlimited messages, AI_PAID_DAILY_TOKEN_CAP tokens / day (in + out)

Days are UTC; `resets_at` is the next UTC midnight."""
import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException

GUEST_DAILY_MESSAGES = 5
FREE_DAILY_MESSAGES = 30
PAID_PLANS = {"advocate_pro", "law_firm", "enterprise"}  # server.SUBSCRIPTION_PLANS minus "free"


def paid_daily_tokens() -> int:
    return int(os.environ.get("AI_PAID_DAILY_TOKEN_CAP") or 200000)


def _today() -> datetime:
    return datetime.now(timezone.utc)


def identity(user: Optional[dict], client_ip: Optional[str]) -> Dict[str, str]:
    """Who a request counts against. Guests have no lasting identity (the
    conversation token is per chat), so they count by IP, hashed with the
    server secret so the raw address is never stored."""
    if user and user.get("user_id"):
        plan = "paid" if user.get("subscription") in PAID_PLANS else "free"
        return {"key": f"user:{user['user_id']}", "plan": plan}
    salt = os.environ.get("JWT_SECRET") or ""
    digest = hashlib.sha256(f"{salt}:{client_ip or 'unknown'}".encode("utf-8")).hexdigest()
    return {"key": f"guest:{digest}", "plan": "guest"}


def _limits(plan: str) -> Dict[str, Optional[int]]:
    if plan == "paid":
        return {"messages_limit": None, "tokens_limit": paid_daily_tokens()}
    return {"messages_limit": GUEST_DAILY_MESSAGES if plan == "guest" else FREE_DAILY_MESSAGES, "tokens_limit": None}


async def summary(db, user: Optional[dict], client_ip: Optional[str]) -> Dict[str, Any]:
    """Backing GET /ai/usage."""
    who = identity(user, client_ip)
    now = _today()
    rec = await db.ai_usage_daily.find_one({"key": who["key"], "day": now.date().isoformat()}, {"_id": 0}) or {}
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return {"plan": who["plan"], "messages_used": int(rec.get("messages", 0)), "tokens_used": int(rec.get("tokens", 0)),
            **_limits(who["plan"]), "resets_at": tomorrow.isoformat()}


def limit_message(plan: str) -> str:
    if plan == "guest":
        return f"You've used today's {GUEST_DAILY_MESSAGES} free questions. Sign up to continue."
    if plan == "free":
        return f"You've used today's {FREE_DAILY_MESSAGES} questions on the free plan. Upgrade for unlimited questions."
    return "You've reached today's usage limit for your plan. It resets at midnight UTC."


async def check(db, user: Optional[dict], client_ip: Optional[str]) -> Dict[str, str]:
    """Raises 429 when today's limit is used up; otherwise returns the identity
    to pass to record(). The reason travels in the X-Usage-Limit header (and
    the stream's error event) so the page can pick the right card."""
    usage = await summary(db, user, client_ip)
    over = (usage["messages_limit"] is not None and usage["messages_used"] >= usage["messages_limit"]) \
        or (usage["tokens_limit"] is not None and usage["tokens_used"] >= usage["tokens_limit"])
    if over:
        raise HTTPException(429, limit_message(usage["plan"]), headers={"X-Usage-Limit": usage["plan"]})
    return identity(user, client_ip)


async def record(db, who: Dict[str, str], tokens: int) -> None:
    # shortcut: check-then-record, so parallel sends can overshoot by a message or two; fine for a daily cap.
    await db.ai_usage_daily.update_one(
        {"key": who["key"], "day": _today().date().isoformat()},
        {"$inc": {"messages": 1, "tokens": max(0, int(tokens))},
         "$set": {"plan": who["plan"], "updated_at": _today().isoformat()}},
        upsert=True,
    )


async def ensure_indexes(db) -> None:
    await db.ai_usage_daily.create_index([("key", 1), ("day", 1)], name="key_day", unique=True)
