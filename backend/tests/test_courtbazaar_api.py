"""
CourtBazaar Backend API Tests
Covers: health, auth, courts, services, files, orders, payments, AI, subscriptions,
        wallet, vendor flow, admin flow, vendor onboarding, auth security
"""
import io
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fall back to frontend .env file (tests run from /app)
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip()
                    break
    except Exception:
        pass
BASE_URL = (BASE_URL or "").rstrip("/")
API = f"{BASE_URL}/api"

ADV_EMAIL = "advocate@demo.in"
ADV_PASS = "Advocate@123"
VENDOR_EMAIL = "vendor@demo.in"
VENDOR_PASS = "Vendor@123"
ADMIN_EMAIL = "admin@courtbazaar.in"
ADMIN_PASS = "Admin@123"


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


def _login(s, email, password):
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def advocate_token(s):
    return _login(s, ADV_EMAIL, ADV_PASS)


@pytest.fixture(scope="session")
def vendor_token(s):
    return _login(s, VENDOR_EMAIL, VENDOR_PASS)


@pytest.fixture(scope="session")
def admin_token(s):
    return _login(s, ADMIN_EMAIL, ADMIN_PASS)


def hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Health / catalog ----------
class TestHealth:
    def test_root(self, s):
        r = s.get(f"{API}/", timeout=15)
        assert r.status_code == 200
        assert "CourtBazaar" in r.json().get("message", "")

    def test_states(self, s):
        r = s.get(f"{API}/states", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # Expanded in P1: now 36+ states/UTs
        assert len(data) >= 36, f"expected 36+ states, got {len(data)}"

    def test_services(self, s):
        r = s.get(f"{API}/services", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 44, f"expected 44 services, got {len(data)}"

    def test_service_categories(self, s):
        r = s.get(f"{API}/services/categories", timeout=15)
        assert r.status_code == 200
        cats = r.json()
        assert isinstance(cats, list) and len(cats) > 0
        assert all("category" in c and "count" in c for c in cats)

    def test_service_detail(self, s):
        r = s.get(f"{API}/services/svc_bw_photocopy", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["service_id"] == "svc_bw_photocopy"
        assert "base_price" in data


# ---------- Auth ----------
class TestAuth:
    def test_login_advocate(self, s):
        r = s.post(f"{API}/auth/login", json={"email": ADV_EMAIL, "password": ADV_PASS}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "token" in body and isinstance(body["token"], str) and len(body["token"]) > 10
        assert body["user"]["role"] == "advocate"
        assert body["user"]["email"] == ADV_EMAIL

    def test_auth_me_returns_advocate(self, s, advocate_token):
        r = s.get(f"{API}/auth/me", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 200
        u = r.json()
        assert u["role"] == "advocate"
        assert u["email"] == ADV_EMAIL
        assert "password_hash" not in u

    def test_register_new_user(self, s):
        email = f"TEST_user_{uuid.uuid4().hex[:8]}@test.com"
        payload = {"email": email, "password": "Test@123", "name": "Test U", "role": "advocate", "phone": "9000000001"}
        r = s.post(f"{API}/auth/register", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user"]["email"] == email
        assert body["user"]["role"] == "advocate"
        assert "token" in body
        # me check
        r2 = s.get(f"{API}/auth/me", headers=hdr(body["token"]), timeout=15)
        assert r2.status_code == 200
        assert r2.json()["email"] == email

    def test_login_invalid(self, s):
        r = s.post(f"{API}/auth/login", json={"email": ADV_EMAIL, "password": "wrong"}, timeout=15)
        assert r.status_code == 401

    def test_otp_request(self, s):
        r = s.post(f"{API}/auth/otp/request", json={"phone": "9123456789"}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_otp_verify_creates_user(self, s):
        phone = f"9{uuid.uuid4().int % 1000000000:09d}"
        r = s.post(f"{API}/auth/otp/verify", json={"phone": phone, "otp": "123456", "name": "OTP Tester", "role": "advocate"}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "token" in body
        assert body["user"]["phone"] == phone

    def test_otp_verify_invalid(self, s):
        r = s.post(f"{API}/auth/otp/verify", json={"phone": "9000000099", "otp": "000000"}, timeout=15)
        assert r.status_code == 400


class TestProfile:
    def test_update_profile_persists(self, s, advocate_token):
        new_bar = f"D/TEST/{uuid.uuid4().hex[:4]}"
        new_addr = f"TEST Chamber {uuid.uuid4().hex[:4]}, Tis Hazari"
        r = s.put(f"{API}/auth/profile", headers=hdr(advocate_token),
                  json={"bar_council_id": new_bar, "chamber_address": new_addr}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["bar_council_id"] == new_bar
        assert body["chamber_address"] == new_addr
        # Re-fetch
        r2 = s.get(f"{API}/auth/me", headers=hdr(advocate_token), timeout=15)
        assert r2.json()["bar_council_id"] == new_bar
        assert r2.json()["chamber_address"] == new_addr


# ---------- Courts ----------
class TestCourts:
    def test_courts_by_state_delhi(self, s):
        r = s.get(f"{API}/courts?state_id=state_delhi", timeout=15)
        assert r.status_code == 200
        courts = r.json()
        assert isinstance(courts, list)
        # Expanded in P1: Delhi now has ~35+ courts
        assert len(courts) >= 10, f"expected 10+ courts in Delhi, got {len(courts)}"
        for c in courts:
            assert c["state_id"] == "state_delhi"

    def test_court_detail_with_vendor_count(self, s):
        r = s.get(f"{API}/courts/court_tishazari", timeout=15)
        assert r.status_code == 200
        c = r.json()
        assert c["court_id"] == "court_tishazari"
        assert "vendor_count" in c
        assert isinstance(c["vendor_count"], int)
        assert c["vendor_count"] >= 1


# ---------- Files ----------
class TestFiles:
    def test_upload_and_list(self, s, advocate_token):
        # multipart upload (no content-type override)
        files = {"file": ("TEST_doc.png", io.BytesIO(b"\x89PNG\r\n\x1a\nTEST_FILE_DATA"), "image/png")}
        headers = {"Authorization": f"Bearer {advocate_token}"}
        r = requests.post(f"{API}/files/upload", headers=headers, files=files, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "file_id" in body and "storage_path" in body
        # List my files
        r2 = s.get(f"{API}/files/mine", headers=hdr(advocate_token), timeout=15)
        assert r2.status_code == 200
        ids = [f["file_id"] for f in r2.json()]
        assert body["file_id"] in ids


# ---------- Orders ----------
ORDER_PAYLOAD = {
    "services": [{"service_id": "svc_bw_photocopy", "qty": 100}],
    "state_id": "state_delhi",
    "court_id": "court_tishazari",
    "delivery_option": "chamber",
    "delivery_address": "Chamber 42, Tis Hazari",
    "file_ids": [],
    "urgent": False,
    "notes": "TEST order",
}


class TestOrders:
    def test_quote_pricing_includes_gst_total(self, s, advocate_token):
        r = s.post(f"{API}/orders/quote", headers=hdr(advocate_token), json=ORDER_PAYLOAD, timeout=15)
        assert r.status_code == 200
        p = r.json()
        for key in ("breakdown", "subtotal", "delivery_fee", "gst", "total", "convenience_fee"):
            assert key in p, f"missing {key}"
        assert p["gst"] > 0
        assert p["total"] > p["subtotal"]

    def test_create_order_auto_matches_vendor(self, s, advocate_token):
        r = s.post(f"{API}/orders", headers=hdr(advocate_token), json=ORDER_PAYLOAD, timeout=15)
        assert r.status_code == 200, r.text
        order = r.json()
        assert order["status"] == "placed"
        assert order["court_id"] == "court_tishazari"
        assert order["vendor_id"] is not None
        assert "Sharma" in (order.get("vendor_name") or ""), f"expected Sharma vendor, got {order.get('vendor_name')}"
        assert isinstance(order["timeline"], list) and len(order["timeline"]) >= 1
        pytest.advocate_order_id = order["order_id"]

    def test_list_my_orders(self, s, advocate_token):
        r = s.get(f"{API}/orders", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 200
        orders = r.json()
        assert isinstance(orders, list) and len(orders) >= 1
        assert any(o["order_id"] == pytest.advocate_order_id for o in orders)

    def test_get_order_detail(self, s, advocate_token):
        oid = pytest.advocate_order_id
        r = s.get(f"{API}/orders/{oid}", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 200
        o = r.json()
        assert o["order_id"] == oid
        assert "timeline" in o and "pricing" in o


# ---------- Payments ----------
class TestPayments:
    def test_checkout_returns_stripe_url(self, s, advocate_token):
        oid = pytest.advocate_order_id
        r = s.post(f"{API}/payments/checkout", headers=hdr(advocate_token),
                   json={"order_id": oid, "origin_url": "https://example.com"}, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "url" in body and body["url"].startswith("http")
        assert "session_id" in body
        pytest.session_id = body["session_id"]

    def test_payment_status_pending(self, s, advocate_token):
        sid = pytest.session_id
        r = s.get(f"{API}/payments/status/{sid}", headers=hdr(advocate_token), timeout=30)
        assert r.status_code == 200
        tx = r.json()
        assert tx["session_id"] == sid
        # Initially unpaid - either 'unpaid' or 'pending'
        assert tx.get("payment_status") in ("pending", "unpaid", "no_payment_required")


# ---------- AI ----------
class TestAI:
    def test_ai_chat(self, s, advocate_token):
        sid = f"TEST_chat_{uuid.uuid4().hex[:6]}"
        r = s.post(f"{API}/ai/chat", headers=hdr(advocate_token),
                   json={"session_id": sid, "message": "What documents are needed for filing a civil suit at Tis Hazari court?"},
                   timeout=120)
        assert r.status_code == 200, r.text
        reply = r.json().get("reply", "")
        assert isinstance(reply, str) and len(reply) > 20, f"empty/short reply: {reply!r}"
        pytest.ai_session = sid

    def test_ai_history(self, s, advocate_token):
        sid = pytest.ai_session
        r = s.get(f"{API}/ai/history/{sid}", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 200
        msgs = r.json()
        assert isinstance(msgs, list) and len(msgs) >= 1

    def test_filing_checklist(self, s, advocate_token):
        r = s.post(f"{API}/ai/filing-checklist", headers=hdr(advocate_token),
                   json={"court": "Tis Hazari", "case_type": "Civil Suit"}, timeout=120)
        assert r.status_code == 200, r.text
        cl = r.json().get("checklist", "")
        assert isinstance(cl, str) and len(cl) > 30


# ---------- Subscriptions ----------
class TestSubscriptions:
    def test_plans(self, s):
        r = s.get(f"{API}/subscriptions/plans", timeout=15)
        assert r.status_code == 200
        plans = r.json()
        # current impl returns dict
        if isinstance(plans, dict):
            assert set(plans.keys()) >= {"free", "advocate_pro", "law_firm", "enterprise"}
            assert len(plans) == 4
        else:
            assert len(plans) == 4

    def test_activate(self, s, advocate_token):
        r = s.post(f"{API}/subscriptions/activate", headers=hdr(advocate_token), json={"plan": "law_firm"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["plan"] == "law_firm"
        # verify persisted
        me = s.get(f"{API}/auth/me", headers=hdr(advocate_token), timeout=15).json()
        assert me["subscription"] == "law_firm"
        # restore
        s.post(f"{API}/subscriptions/activate", headers=hdr(advocate_token), json={"plan": "advocate_pro"}, timeout=15)


# ---------- Wallet ----------
class TestWallet:
    def test_wallet_get_and_add(self, s, advocate_token):
        r = s.get(f"{API}/wallet", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 200
        before = r.json()["balance"]
        r2 = s.post(f"{API}/wallet/add", headers=hdr(advocate_token), json={"amount": 100, "description": "TEST topup"}, timeout=15)
        assert r2.status_code == 200
        after = r2.json()["balance"]
        assert round(after - before, 2) == 100.0


# ---------- Vendor flow ----------
class TestVendor:
    def test_vendor_login_and_me(self, s, vendor_token):
        r = s.get(f"{API}/vendors/me", headers=hdr(vendor_token), timeout=15)
        assert r.status_code == 200
        v = r.json()
        assert v.get("onboarded") is True
        assert "court_tishazari" in v.get("court_ids", [])

    def test_vendor_sees_matched_orders(self, s, vendor_token):
        r = s.get(f"{API}/orders", headers=hdr(vendor_token), timeout=15)
        assert r.status_code == 200
        orders = r.json()
        assert isinstance(orders, list)
        # The advocate just created an order matched to this vendor
        assert any(o.get("order_id") == pytest.advocate_order_id for o in orders), \
            f"vendor should see order {pytest.advocate_order_id}"

    def test_vendor_updates_order_status(self, s, vendor_token):
        oid = pytest.advocate_order_id
        r = s.post(f"{API}/orders/{oid}/status", headers=hdr(vendor_token),
                   json={"status": "accepted", "note": "TEST accepted"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "accepted"
        # verify timeline appended
        det = s.get(f"{API}/orders/{oid}", headers=hdr(vendor_token), timeout=15).json()
        assert any(t["status"] == "accepted" for t in det["timeline"])


# ---------- Vendor onboarding ----------
class TestVendorOnboard:
    def test_advocate_can_onboard_vendor(self, s):
        # Create new advocate user
        email = f"TEST_onbo_{uuid.uuid4().hex[:8]}@test.com"
        reg = s.post(f"{API}/auth/register", json={"email": email, "password": "Test@123", "name": "Onbo", "role": "advocate", "phone": "9000000077"}, timeout=15).json()
        tok = reg["token"]
        r = s.post(f"{API}/vendors/onboard", headers=hdr(tok), json={
            "shop_name": "TEST Shop", "owner_name": "TEST Owner", "phone": "9111111111",
            "address": "TEST Addr", "court_ids": ["court_tishazari"], "service_ids": ["svc_bw_photocopy"],
            "pan": "ABCDE1234F",
        }, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["kyc_status"] == "pending"
        # role should be updated to vendor
        me = s.get(f"{API}/auth/me", headers=hdr(tok), timeout=15).json()
        assert me["role"] == "vendor"


# ---------- Admin flow ----------
class TestAdmin:
    def test_analytics(self, s, admin_token):
        r = s.get(f"{API}/admin/analytics", headers=hdr(admin_token), timeout=20)
        assert r.status_code == 200
        a = r.json()
        for k in ("total_orders", "total_users", "total_vendors", "revenue", "platform_commission"):
            assert k in a
        assert a["total_users"] >= 3

    def test_admin_vendors(self, s, admin_token):
        r = s.get(f"{API}/admin/vendors", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_users(self, s, admin_token):
        r = s.get(f"{API}/admin/users", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200
        users = r.json()
        assert any(u["email"] == ADV_EMAIL for u in users)
        # ensure no password_hash leaks
        assert all("password_hash" not in u for u in users)

    def test_admin_update_pricing(self, s, admin_token):
        new_price = 2.5
        r = s.put(f"{API}/admin/services/svc_bw_photocopy/pricing", headers=hdr(admin_token),
                  json={"service_id": "svc_bw_photocopy", "base_price": new_price}, timeout=15)
        assert r.status_code == 200
        # verify
        svc = s.get(f"{API}/services/svc_bw_photocopy", timeout=15).json()
        assert float(svc["base_price"]) == new_price
        # restore original (2.0 typical)
        s.put(f"{API}/admin/services/svc_bw_photocopy/pricing", headers=hdr(admin_token),
              json={"service_id": "svc_bw_photocopy", "base_price": 2.0}, timeout=15)


# ---------- Auth security ----------
class TestAuthSecurity:
    def test_orders_requires_auth(self, s):
        r = requests.get(f"{API}/orders", timeout=15)
        assert r.status_code == 401

    def test_admin_endpoint_forbidden_for_non_admin(self, s, advocate_token):
        r = s.get(f"{API}/admin/analytics", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 403


# ============================================================================
# P1 FEATURES (iteration_2)
# ============================================================================

# ---------- Courts: serviceable enforcement & expanded hierarchy ----------
class TestCourtsP1:
    def test_serviceable_only_returns_delhi_only(self, s):
        r = s.get(f"{API}/courts?serviceable_only=true", timeout=15)
        assert r.status_code == 200
        courts = r.json()
        assert isinstance(courts, list)
        assert len(courts) >= 30, f"expected ~35 serviceable Delhi courts, got {len(courts)}"
        # All serviceable courts must belong to Delhi
        for c in courts:
            assert c["state_id"] == "state_delhi", f"non-Delhi court in serviceable list: {c['court_id']}"

    def test_all_courts_count(self, s):
        r = s.get(f"{API}/courts", timeout=15)
        assert r.status_code == 200
        courts = r.json()
        assert len(courts) >= 400, f"expected 400+ courts, got {len(courts)}"


# ---------- P1 Payments: Razorpay ----------
class TestPaymentsP1:
    def test_payment_methods_endpoint(self, s):
        r = s.get(f"{API}/payments/methods", timeout=15)
        assert r.status_code == 200
        b = r.json()
        assert b.get("stripe") is True
        # No keys configured -> razorpay disabled, simulated mode on
        assert b.get("razorpay") is False
        assert b.get("razorpay_simulated") is True

    def test_razorpay_create_and_verify_simulated(self, s, advocate_token):
        # Create a new order to pay via razorpay (separate from stripe-tested order)
        payload = dict(ORDER_PAYLOAD)
        payload["notes"] = "TEST razorpay order"
        ro = s.post(f"{API}/orders", headers=hdr(advocate_token), json=payload, timeout=15)
        assert ro.status_code == 200, ro.text
        order_id = ro.json()["order_id"]
        pytest.rzp_order_id = order_id

        # Create razorpay order
        r = s.post(f"{API}/payments/razorpay/create-order", headers=hdr(advocate_token),
                   json={"order_id": order_id}, timeout=15)
        assert r.status_code == 200, r.text
        rb = r.json()
        assert "razorpay_order_id" in rb
        assert rb.get("simulated") is True
        rzp_oid = rb["razorpay_order_id"]

        # Verify
        v = s.post(f"{API}/payments/razorpay/verify", headers=hdr(advocate_token),
                   json={"razorpay_order_id": rzp_oid, "razorpay_payment_id": "pay_test_1",
                         "razorpay_signature": "sig_test_1"}, timeout=15)
        assert v.status_code == 200, v.text
        assert v.json().get("ok") is True

        # Verify the order is now paid
        det = s.get(f"{API}/orders/{order_id}", headers=hdr(advocate_token), timeout=15).json()
        assert det.get("payment_status") == "paid"


# ---------- P1 Notifications ----------
class TestNotificationsP1:
    def test_notifications_status(self, s):
        r = s.get(f"{API}/notifications/status", timeout=15)
        assert r.status_code == 200
        b = r.json()
        # All providers in mock mode (no env keys configured)
        assert b.get("sms_enabled") is False
        assert b.get("whatsapp_enabled") is False
        assert b.get("email_enabled") is False

    def test_notif_prefs_update_persists(self, s, advocate_token):
        prefs = {"sms": True, "whatsapp": False, "email": True}
        r = s.put(f"{API}/notifications/prefs", headers=hdr(advocate_token), json=prefs, timeout=15)
        assert r.status_code == 200
        b = r.json()
        assert b.get("ok") is True
        assert b.get("notif_prefs") == prefs
        # Verify on me
        me = s.get(f"{API}/auth/me", headers=hdr(advocate_token), timeout=15).json()
        assert me.get("notif_prefs") == prefs

    def test_order_creation_triggers_notification_without_error(self, s, advocate_token):
        # If notifications dispatch raises, order create would 500. We already created orders in earlier tests
        # but assert again with a fresh payload.
        r = s.post(f"{API}/orders", headers=hdr(advocate_token), json=ORDER_PAYLOAD, timeout=15)
        assert r.status_code == 200, r.text

    def test_order_status_update_triggers_notification_without_error(self, s, advocate_token, vendor_token):
        # Create a fresh order so this test doesn't depend on inter-class state
        ro = s.post(f"{API}/orders", headers=hdr(advocate_token), json=ORDER_PAYLOAD, timeout=15)
        assert ro.status_code == 200, ro.text
        oid = ro.json()["order_id"]
        r = s.post(f"{API}/orders/{oid}/status", headers=hdr(vendor_token),
                   json={"status": "processing", "note": "TEST progress"}, timeout=15)
        assert r.status_code == 200, r.text


# ---------- P1 Law Firm Multi-User ----------
class TestLawFirmP1:
    def test_create_firm_and_me(self, s):
        # Create a fresh advocate to own a firm
        email = f"TEST_firmowner_{uuid.uuid4().hex[:8]}@test.com"
        reg = s.post(f"{API}/auth/register", json={
            "email": email, "password": "Test@123", "name": "Firm Owner",
            "role": "advocate", "phone": "9000000201",
        }, timeout=15).json()
        owner_tok = reg["token"]
        pytest.firm_owner_token = owner_tok
        pytest.firm_owner_email = email

        r = s.post(f"{API}/firms", headers=hdr(owner_tok),
                   json={"name": "TEST & Associates", "gst": "07ABCDE1234F1Z5", "address": "Tis Hazari"}, timeout=15)
        assert r.status_code == 200, r.text
        firm = r.json()
        assert "firm_id" in firm
        pytest.firm_id = firm["firm_id"]

        # Me should reflect firm + role
        me = s.get(f"{API}/auth/me", headers=hdr(owner_tok), timeout=15).json()
        assert me.get("firm_id") == firm["firm_id"]
        assert me.get("firm_role") == "owner"
        assert me.get("role") == "law_firm"

        # /firms/me
        r2 = s.get(f"{API}/firms/me", headers=hdr(owner_tok), timeout=15)
        assert r2.status_code == 200
        b = r2.json()
        assert b.get("onboarded") is True
        assert b.get("firm", {}).get("firm_id") == firm["firm_id"]
        assert isinstance(b.get("members"), list) and len(b["members"]) == 1
        assert b["members"][0]["role"] == "owner"

    def test_firm_invite_non_owner_forbidden(self, s, advocate_token):
        # Advocate (not in this firm) cannot invite
        r = s.post(f"{API}/firms/invite", headers=hdr(advocate_token),
                   json={"firm_id": pytest.firm_id, "email": "x@y.com", "name": "X", "role": "associate"}, timeout=15)
        assert r.status_code == 403

    def test_firm_invite_and_accept_flow(self, s):
        owner_tok = pytest.firm_owner_token
        invitee_email = f"TEST_invitee_{uuid.uuid4().hex[:8]}@test.com"
        # Owner sends invite
        r = s.post(f"{API}/firms/invite", headers=hdr(owner_tok),
                   json={"firm_id": pytest.firm_id, "email": invitee_email, "name": "Invitee A", "role": "associate"}, timeout=15)
        assert r.status_code == 200, r.text
        inv = r.json()
        assert "token" in inv and "invite_id" in inv
        token = inv["token"]

        # Register the 2nd user
        reg = s.post(f"{API}/auth/register", json={
            "email": invitee_email, "password": "Test@123", "name": "Invitee A",
            "role": "advocate", "phone": "9000000202",
        }, timeout=15).json()
        invitee_tok = reg["token"]

        # Accept invite
        r2 = s.post(f"{API}/firms/accept-invite", headers=hdr(invitee_tok), json={"token": token}, timeout=15)
        assert r2.status_code == 200, r2.text
        assert r2.json().get("firm_id") == pytest.firm_id

        # Verify invitee role
        me = s.get(f"{API}/auth/me", headers=hdr(invitee_tok), timeout=15).json()
        assert me.get("firm_id") == pytest.firm_id
        assert me.get("firm_role") == "associate"
        assert me.get("role") == "law_firm"

        # Firm /me now has 2 members
        b = s.get(f"{API}/firms/me", headers=hdr(owner_tok), timeout=15).json()
        assert len(b["members"]) == 2

    def test_firm_orders_endpoint(self, s):
        owner_tok = pytest.firm_owner_token
        r = s.get(f"{API}/firms/{pytest.firm_id}/orders", headers=hdr(owner_tok), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        # Foreign firm_id forbidden
        r2 = s.get(f"{API}/firms/firm_nonexistent/orders", headers=hdr(owner_tok), timeout=15)
        assert r2.status_code == 403


# ---------- P1 Delivery Partner ----------
class TestDeliveryP1:
    def test_delivery_integrations(self, s):
        r = s.get(f"{API}/delivery/integrations", timeout=15)
        assert r.status_code == 200
        b = r.json()
        assert b.get("dunzo_enabled") is False
        assert b.get("borzo_enabled") is False
        assert b.get("own_network") is True

    def test_delivery_full_flow(self, s, advocate_token, vendor_token):
        # Register a delivery partner
        dp_email = f"TEST_dp_{uuid.uuid4().hex[:8]}@test.com"
        reg = s.post(f"{API}/auth/register", json={
            "email": dp_email, "password": "Test@123", "name": "Delivery Bro",
            "role": "delivery_partner", "phone": "9000000301",
        }, timeout=15)
        assert reg.status_code == 200, reg.text
        dp_tok = reg.json()["token"]

        # Queue accessible
        rq = s.get(f"{API}/delivery/queue", headers=hdr(dp_tok), timeout=15)
        assert rq.status_code == 200

        # Create an order + pay (razorpay simulated) + mark ready by vendor
        ro = s.post(f"{API}/orders", headers=hdr(advocate_token), json=ORDER_PAYLOAD, timeout=15)
        assert ro.status_code == 200, ro.text
        order_id = ro.json()["order_id"]

        rzp = s.post(f"{API}/payments/razorpay/create-order", headers=hdr(advocate_token),
                     json={"order_id": order_id}, timeout=15).json()
        s.post(f"{API}/payments/razorpay/verify", headers=hdr(advocate_token),
               json={"razorpay_order_id": rzp["razorpay_order_id"]}, timeout=15)

        # Vendor advances to 'ready'
        for st in ("accepted", "processing", "ready"):
            r = s.post(f"{API}/orders/{order_id}/status", headers=hdr(vendor_token),
                       json={"status": st, "note": f"TEST {st}"}, timeout=15)
            assert r.status_code == 200, r.text

        # Delivery accept
        ra = s.post(f"{API}/delivery/{order_id}/accept", headers=hdr(dp_tok), json={}, timeout=15)
        assert ra.status_code == 200, ra.text
        det = s.get(f"{API}/orders/{order_id}", headers=hdr(advocate_token), timeout=15).json()
        assert det.get("status") == "out_for_delivery"
        assert det.get("delivery_partner_id") is not None

        # Location update
        rl = s.post(f"{API}/delivery/{order_id}/location", headers=hdr(dp_tok),
                    json={"lat": 28.6692, "lng": 77.2265, "note": "near gate"}, timeout=15)
        assert rl.status_code == 200

        # Wrong OTP -> 400
        rw = s.post(f"{API}/delivery/{order_id}/complete", headers=hdr(dp_tok), json={"otp": "000000"}, timeout=15)
        assert rw.status_code == 400

        # Correct OTP -> 200, status delivered
        rc = s.post(f"{API}/delivery/{order_id}/complete", headers=hdr(dp_tok), json={"otp": "123456"}, timeout=15)
        assert rc.status_code == 200, rc.text
        det2 = s.get(f"{API}/orders/{order_id}", headers=hdr(advocate_token), timeout=15).json()
        assert det2.get("status") == "delivered"

    def test_delivery_queue_forbidden_for_non_dp(self, s, advocate_token):
        r = s.get(f"{API}/delivery/queue", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 403


# ---------- P1 Serviceability enforcement on Order ----------
class TestServiceabilityP1:
    def test_order_non_delhi_court_rejected(self, s, advocate_token):
        bad = dict(ORDER_PAYLOAD)
        bad["state_id"] = "state_ka"
        bad["court_id"] = "court_ka_hc"
        r = s.post(f"{API}/orders", headers=hdr(advocate_token), json=bad, timeout=15)
        assert r.status_code == 400, f"expected 400 for non-serviceable court, got {r.status_code} {r.text}"
        assert "serviceable" in r.text.lower()

    def test_order_delhi_court_succeeds(self, s, advocate_token):
        r = s.post(f"{API}/orders", headers=hdr(advocate_token), json=ORDER_PAYLOAD, timeout=15)
        assert r.status_code == 200, r.text


# ---------- P1 Document Intelligence ----------
class TestDocIntelP1:
    def test_doc_intel_analyze_returns_valid_report(self, s, advocate_token):
        # Upload a tiny file first
        files = {"file": ("TEST_docint.png", io.BytesIO(b"\x89PNG\r\n\x1a\nTEST_DOCINT"), "image/png")}
        headers = {"Authorization": f"Bearer {advocate_token}"}
        up = requests.post(f"{API}/files/upload", headers=headers, files=files, timeout=60)
        assert up.status_code == 200, up.text
        file_id = up.json()["file_id"]

        r = s.post(f"{API}/doc-intel/analyze", headers=hdr(advocate_token),
                   json={"file_ids": [file_id], "target_court": "court_tishazari", "case_type": "Civil Suit"},
                   timeout=180)
        # AI may fail; spec says we should return 200 with fallback defaults
        assert r.status_code == 200, r.text
        b = r.json()
        assert "report_id" in b
        report = b.get("report", {})
        # Validate the JSON schema
        assert isinstance(report.get("filing_readiness_score"), int)
        assert 0 <= report["filing_readiness_score"] <= 100
        assert isinstance(report.get("ocr_quality_score"), int)
        assert isinstance(report.get("pagination_score"), int)
        assert isinstance(report.get("missing_documents"), list)
        assert isinstance(report.get("defects"), list)
        assert isinstance(report.get("recommended_services"), list)
        assert isinstance(report.get("summary"), str)


# ---------- P1 Sponsored Vendor Listings ----------
class TestSponsoredP1:
    def test_sponsored_plan(self, s):
        r = s.get(f"{API}/vendors/sponsored/plan", timeout=15)
        assert r.status_code == 200
        b = r.json()
        assert b.get("price") == 999
        assert b.get("duration_days") == 30
        assert isinstance(b.get("benefits"), list)

    def test_sponsored_activate_and_priority_in_matching(self, s, vendor_token, advocate_token):
        r = s.post(f"{API}/vendors/sponsored/activate", headers=hdr(vendor_token), json={}, timeout=15)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("ok") is True
        assert b.get("amount") == 999
        assert "sponsored_until" in b

        # Vendor /me should reflect sponsored
        v = s.get(f"{API}/vendors/me", headers=hdr(vendor_token), timeout=15).json()
        assert v.get("sponsored") is True

        # Place a new order and ensure it gets matched to the sponsored vendor
        ro = s.post(f"{API}/orders", headers=hdr(advocate_token), json=ORDER_PAYLOAD, timeout=15)
        assert ro.status_code == 200, ro.text
        order = ro.json()
        assert order.get("vendor_id") is not None
        # In demo data, the Sharma vendor at Tis Hazari is the activated vendor
        assert "Sharma" in (order.get("vendor_name") or "")


# ============================================================================
# ITERATION 3: OCR / Reconciliation / WhatsApp Template Approval
# ============================================================================

def _make_text_pdf_bytes(text="This is page 1 of a CourtBazaar test PDF.\nIN THE COURT OF TIS HAZARI, DELHI\nCivil Suit No. TEST/2026"):
    """Generate a small text-layer PDF using reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in text.split("\n"):
        c.drawString(72, y, line)
        y -= 20
    c.drawString(72, 60, "Page 1")
    c.showPage()
    c.drawString(72, 800, "Continuation page with more body text.")
    c.drawString(72, 60, "Page 2")
    c.showPage()
    c.save()
    return buf.getvalue()


def _make_text_png_bytes(text="HELLO COURTBAZAAR\nTesseract OCR test"):
    """Generate a small PNG with rendered text for OCR."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (600, 200), color="white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
    y = 30
    for line in text.split("\n"):
        d.text((30, y), line, fill="black", font=font)
        y += 50
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _upload_file(token, filename, data, content_type):
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": (filename, io.BytesIO(data), content_type)}
    r = requests.post(f"{API}/files/upload", headers=headers, files=files, timeout=90)
    assert r.status_code == 200, r.text
    return r.json()["file_id"]


# ---------- Doc Intel Real OCR ----------
class TestDocIntelRealOCR:
    def test_analyze_pdf_and_png_with_ocr(self, s, advocate_token):
        pdf_id = _upload_file(advocate_token, "TEST_text.pdf", _make_text_pdf_bytes(), "application/pdf")
        png_id = _upload_file(advocate_token, "TEST_text.png", _make_text_png_bytes(), "image/png")

        r = s.post(
            f"{API}/doc-intel/analyze",
            headers=hdr(advocate_token),
            json={"file_ids": [pdf_id, png_id], "target_court": "court_tishazari", "case_type": "Civil Suit"},
            timeout=180,
        )
        assert r.status_code == 200, r.text
        b = r.json()
        # Extracted block
        ex = b.get("extracted") or {}
        assert ex.get("total_pages", 0) > 0, f"total_pages should be > 0, got {ex}"
        assert ex.get("text_layer_count", 0) >= 1, f"PDF should have text layer, got {ex}"
        assert ex.get("ocr_used") is True, "PNG should trigger OCR (any_ocr=true)"
        files_arr = ex.get("files") or []
        assert len(files_arr) == 2, f"expected 2 files in extracted.files[], got {len(files_arr)}"
        for f in files_arr:
            for key in ("filename", "page_count", "has_text_layer", "ocr_used", "char_count", "page_numbers_detected"):
                assert key in f, f"missing {key} in per-file metadata: {f}"

        # Report block (fallback OK)
        report = b.get("report") or {}
        for key in ("filing_readiness_score", "ocr_quality_score", "pagination_score"):
            assert key in report, f"missing {key} in report"
            assert isinstance(report[key], int)
        assert "summary" in report and isinstance(report["summary"], str)


# ---------- Admin Reconciliation ----------
class TestAdminReconciliation:
    def test_seed_one_paid_stripe_and_one_paid_razorpay(self, s, advocate_token):
        """Ensure at least one stripe + one razorpay txn exist for the report."""
        # Stripe checkout (creates a payment_transactions row, status 'pending')
        ro = s.post(f"{API}/orders", headers=hdr(advocate_token), json=ORDER_PAYLOAD, timeout=15)
        assert ro.status_code == 200
        oid = ro.json()["order_id"]
        chk = s.post(f"{API}/payments/checkout", headers=hdr(advocate_token),
                     json={"order_id": oid, "origin_url": "https://example.com"}, timeout=60)
        assert chk.status_code == 200

        # Razorpay simulated paid
        ro2 = s.post(f"{API}/orders", headers=hdr(advocate_token), json=ORDER_PAYLOAD, timeout=15)
        assert ro2.status_code == 200
        oid2 = ro2.json()["order_id"]
        rzp = s.post(f"{API}/payments/razorpay/create-order", headers=hdr(advocate_token),
                     json={"order_id": oid2}, timeout=15).json()
        s.post(f"{API}/payments/razorpay/verify", headers=hdr(advocate_token),
               json={"razorpay_order_id": rzp["razorpay_order_id"]}, timeout=15)
        pytest.recon_paid_order_id = oid2

    def test_reconciliation_list_shape(self, s, admin_token):
        r = s.get(f"{API}/admin/reconciliation", headers=hdr(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        b = r.json()
        assert isinstance(b.get("rows"), list) and len(b["rows"]) >= 1
        assert "totals" in b and "mismatches" in b
        t = b["totals"]
        for gw in ("stripe", "razorpay"):
            assert gw in t
            for k in ("paid", "pending", "failed", "paid_amount"):
                assert k in t[gw]
        assert "grand_total_paid" in t and "transaction_count" in t
        # row shape
        row = b["rows"][0]
        for key in ("gateway", "order_id", "amount", "payment_status", "order_payment_status", "mismatch"):
            assert key in row, f"row missing {key}: {row}"
        assert row["gateway"] in ("stripe", "razorpay")

    def test_reconciliation_filter_by_gateway(self, s, admin_token):
        r = s.get(f"{API}/admin/reconciliation?gateway=razorpay", headers=hdr(admin_token), timeout=30)
        assert r.status_code == 200
        rows = r.json()["rows"]
        assert len(rows) >= 1
        for row in rows:
            assert row["gateway"] == "razorpay", f"gateway filter leaked stripe row: {row}"

    def test_reconciliation_filter_by_status_paid(self, s, admin_token):
        r = s.get(f"{API}/admin/reconciliation?status_filter=paid", headers=hdr(admin_token), timeout=30)
        assert r.status_code == 200
        rows = r.json()["rows"]
        # At least the razorpay-paid we created should be here
        assert len(rows) >= 1
        for row in rows:
            assert row["payment_status"] == "paid", f"status filter leaked non-paid: {row}"

    def test_reconciliation_mismatch_detection(self, s, admin_token, advocate_token):
        # Create order + stripe checkout (txn pending, order pending). Manually pull
        # admin route then force a mismatch by activating the order's payment_status=paid
        # while leaving the txn pending. We use razorpay create (txn pending) then mark
        # order paid by hitting a parallel razorpay verify on a DIFFERENT razorpay_order_id
        # — actually simpler: create a stripe checkout (txn pending), then razorpay-verify
        # the same order so order.payment_status='paid' but stripe txn stays 'pending'.
        ro = s.post(f"{API}/orders", headers=hdr(advocate_token), json=ORDER_PAYLOAD, timeout=15)
        assert ro.status_code == 200
        oid = ro.json()["order_id"]
        # 1) stripe checkout -> creates stripe txn (pending)
        chk = s.post(f"{API}/payments/checkout", headers=hdr(advocate_token),
                     json={"order_id": oid, "origin_url": "https://example.com"}, timeout=60)
        assert chk.status_code == 200
        stripe_sid = chk.json()["session_id"]
        # 2) razorpay simulated paid -> sets order.payment_status='paid'
        rzp = s.post(f"{API}/payments/razorpay/create-order", headers=hdr(advocate_token),
                     json={"order_id": oid}, timeout=15).json()
        s.post(f"{API}/payments/razorpay/verify", headers=hdr(advocate_token),
               json={"razorpay_order_id": rzp["razorpay_order_id"]}, timeout=15)
        # Now stripe txn is still pending but order is paid -> mismatch
        r = s.get(f"{API}/admin/reconciliation", headers=hdr(admin_token), timeout=30)
        assert r.status_code == 200
        body = r.json()
        # find the stripe row for this order
        stripe_row = next((x for x in body["rows"] if x.get("session_id") == stripe_sid), None)
        assert stripe_row is not None, f"stripe row missing for session {stripe_sid}"
        assert stripe_row["mismatch"] is True, f"expected mismatch=True on stripe pending vs order paid: {stripe_row}"
        # Mismatches array must include it
        mm_ids = [m.get("session_id") for m in body["mismatches"]]
        assert stripe_sid in mm_ids, f"mismatches[] missing stripe session: {mm_ids}"

    def test_reconciliation_csv_export(self, s, admin_token):
        r = s.get(f"{API}/admin/reconciliation/export", headers=hdr(admin_token), timeout=30)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/csv" in ct, f"expected text/csv, got {ct}"
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd.lower(), f"expected attachment header, got {cd}"
        body = r.text
        first_line = body.splitlines()[0]
        assert first_line.startswith("session_id,gateway,order_id,"), f"unexpected header: {first_line}"

    def test_reconciliation_forbidden_for_non_admin(self, s, advocate_token):
        r = s.get(f"{API}/admin/reconciliation", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 403
        r2 = s.get(f"{API}/admin/reconciliation/export", headers=hdr(advocate_token), timeout=15)
        assert r2.status_code == 403


# ---------- WhatsApp Templates Approval Workflow ----------
class TestWhatsAppTemplates:
    def test_seed_defaults_on_first_get(self, s, admin_token):
        r = s.get(f"{API}/admin/whatsapp-templates", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200
        tmpls = r.json()
        names = {t["name"] for t in tmpls}
        # Must contain the 4 defaults (may also include any later-created ones)
        for required in ("order_placed_v1", "order_status_v1", "otp_login_v1", "delivery_otp_v1"):
            assert required in names, f"default template {required} missing — got {names}"
        statuses = {t["status"] for t in tmpls if t["name"] in {"order_placed_v1", "order_status_v1", "otp_login_v1", "delivery_otp_v1"}}
        assert statuses & {"approved", "pending", "draft"}, f"expected mixed statuses, got {statuses}"

    def test_create_submit_approve_flow(self, s, admin_token):
        payload = {
            "name": f"TEST_tmpl_{uuid.uuid4().hex[:6]}",
            "category": "transactional",
            "language": "en",
            "body": "Hello {{1}}, your TEST message.",
            "variables": ["name"],
            "description": "TEST template",
        }
        r = s.post(f"{API}/admin/whatsapp-templates", headers=hdr(admin_token), json=payload, timeout=15)
        assert r.status_code == 200, r.text
        t = r.json()
        assert t["status"] == "draft"
        assert "template_id" in t
        assert isinstance(t.get("history"), list) and len(t["history"]) >= 1
        assert t["history"][0]["action"] == "created"
        tid = t["template_id"]

        # Submit (draft -> pending)
        r2 = s.post(f"{API}/admin/whatsapp-templates/{tid}/submit", headers=hdr(admin_token), timeout=15)
        assert r2.status_code == 200, r2.text
        sb = r2.json()
        assert sb["status"] == "pending"
        # mock mode: twilio_sid None since no Twilio keys
        assert sb.get("twilio_sid") is None

        # Submit again should fail with 400 (already pending)
        r2b = s.post(f"{API}/admin/whatsapp-templates/{tid}/submit", headers=hdr(admin_token), timeout=15)
        assert r2b.status_code == 400

        # Approve
        r3 = s.post(f"{API}/admin/whatsapp-templates/{tid}/approve", headers=hdr(admin_token), timeout=15)
        assert r3.status_code == 200
        assert r3.json()["status"] == "approved"

        # Verify history has 'approved'
        lst = s.get(f"{API}/admin/whatsapp-templates", headers=hdr(admin_token), timeout=15).json()
        found = next((x for x in lst if x["template_id"] == tid), None)
        assert found and found["status"] == "approved"
        actions = [h.get("action") for h in found.get("history", [])]
        assert "approved" in actions, f"history missing approved: {actions}"

    def test_reject_flow(self, s, admin_token):
        # Create + submit
        payload = {"name": f"TEST_rej_{uuid.uuid4().hex[:6]}", "category": "marketing", "language": "en", "body": "Promo {{1}}", "variables": ["x"]}
        t = s.post(f"{API}/admin/whatsapp-templates", headers=hdr(admin_token), json=payload, timeout=15).json()
        tid = t["template_id"]
        s.post(f"{API}/admin/whatsapp-templates/{tid}/submit", headers=hdr(admin_token), timeout=15)
        # Reject
        r = s.post(f"{API}/admin/whatsapp-templates/{tid}/reject", headers=hdr(admin_token),
                   json={"reason": "Body too promotional"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "rejected"
        # Verify rejection_reason persisted
        lst = s.get(f"{API}/admin/whatsapp-templates", headers=hdr(admin_token), timeout=15).json()
        found = next((x for x in lst if x["template_id"] == tid), None)
        assert found and found.get("rejection_reason") == "Body too promotional"

    def test_filter_by_status_approved(self, s, admin_token):
        r = s.get(f"{API}/admin/whatsapp-templates?status_filter=approved", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200
        tmpls = r.json()
        assert len(tmpls) >= 1
        for t in tmpls:
            assert t["status"] == "approved", f"filter leaked: {t}"

    def test_delete(self, s, admin_token):
        payload = {"name": f"TEST_del_{uuid.uuid4().hex[:6]}", "category": "utility", "language": "en", "body": "X", "variables": []}
        t = s.post(f"{API}/admin/whatsapp-templates", headers=hdr(admin_token), json=payload, timeout=15).json()
        tid = t["template_id"]
        r = s.delete(f"{API}/admin/whatsapp-templates/{tid}", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200
        # confirm gone
        lst = s.get(f"{API}/admin/whatsapp-templates", headers=hdr(admin_token), timeout=15).json()
        assert not any(x["template_id"] == tid for x in lst)

    def test_whatsapp_templates_forbidden_for_non_admin(self, s, advocate_token):
        r = s.get(f"{API}/admin/whatsapp-templates", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 403


# ---------- Regression: core endpoints still healthy ----------
class TestRegressionIter3:
    def test_states_still_36plus(self, s):
        r = s.get(f"{API}/states", timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 36

    def test_services_still_44(self, s):
        r = s.get(f"{API}/services", timeout=15)
        assert r.status_code == 200
        assert len(r.json()) == 44

    def test_logins_all_three(self, s):
        for email, pwd, role in [
            (ADV_EMAIL, ADV_PASS, "advocate"),
            (VENDOR_EMAIL, VENDOR_PASS, "vendor"),
            (ADMIN_EMAIL, ADMIN_PASS, "admin"),
        ]:
            r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=15)
            assert r.status_code == 200, f"login {email}: {r.text}"
            assert r.json()["user"]["role"] == role

    def test_order_create_at_tishazari(self, s, advocate_token):
        r = s.post(f"{API}/orders", headers=hdr(advocate_token), json=ORDER_PAYLOAD, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["court_id"] == "court_tishazari"

