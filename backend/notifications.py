"""Notification service. Email and SMS are both dispatched through an
env-driven provider switch (EMAIL_PROVIDER / SMS_PROVIDER) so the underlying
vendor can change later without touching any call site — every caller only
ever sees notify()/send_email()/send_sms(), never a provider name.

Fail-soft throughout: if a provider isn't configured (no API key set), calls
log to console and report status "mocked" instead of raising, exactly as
before this refactor.
"""
import os
import logging
import uuid
import requests
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _raise_with_body(resp: "requests.Response") -> None:
    """requests' default HTTPError only includes the status line, not the
    provider's actual rejection reason (e.g. Brevo's {"message": "Key not
    found"}) — that body is exactly what you need to diagnose a failure, so
    surface it instead of a bare status code."""
    if resp.status_code >= 400:
        raise RuntimeError(f"{resp.status_code} {resp.reason}: {resp.text[:300]}")


EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "brevo").lower()  # brevo | resend | sendgrid
SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "fast2sms").lower()  # fast2sms | msg91 | twilio

TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_FROM = os.environ.get("TWILIO_PHONE_NUMBER")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
SENDGRID_KEY = os.environ.get("SENDGRID_API_KEY")
# No fallback address here on purpose: an unset sender must not silently
# default to a made-up address that was never verified with the provider —
# Brevo (and Resend) reject sends from an unverified sender/domain, so a
# quiet default would just trade a clear "email not configured" mock for a
# confusing rejection at send time. EMAIL_FROM_NAME is just a display label,
# not a credential, so a cosmetic default there is fine.
EMAIL_FROM = os.environ.get("EMAIL_FROM_ADDRESS")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "CourtBazaar")

# Comma-separated list of addresses that get an email whenever something needs
# admin attention outside the per-user notify() path below (e.g. a new review
# submitted for moderation). Unset -> those alerts just log, same fail-soft
# behaviour as an unconfigured EMAIL_PROVIDER. This is the extension point for
# any future "notify admins" need — add a new tmpl_*/notify_admins_* pair
# rather than routing more things through this one.
ADMIN_ALERT_EMAILS = [e.strip() for e in os.environ.get("ADMIN_ALERT_EMAILS", "").split(",") if e.strip()]

FAST2SMS_API_KEY = os.environ.get("FAST2SMS_API_KEY")
MSG91_AUTH_KEY = os.environ.get("MSG91_AUTH_KEY")
MSG91_SENDER_ID = os.environ.get("MSG91_SENDER_ID", "CRTBZR")


def is_whatsapp_enabled() -> bool:
    return bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_WHATSAPP_FROM)


def is_sms_enabled() -> bool:
    if SMS_PROVIDER == "fast2sms":
        return bool(FAST2SMS_API_KEY)
    if SMS_PROVIDER == "msg91":
        return bool(MSG91_AUTH_KEY)
    if SMS_PROVIDER == "twilio":
        return bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM)
    return False


def is_email_enabled() -> bool:
    if not EMAIL_FROM:
        return False
    if EMAIL_PROVIDER == "brevo":
        return bool(BREVO_API_KEY)
    if EMAIL_PROVIDER == "resend":
        return bool(RESEND_API_KEY)
    if EMAIL_PROVIDER == "sendgrid":
        return bool(SENDGRID_KEY)
    return False


def _format_phone(phone: str) -> str:
    if not phone:
        return phone
    if phone.startswith("+"):
        return phone
    if len(phone) == 10:
        return f"+91{phone}"
    return f"+{phone}"


def _digits_only(phone: str) -> str:
    return "".join(c for c in phone if c.isdigit())[-10:]


def _send_sms_fast2sms(phone: str, body: str) -> dict:
    resp = requests.post(
        "https://www.fast2sms.com/dev/bulkV2",
        headers={"authorization": FAST2SMS_API_KEY},
        data={"route": "q", "message": body, "language": "english", "flash": 0, "numbers": _digits_only(phone)},
        timeout=15,
    )
    _raise_with_body(resp)
    data = resp.json()
    if not data.get("return"):
        raise RuntimeError(data.get("message", "Fast2SMS send failed"))
    return {"sid": ",".join(map(str, data.get("request_id", [])))} if isinstance(data.get("request_id"), list) else {"sid": data.get("request_id")}


def _send_sms_msg91(phone: str, body: str) -> dict:
    resp = requests.post(
        "https://api.msg91.com/api/sendhttp.php",
        params={
            "authkey": MSG91_AUTH_KEY, "mobiles": f"91{_digits_only(phone)}",
            "message": body, "sender": MSG91_SENDER_ID, "route": "4", "country": "91",
        },
        timeout=15,
    )
    _raise_with_body(resp)
    return {"sid": resp.text.strip()}


def _send_sms_twilio(phone: str, body: str) -> dict:
    from twilio.rest import Client
    client = Client(TWILIO_SID, TWILIO_TOKEN)
    msg = client.messages.create(body=body, from_=TWILIO_FROM, to=_format_phone(phone))
    return {"sid": msg.sid}


def send_sms(phone: str, body: str) -> dict:
    phone = _format_phone(phone)
    if not is_sms_enabled():
        logger.info(f"[MOCK SMS via {SMS_PROVIDER}] to={phone} body={body[:80]}")
        return {"channel": "sms", "to": phone, "status": "mocked", "body": body}
    try:
        sender = {"fast2sms": _send_sms_fast2sms, "msg91": _send_sms_msg91, "twilio": _send_sms_twilio}.get(SMS_PROVIDER)
        if not sender:
            raise RuntimeError(f"Unknown SMS_PROVIDER: {SMS_PROVIDER}")
        result = sender(phone, body)
        return {"channel": "sms", "to": phone, "status": "sent", **result}
    except Exception as e:
        logger.error(f"SMS send failed ({SMS_PROVIDER}): {e}")
        return {"channel": "sms", "to": phone, "status": "failed", "error": str(e)}


def send_whatsapp(phone: str, body: str, template_vars: Optional[dict] = None) -> dict:
    """Send WhatsApp message via Twilio. body is the rendered text."""
    phone = _format_phone(phone)
    to = f"whatsapp:{phone}" if not phone.startswith("whatsapp:") else phone
    if not is_whatsapp_enabled():
        logger.info(f"[MOCK WhatsApp] to={to} body={body[:80]}")
        return {"channel": "whatsapp", "to": to, "status": "mocked", "body": body}
    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        msg = client.messages.create(body=body, from_=TWILIO_WHATSAPP_FROM, to=to)
        return {"channel": "whatsapp", "to": to, "status": "sent", "sid": msg.sid}
    except Exception as e:
        logger.error(f"WhatsApp send failed: {e}")
        return {"channel": "whatsapp", "to": to, "status": "failed", "error": str(e)}


def _send_email_brevo(to_email: str, subject: str, html_body: str, text_body: Optional[str]) -> dict:
    payload = {
        "sender": {"name": EMAIL_FROM_NAME, "email": EMAIL_FROM},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_body,
    }
    if text_body:
        payload["textContent"] = text_body
    resp = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json", "Accept": "application/json"},
        json=payload,
        timeout=15,
    )
    _raise_with_body(resp)
    return {"code": resp.status_code}


def _send_email_resend(to_email: str, subject: str, html_body: str, text_body: Optional[str]) -> dict:
    payload = {"from": f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>", "to": [to_email], "subject": subject, "html": html_body}
    if text_body:
        payload["text"] = text_body
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    _raise_with_body(resp)
    return {"code": resp.status_code}


def _send_email_sendgrid(to_email: str, subject: str, html_body: str, text_body: Optional[str]) -> dict:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, From
    msg = Mail(
        from_email=From(EMAIL_FROM, EMAIL_FROM_NAME),
        to_emails=to_email, subject=subject,
        html_content=html_body, plain_text_content=text_body or "",
    )
    resp = SendGridAPIClient(SENDGRID_KEY).send(msg)
    return {"code": resp.status_code}


def send_email(to_email: str, subject: str, html_body: str, text_body: Optional[str] = None) -> dict:
    if not is_email_enabled():
        logger.info(f"[MOCK Email via {EMAIL_PROVIDER}] to={to_email} subject={subject}")
        return {"channel": "email", "to": to_email, "status": "mocked", "subject": subject}
    try:
        sender = {"brevo": _send_email_brevo, "resend": _send_email_resend, "sendgrid": _send_email_sendgrid}.get(EMAIL_PROVIDER)
        if not sender:
            raise RuntimeError(f"Unknown EMAIL_PROVIDER: {EMAIL_PROVIDER}")
        result = sender(to_email, subject, html_body, text_body)
        return {"channel": "email", "to": to_email, "status": "sent", **result}
    except Exception as e:
        logger.error(f"Email send failed ({EMAIL_PROVIDER}): {e}")
        return {"channel": "email", "to": to_email, "status": "failed", "error": str(e)}


# Templates --------------------------------------------------------------------
def tmpl_order_placed(user, order):
    base = f"CourtBazaar: Order {order['order_id']} placed for {order.get('court_name', 'court')}. Total ₹{order['pricing']['total']}. Track at courtbazaar.com"
    return {"sms": base, "whatsapp": base, "email_subject": f"Order {order['order_id']} placed",
            "email_html": f"<p>Hi {user.get('name', 'Advocate')},</p><p>Your order <b>{order['order_id']}</b> at <b>{order.get('court_name')}</b> has been placed. Total: <b>₹{order['pricing']['total']}</b>.</p><p>Track your order in real time on CourtBazaar.</p>"}


def tmpl_order_status(user, order, status):
    label = status.replace("_", " ").title()
    base = f"CourtBazaar: Order {order['order_id']} is now {label}. Vendor: {order.get('vendor_name', '—')}."
    return {"sms": base, "whatsapp": base, "email_subject": f"Order {order['order_id']}: {label}",
            "email_html": f"<p>Update on order <b>{order['order_id']}</b>:</p><p>Status: <b>{label}</b><br/>Vendor: {order.get('vendor_name', '—')}</p>"}


def tmpl_otp(otp):
    base = f"Your CourtBazaar OTP is {otp}. Valid for 5 minutes. Do not share."
    return {
        "sms": base, "whatsapp": base,
        "email_subject": "Your CourtBazaar OTP",
        "email_html": f"<p>Your CourtBazaar OTP is <b>{otp}</b>.</p><p>Valid for 5 minutes. Do not share this code with anyone.</p>",
    }


def tmpl_hearing_event(title, body):
    """One generic template for every Hire Proxy Counsel lifecycle event
    (new request, accept/reject, payment held, verified, payout released) —
    proportionate to how internal/status-update these are, matching the
    founder's "Notifications Triggered" panel without a template per event."""
    return {"sms": f"CourtBazaar: {body}", "whatsapp": f"CourtBazaar: {body}",
            "email_subject": f"CourtBazaar — {title}", "email_html": f"<p>{body}</p>"}


LEAD_ROLE_LABELS = {
    "proxy_counsel": "Proxy Counsel",
    "counsel": "Counsel",
    "vendor": "Vendor",
    "partner": "E-Filing Partner",
    "agent": "Agent",
}


def _lead_role_label(lead):
    return LEAD_ROLE_LABELS.get(lead.get("role_applied_for"), "CourtBazaar")


def _lead_identity_phrase(lead):
    """Identity vs. capability, in the one place lead-approval copy states it
    to the applicant: a proxy_counsel lead becomes an Advocate account with
    Proxy Counsel *enabled*, not a person whose identity is "Proxy Counsel"
    (LEAD_ROLE_LABELS/_lead_role_label stay as-is for email subjects and
    admin-facing lead-type labels — those describe the application queue,
    not the applicant's identity)."""
    if lead.get("role_applied_for") == "proxy_counsel":
        return "an <b>Advocate</b>, with <b>Proxy Counsel</b> enabled"
    return f"a <b>{_lead_role_label(lead)}</b>"


def tmpl_set_password(lead, set_password_url):
    """Sent once, when an approved proxy_counsel/counsel lead produces a
    brand-new account (no existing account matched by email) — the
    Lead->Professional bridge in leads.py's _activate_professional."""
    name = lead.get("full_name") or "there"
    identity_phrase = _lead_identity_phrase(lead)
    return {
        "email_subject": "Welcome to CourtBazaar — set your password",
        "email_html": (
            f"<p>Hi {name},</p>"
            f"<p>Your application to join CourtBazaar as {identity_phrase} has been approved "
            f"and your account is ready.</p>"
            f"<p>Set your password to log in:</p>"
            f"<p><a href=\"{set_password_url}\">Set my password</a></p>"
            f"<p>This link expires in 7 days.</p>"
        ),
    }


def tmpl_lead_submitted(lead, verify_url):
    name = lead.get("full_name") or "there"
    role_label = _lead_role_label(lead)
    identity_phrase = _lead_identity_phrase(lead)
    return {
        "email_subject": f"We've received your {role_label} application",
        "email_html": (
            f"<p>Hi {name},</p>"
            f"<p>Thanks for applying to join CourtBazaar as {identity_phrase}. "
            f"Our team will review your application and get back to you shortly.</p>"
            f"<p>Please confirm your email address to keep your application moving:</p>"
            f"<p><a href=\"{verify_url}\">Verify my email address</a></p>"
            f"<p>If you didn't apply, you can safely ignore this email.</p>"
        ),
    }


def tmpl_lead_approved(lead, remark=None):
    name = lead.get("full_name") or "there"
    role_label = _lead_role_label(lead)
    remark_html = f"<p>{remark}</p>" if remark else ""
    return {
        "email_subject": f"Your {role_label} application has been approved",
        "email_html": (
            f"<p>Hi {name},</p>"
            f"<p>Good news — your application to join CourtBazaar as a <b>{role_label}</b> has been <b>approved</b>.</p>"
            f"{remark_html}"
            f"<p>Our team will follow up with next steps shortly.</p>"
        ),
    }


def tmpl_lead_rejected(lead, remark=None):
    name = lead.get("full_name") or "there"
    role_label = _lead_role_label(lead)
    remark_html = f"<p>{remark}</p>" if remark else ""
    return {
        "email_subject": f"Update on your {role_label} application",
        "email_html": (
            f"<p>Hi {name},</p>"
            f"<p>Thank you for your interest in joining CourtBazaar as a <b>{role_label}</b>. "
            f"After review, we're unable to move forward with your application at this time.</p>"
            f"{remark_html}"
        ),
    }


def tmpl_lead_more_info_requested(lead, remark=None):
    name = lead.get("full_name") or "there"
    role_label = _lead_role_label(lead)
    remark_html = f"<p>{remark}</p>" if remark else "<p>Please reach out to our team for details on what's needed.</p>"
    return {
        "email_subject": f"Action needed on your {role_label} application",
        "email_html": (
            f"<p>Hi {name},</p>"
            f"<p>We're reviewing your <b>{role_label}</b> application and need some additional information or documents before we can proceed.</p>"
            f"{remark_html}"
        ),
    }


def tmpl_review_submitted(review: dict) -> dict:
    stars = "★" * review.get("rating", 0) + "☆" * (5 - review.get("rating", 0))
    who = review.get("name") or "Someone"
    org = f" ({review['organization']})" if review.get("organization") else ""
    return {
        "email_subject": f"New review awaiting approval — {who}",
        "email_html": (
            f"<p>A new review was submitted on CourtBazaar and is pending moderation.</p>"
            f"<p><b>{who}</b>{org} — {stars}</p>"
            f"<p>{review.get('review', '')}</p>"
            f"<p>Review it in the admin console: Admin → Reviews.</p>"
        ),
    }


def notify_admins_new_review(review: dict) -> list:
    """Extension point for "notify admins" alerts — currently the only one,
    fires whenever a landing-page review is submitted (status=pending).
    Fail-soft/no-op if ADMIN_ALERT_EMAILS isn't configured, same convention
    as every other channel in this module."""
    if not ADMIN_ALERT_EMAILS:
        logger.info(f"[MOCK admin alert] new review pending approval: review_id={review.get('review_id')}")
        return []
    tmpl = tmpl_review_submitted(review)
    return [send_email(addr, tmpl["email_subject"], tmpl["email_html"]) for addr in ADMIN_ALERT_EMAILS]


def notify(user: dict, event: str, ctx: dict = None) -> list:
    """Send across SMS + WhatsApp + Email based on user prefs."""
    ctx = ctx or {}
    phone = user.get("phone")
    email = user.get("email")
    prefs = user.get("notif_prefs", {"sms": True, "whatsapp": True, "email": True})
    results = []

    tmpl = None
    if event == "order_placed":
        tmpl = tmpl_order_placed(user, ctx["order"])
    elif event == "order_status":
        tmpl = tmpl_order_status(user, ctx["order"], ctx["status"])
    elif event == "otp":
        tmpl = tmpl_otp(ctx["otp"])
    elif event == "hearing_event":
        tmpl = tmpl_hearing_event(ctx["title"], ctx["body"])
    else:
        return results

    if phone and prefs.get("sms", True):
        results.append(send_sms(phone, tmpl["sms"]))
    if phone and prefs.get("whatsapp", True):
        results.append(send_whatsapp(phone, tmpl["whatsapp"]))
    if email and prefs.get("email", True) and tmpl.get("email_subject"):
        results.append(send_email(email, tmpl["email_subject"], tmpl["email_html"]))
    return results


async def record_notification_event(db, user_id: str, event_type: str, title: str, body: str,
                                     related_entity_type: Optional[str] = None,
                                     related_entity_id: Optional[str] = None) -> None:
    """Writes the in-app Notification Center feed entry for an event. Called
    alongside notify() (not from inside it — notify() is sync and has no db
    handle) at call sites that have a real user_id to attach the event to;
    the anonymous OTP path has no such user and is skipped. Single unified
    event -> fans out to email/SMS/WhatsApp (notify()) and the in-app feed
    (this) from one call site each, not a parallel notification system."""
    await db.notification_events.insert_one({
        "notification_id": f"notif_{uuid.uuid4().hex[:14]}",
        "user_id": user_id,
        "event_type": event_type,
        "title": title,
        "body": body,
        "related_entity_type": related_entity_type,
        "related_entity_id": related_entity_id,
        "read_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def status() -> dict:
    return {
        "sms_enabled": is_sms_enabled(),
        "whatsapp_enabled": is_whatsapp_enabled(),
        "email_enabled": is_email_enabled(),
    }
