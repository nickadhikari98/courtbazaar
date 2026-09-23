"""Support-ticket emails must not let user-controlled ticket text become HTML.

Covers the three HTML emails built from ticket data:
  - tmpl_support_ticket_created      (to the submitter)
  - tmpl_support_ticket_replied      (to the submitter, carries the admin reply)
  - tmpl_support_ticket_admin_notify (to ADMIN_ALERT_EMAILS)

Also drives support_tickets.create_ticket / admin_change_status end-to-end
against a tiny in-memory fake db (no Mongo needed) to prove the escaped HTML
is what actually reaches send_email.

Assertions parse the rendered HTML with html.parser: the only tags allowed in
the output are the template's own layout tags (<p>, <b>, <br>). Any <script>,
<img> or attacker <b> surviving would show up as a real element or attribute.
"""
import asyncio
import os
import sys
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import notifications  # noqa: E402
import support_tickets  # noqa: E402

PAYLOADS = [
    "<b>Injected</b>",
    "<img src=x onerror=alert(1)>",
    "<script>alert(1)</script>",
]
COMBINED = " ".join(PAYLOADS)
TEMPLATE_TAGS = {"p", "b", "br"}


class _TagCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []   # (tag, attrs)
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, attrs))

    def handle_startendtag(self, tag, attrs):
        self.tags.append((tag, attrs))

    def handle_data(self, data):
        self.text.append(data)


def _parse(html_str):
    p = _TagCollector()
    p.feed(html_str)
    p.close()
    return p


def _assert_inert(html_str, expected_visible_texts):
    parsed = _parse(html_str)
    tag_names = {t for t, _ in parsed.tags}
    assert tag_names <= TEMPLATE_TAGS, f"unexpected tags rendered: {tag_names - TEMPLATE_TAGS}"
    # Template layout tags never carry attributes — an attribute here would
    # mean user text broke out into markup (e.g. onerror=...).
    assert all(not attrs for _, attrs in parsed.tags), parsed.tags
    for raw in ("<script", "<img", "onerror=alert(1)>", "<b>Injected"):
        assert raw not in html_str
    # The user's text is still shown to the reader, just as literal text.
    visible = "".join(parsed.text)
    for t in expected_visible_texts:
        assert t in visible
    # Escaped once, not twice.
    assert "&amp;lt;" not in html_str


def _ticket(**overrides):
    t = {
        "ticket_id": "TKT_ABC123",
        "name": COMBINED,
        "email": "a<script>@x.com",
        "category": "technical",
        "subject": COMBINED,
        "message": COMBINED,
        "order_id": "<img src=x onerror=alert(1)>",
        "status": "in_progress",
    }
    t.update(overrides)
    return t


def test_created_email_escapes_user_fields():
    out = notifications.tmpl_support_ticket_created(_ticket())
    _assert_inert(out["email_html"], PAYLOADS)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out["email_html"]
    assert "Related order:" in out["email_html"]


def test_replied_email_escapes_subject_name_and_reply():
    out = notifications.tmpl_support_ticket_replied(_ticket(), COMBINED)
    _assert_inert(out["email_html"], PAYLOADS)
    assert "status: <b>In Progress</b>" in out["email_html"]


def test_admin_notify_email_escapes_all_user_fields():
    out = notifications.tmpl_support_ticket_admin_notify(_ticket())
    _assert_inert(out["email_html"], PAYLOADS + ["a<script>@x.com"])


def test_plain_text_and_layout_unchanged_for_normal_input():
    t = _ticket(name="Asha", subject="Refund not received", message="Paid twice for order 42",
                email="asha@example.com", order_id="ORD-42")
    created = notifications.tmpl_support_ticket_created(t)["email_html"]
    assert created.startswith("<p>Hi Asha,</p>")
    assert "<b>Subject:</b> Refund not received</p>" in created
    assert "<p><b>Related order:</b> ORD-42</p>" in created
    admin = notifications.tmpl_support_ticket_admin_notify(t)["email_html"]
    assert "<b>From:</b> Asha (asha@example.com)<br>" in admin
    assert "<p>Paid twice for order 42</p>" in admin
    # Email subject header is not HTML — left as-is on purpose.
    assert notifications.tmpl_support_ticket_admin_notify(t)["email_subject"].endswith("Refund not received")


def test_apostrophes_and_ampersands_escaped_exactly_once():
    t = _ticket(name="O'Brien & Sons", subject='Say "hi" & <bye>')
    out = notifications.tmpl_support_ticket_created(t)["email_html"]
    assert "O&#x27;Brien &amp; Sons" in out
    assert "Say &quot;hi&quot; &amp; &lt;bye&gt;" in out
    assert "&amp;amp;" not in out


# ---- end-to-end through support_tickets.py with a fake db ----

class _FakeColl:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def find_one(self, q, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return dict(d)
        return None

    async def update_one(self, q, update):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(update.get("$set", {}))


class _FakeDb:
    def __init__(self):
        self.support_tickets = _FakeColl()
        self.audit_log = _FakeColl()


def test_create_and_reply_flows_send_escaped_html(monkeypatch):
    monkeypatch.setattr(notifications, "ADMIN_ALERT_EMAILS", ["admin@example.com"], raising=False)
    admin_sent = []
    monkeypatch.setattr(notifications, "send_email",
                        lambda to, subj, html_body, *a, **k: admin_sent.append((to, html_body)) or {"status": "mocked"})
    sent = []

    def fake_send(to, subject, html_body, *a, **k):
        sent.append((to, subject, html_body))
        return {"status": "mocked"}

    async def run():
        db = _FakeDb()
        res = await support_tickets.create_ticket(
            db, fake_send, name=COMBINED, email="victim@example.com", phone=None,
            category="technical", subject=COMBINED, message=COMBINED,
            order_id=None, client_ip="127.0.0.1",
        )
        # Stored raw — escaping happens only at email render time.
        stored = db.support_tickets.docs[0]
        assert stored["subject"] == COMBINED and stored["message"] == COMBINED
        await support_tickets.admin_change_status(
            db, fake_send, res["ticket_id"], "resolved", COMBINED,
            {"user_id": "admin_1", "name": "Admin"},
        )

    asyncio.run(run())

    assert len(sent) == 2  # created confirmation + reply
    for _, _, body in sent:
        _assert_inert(body, PAYLOADS)
    assert len(admin_sent) == 1
    _assert_inert(admin_sent[0][1], PAYLOADS)
