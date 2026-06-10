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
        assert len(data) == 8, f"expected 8 states, got {len(data)}"

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
        assert len(courts) == 10, f"expected 10 courts in Delhi, got {len(courts)}"
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
