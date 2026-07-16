"""CAPTCHA verification, provider-pluggable behind one function so no call
site ever needs to know which vendor is configured.

Disabled by default (CAPTCHA_PROVIDER unset/"none") so every existing and
new anonymous endpoint keeps working with zero frontend changes until this
is deliberately turned on for production. To enable it later:

  1. Set CAPTCHA_PROVIDER=turnstile (or hcaptcha / recaptcha) and
     CAPTCHA_SECRET_KEY in the environment.
  2. Have the frontend collect a token from the corresponding widget and
     send it as `captcha_token` in the request body (already accepted and
     passed through by the lead-draft and review-submit endpoints).

No other code changes needed — verify_captcha() below is the only place
that knows about provider request/response shapes, and every caller only
ever calls verify_captcha(token, remote_ip).
"""
import os
import logging
from typing import Optional

import requests
from fastapi import HTTPException

logger = logging.getLogger(__name__)

CAPTCHA_PROVIDER = os.environ.get("CAPTCHA_PROVIDER", "none").lower()  # none | turnstile | hcaptcha | recaptcha
CAPTCHA_SECRET_KEY = os.environ.get("CAPTCHA_SECRET_KEY")

_PROVIDER_VERIFY_URL = {
    "turnstile": "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    "hcaptcha": "https://hcaptcha.com/siteverify",
    "recaptcha": "https://www.google.com/recaptcha/api/siteverify",
}


def is_captcha_enabled() -> bool:
    return CAPTCHA_PROVIDER in _PROVIDER_VERIFY_URL and bool(CAPTCHA_SECRET_KEY)


def verify_captcha(token: Optional[str], remote_ip: Optional[str] = None) -> None:
    """Raises HTTPException(400) if a CAPTCHA provider is configured and the
    token fails verification. No-ops entirely if CAPTCHA isn't configured,
    so this is safe to call unconditionally from every public endpoint that
    should eventually be CAPTCHA-protected."""
    if not is_captcha_enabled():
        return
    if not token:
        raise HTTPException(400, "Captcha verification is required.")
    verify_url = _PROVIDER_VERIFY_URL[CAPTCHA_PROVIDER]
    payload = {"secret": CAPTCHA_SECRET_KEY, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    try:
        resp = requests.post(verify_url, data=payload, timeout=10)
        result = resp.json()
    except Exception as e:
        logger.error(f"Captcha verification request failed: {e}")
        raise HTTPException(400, "Captcha verification failed. Please try again.")
    if not result.get("success"):
        raise HTTPException(400, "Captcha verification failed. Please try again.")
