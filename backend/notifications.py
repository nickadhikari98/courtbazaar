"""Notification service - Twilio (SMS + WhatsApp) + SendGrid (Email).
Fail-soft: if keys missing, logs to console and stores in DB."""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_FROM = os.environ.get("TWILIO_PHONE_NUMBER")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
SENDGRID_KEY = os.environ.get("SENDGRID_API_KEY")
SENDGRID_FROM = os.environ.get("SENDGRID_FROM_EMAIL", "noreply@courtbazaar.in")
SENDGRID_FROM_NAME = os.environ.get("SENDGRID_FROM_NAME", "CourtBazaar")


def is_sms_enabled() -> bool:
    return bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM)


def is_whatsapp_enabled() -> bool:
    return bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_WHATSAPP_FROM)


def is_email_enabled() -> bool:
    return bool(SENDGRID_KEY)


def _format_phone(phone: str) -> str:
    if not phone:
        return phone
    if phone.startswith("+"):
        return phone
    if len(phone) == 10:
        return f"+91{phone}"
    return f"+{phone}"


def send_sms(phone: str, body: str) -> dict:
    phone = _format_phone(phone)
    if not is_sms_enabled():
        logger.info(f"[MOCK SMS] to={phone} body={body[:80]}")
        return {"channel": "sms", "to": phone, "status": "mocked", "body": body}
    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        msg = client.messages.create(body=body, from_=TWILIO_FROM, to=phone)
        return {"channel": "sms", "to": phone, "status": "sent", "sid": msg.sid}
    except Exception as e:
        logger.error(f"SMS send failed: {e}")
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


def send_email(to_email: str, subject: str, html_body: str, text_body: Optional[str] = None) -> dict:
    if not is_email_enabled():
        logger.info(f"[MOCK Email] to={to_email} subject={subject}")
        return {"channel": "email", "to": to_email, "status": "mocked", "subject": subject}
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, From
        msg = Mail(
            from_email=From(SENDGRID_FROM, SENDGRID_FROM_NAME),
            to_emails=to_email, subject=subject,
            html_content=html_body, plain_text_content=text_body or "",
        )
        sg = SendGridAPIClient(SENDGRID_KEY)
        resp = sg.send(msg)
        return {"channel": "email", "to": to_email, "status": "sent", "code": resp.status_code}
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return {"channel": "email", "to": to_email, "status": "failed", "error": str(e)}


# Templates --------------------------------------------------------------------
def tmpl_order_placed(user, order):
    base = f"CourtBazaar: Order {order['order_id']} placed for {order.get('court_name', 'court')}. Total ₹{order['pricing']['total']}. Track at courtbazaar.in"
    return {"sms": base, "whatsapp": base, "email_subject": f"Order {order['order_id']} placed",
            "email_html": f"<p>Hi {user.get('name', 'Advocate')},</p><p>Your order <b>{order['order_id']}</b> at <b>{order.get('court_name')}</b> has been placed. Total: <b>₹{order['pricing']['total']}</b>.</p><p>Track your order in real time on CourtBazaar.</p>"}


def tmpl_order_status(user, order, status):
    label = status.replace("_", " ").title()
    base = f"CourtBazaar: Order {order['order_id']} is now {label}. Vendor: {order.get('vendor_name', '—')}."
    return {"sms": base, "whatsapp": base, "email_subject": f"Order {order['order_id']}: {label}",
            "email_html": f"<p>Update on order <b>{order['order_id']}</b>:</p><p>Status: <b>{label}</b><br/>Vendor: {order.get('vendor_name', '—')}</p>"}


def tmpl_otp(otp):
    base = f"Your CourtBazaar OTP is {otp}. Valid for 5 minutes. Do not share."
    return {"sms": base, "whatsapp": base}


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
    else:
        return results

    if phone and prefs.get("sms", True):
        results.append(send_sms(phone, tmpl["sms"]))
    if phone and prefs.get("whatsapp", True):
        results.append(send_whatsapp(phone, tmpl["whatsapp"]))
    if email and prefs.get("email", True) and tmpl.get("email_subject"):
        results.append(send_email(email, tmpl["email_subject"], tmpl["email_html"]))
    return results


def status() -> dict:
    return {
        "sms_enabled": is_sms_enabled(),
        "whatsapp_enabled": is_whatsapp_enabled(),
        "email_enabled": is_email_enabled(),
    }
