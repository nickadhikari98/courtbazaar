"""
CourtBazaar Backend API Tests
Covers: health, auth, courts, services, files, orders, payments, AI, subscriptions,
        wallet, vendor flow, admin flow, vendor onboarding, auth security
"""
import io
import os
import time
import uuid
import bcrypt
import pytest
import requests
from pymongo import MongoClient

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


def _otp_db():
    """Direct DB access, test-only: OTP codes are delivered via SMS in real
    usage, so a black-box HTTP test has no other way to read the code the
    server generated in order to exercise the real verify path."""
    return MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "courtbazaar")]


ADV_EMAIL = "advocate@demo.in"
ADV_PASS = "Advocate@123"
VENDOR_EMAIL = "vendor@demo.in"
VENDOR_PASS = "Vendor@123"
ADMIN_EMAIL = "admin@courtbazaar.com"
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
        assert len(data) == 48, f"expected 48 services (iter6: 44 + 4 stenographer), got {len(data)}"

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
        # OTP delivery is real now (SMS provider or console-logged mock) —
        # a black-box HTTP test can't intercept the SMS, so it seeds the
        # known code server-side after /request, the same way a test would
        # stub any other real-world delivery channel. This exercises the
        # actual hash-compare/expiry verify path, not a hardcoded bypass.
        phone = f"9{uuid.uuid4().int % 1000000000:09d}"
        r = s.post(f"{API}/auth/otp/request", json={"phone": phone}, timeout=15)
        assert r.status_code == 200

        test_code = "654321"
        db = _otp_db()
        result = db.otp_codes.update_one(
            {"phone": phone, "used": False},
            {"$set": {"otp_hash": bcrypt.hashpw(test_code.encode(), bcrypt.gensalt()).decode()}},
        )
        assert result.matched_count == 1, "expected /auth/otp/request to have created exactly one otp_codes record"

        r = s.post(f"{API}/auth/otp/verify", json={"phone": phone, "otp": test_code, "name": "OTP Tester", "role": "advocate"}, timeout=15)
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


# ---------- AI ----------
class TestAI:
    def test_ai_chat_stubbed(self, s, advocate_token):
        # Not wired to a real LLM provider yet — expect a clear 503, not a 500.
        sid = f"TEST_chat_{uuid.uuid4().hex[:6]}"
        r = s.post(f"{API}/ai/chat", headers=hdr(advocate_token),
                   json={"session_id": sid, "message": "What documents are needed for filing a civil suit at Tis Hazari court?"},
                   timeout=30)
        assert r.status_code == 503, r.text

    def test_ai_history_empty_for_unknown_session(self, s, advocate_token):
        sid = f"TEST_chat_{uuid.uuid4().hex[:6]}"
        r = s.get(f"{API}/ai/history/{sid}", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 200
        assert r.json() == []

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
        # restore original (1.0 — seeded value)
        s.put(f"{API}/admin/services/svc_bw_photocopy/pricing", headers=hdr(admin_token),
              json={"service_id": "svc_bw_photocopy", "base_price": 1.0}, timeout=15)


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
        # No keys configured -> razorpay disabled, simulated mode on
        assert b.get("razorpay") is False
        assert b.get("razorpay_simulated") is True

    def test_razorpay_create_and_verify_simulated(self, s, advocate_token):
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
    def test_seed_one_paid_razorpay(self, s, advocate_token):
        """Ensure at least one paid razorpay txn exists for the report."""
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
        # Create order + razorpay order (txn pending). There's no HTTP path that marks
        # an order paid without also paying its txn, so — test-only, same rationale as
        # _otp_db() above — flip the order's payment_status directly in the DB, leaving
        # the txn pending, to produce a genuine reconciliation mismatch.
        ro = s.post(f"{API}/orders", headers=hdr(advocate_token), json=ORDER_PAYLOAD, timeout=15)
        assert ro.status_code == 200
        oid = ro.json()["order_id"]
        rzp = s.post(f"{API}/payments/razorpay/create-order", headers=hdr(advocate_token),
                     json={"order_id": oid}, timeout=15).json()
        rzp_order_id = rzp["razorpay_order_id"]
        _otp_db().orders.update_one({"order_id": oid}, {"$set": {"payment_status": "paid"}})
        # Now the razorpay txn is still pending but order is paid -> mismatch
        r = s.get(f"{API}/admin/reconciliation", headers=hdr(admin_token), timeout=30)
        assert r.status_code == 200
        body = r.json()
        row = next((x for x in body["rows"] if x.get("razorpay_order_id") == rzp_order_id), None)
        assert row is not None, f"row missing for razorpay order {rzp_order_id}"
        assert row["mismatch"] is True, f"expected mismatch=True on razorpay pending vs order paid: {row}"
        # Mismatches array must include it
        mm_ids = [m.get("order_id") for m in body["mismatches"]]
        assert oid in mm_ids, f"mismatches[] missing order: {mm_ids}"

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
        # Iter6: now 48 services (44 + 4 new Stenographer Services)
        r = s.get(f"{API}/services", timeout=15)
        assert r.status_code == 200
        assert len(r.json()) == 48

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



# ============================================================================
# ITERATION 4: Bulk Import + DPDP + Audit Log + Vendor Leaderboard / SLA
# ============================================================================
import json as _json


def _register_advocate(s, label):
    """Helper: register a fresh advocate user with unique email."""
    suffix = uuid.uuid4().hex[:8]
    email = f"TEST_{label}_{suffix}@cbtest.in"
    pwd = "TestPass@123"
    r = s.post(f"{API}/auth/register", json={
        "email": email, "password": pwd, "name": f"TEST {label} {suffix}",
        "phone": f"9{uuid.uuid4().int % 1000000000:09d}", "role": "advocate",
    }, timeout=15)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    token = r.json()["token"]
    user_id = r.json()["user"]["user_id"]
    return email, pwd, token, user_id


def _create_firm(s, token, name_suffix=""):
    """Helper: create a firm for the given user (they become owner)."""
    r = s.post(f"{API}/firms", headers=hdr(token), json={
        "name": f"TEST Firm {name_suffix or uuid.uuid4().hex[:6]}",
        "gst": "07AAACT1234A1Z5",
        "address": "Test Address, Delhi",
    }, timeout=15)
    assert r.status_code == 200, f"create firm: {r.status_code} {r.text}"
    return r.json()["firm_id"]


class TestBulkImportIter4:
    """Bulk Order CSV Import for law firms."""

    def test_template_download(self, s, advocate_token):
        r = s.get(f"{API}/firms/bulk-import/template", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", "").lower()
        body = r.text
        first_line = body.splitlines()[0]
        expected_header = "matter_name,service_ids,qty_each,court_id,delivery_option,urgent,delivery_address,notes"
        assert first_line == expected_header, f"unexpected header: {first_line}"
        # 1 header + at least 2 example rows
        assert len(body.splitlines()) >= 3

    def test_bulk_import_requires_firm(self, s):
        # Fresh advocate without firm
        _, _, tok, _ = _register_advocate(s, "nofirm")
        csv_body = "matter_name,service_ids,qty_each,court_id,delivery_option,urgent,delivery_address,notes\n"
        csv_body += "TEST Matter,svc_bw_photocopy,10,court_tishazari,chamber,false,Addr,note\n"
        r = requests.post(
            f"{API}/firms/bulk-import",
            headers={"Authorization": f"Bearer {tok}"},
            files={"file": ("test.csv", csv_body, "text/csv")},
            timeout=20,
        )
        assert r.status_code == 400, r.text
        assert "law-firm" in r.text.lower() or "firm" in r.text.lower()

    def test_bulk_import_happy_path(self, s):
        # Fresh advocate -> create firm -> bulk import
        _, _, tok, _ = _register_advocate(s, "happy")
        firm_id = _create_firm(s, tok, "happy")
        csv_body = "matter_name,service_ids,qty_each,court_id,delivery_option,urgent,delivery_address,notes\n"
        csv_body += "TEST Matter A,svc_bw_photocopy;svc_spiral_binding,100;1,court_tishazari,chamber,false,Chamber X,test\n"
        csv_body += "TEST Matter B,svc_bw_photocopy;svc_spiral_binding,50;2,court_tishazari,chamber,false,Chamber Y,test2\n"
        r = requests.post(
            f"{API}/firms/bulk-import",
            headers={"Authorization": f"Bearer {tok}"},
            files={"file": ("bulk.csv", csv_body, "text/csv")},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["success"]) == 2, f"expected 2 success, got {body}"
        assert body["errors"] == []
        assert body["total_amount"] > 0
        # Verify orders persisted with firm_id + matter_name + source
        order_id = body["success"][0]["order_id"]
        ro = s.get(f"{API}/orders/{order_id}", headers=hdr(tok), timeout=15)
        assert ro.status_code == 200, ro.text
        order = ro.json()
        assert order["firm_id"] == firm_id
        assert order["matter_name"] == "TEST Matter A"
        assert order["source"] == "bulk_csv"
        assert order["vendor_id"] is not None, "vendor should be auto-matched at tishazari"

    def test_bulk_import_partial_errors_non_serviceable_court(self, s):
        _, _, tok, _ = _register_advocate(s, "partial")
        _create_firm(s, tok, "partial")
        csv_body = "matter_name,service_ids,qty_each,court_id,delivery_option,urgent,delivery_address,notes\n"
        csv_body += "TEST Good,svc_bw_photocopy,10,court_tishazari,chamber,false,Addr,note\n"
        csv_body += "TEST Bad,svc_bw_photocopy,10,court_ka_hc,chamber,false,Addr,note\n"
        r = requests.post(
            f"{API}/firms/bulk-import",
            headers={"Authorization": f"Bearer {tok}"},
            files={"file": ("partial.csv", csv_body, "text/csv")},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["success"]) == 1
        assert len(body["errors"]) == 1
        assert "not yet serviceable" in body["errors"][0]["error"].lower(), body["errors"]

    def test_bulk_import_unknown_service_handled(self, s):
        _, _, tok, _ = _register_advocate(s, "badsvc")
        _create_firm(s, tok, "badsvc")
        csv_body = "matter_name,service_ids,qty_each,court_id,delivery_option,urgent,delivery_address,notes\n"
        csv_body += "TEST Unknown,svc_does_not_exist,1,court_tishazari,chamber,false,Addr,note\n"
        r = requests.post(
            f"{API}/firms/bulk-import",
            headers={"Authorization": f"Bearer {tok}"},
            files={"file": ("bad.csv", csv_body, "text/csv")},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Graceful handling: should either appear in success (with 0/low total) or errors (without 500)
        assert (len(body["success"]) + len(body["errors"])) == 1

    def test_bulk_import_associate_forbidden(self, s):
        # owner creates firm and invites a new user as associate
        _, _, owner_tok, _ = _register_advocate(s, "owner")
        firm_id = _create_firm(s, owner_tok, "assoc")
        # Register associate user (fresh)
        assoc_email, assoc_pwd, assoc_tok, _ = _register_advocate(s, "assoc")
        # Owner invites
        ri = s.post(f"{API}/firms/invite", headers=hdr(owner_tok), json={
            "firm_id": firm_id, "email": assoc_email, "name": "Associate Test", "role": "associate",
        }, timeout=15)
        assert ri.status_code == 200, ri.text
        token = ri.json()["token"]
        # Associate accepts
        ra = s.post(f"{API}/firms/accept-invite", headers=hdr(assoc_tok), json={"token": token}, timeout=15)
        assert ra.status_code == 200, ra.text
        # Now associate tries bulk import -> 403
        csv_body = "matter_name,service_ids,qty_each,court_id,delivery_option,urgent,delivery_address,notes\n"
        csv_body += "TEST Matter,svc_bw_photocopy,1,court_tishazari,chamber,false,Addr,note\n"
        r = requests.post(
            f"{API}/firms/bulk-import",
            headers={"Authorization": f"Bearer {assoc_tok}"},
            files={"file": ("assoc.csv", csv_body, "text/csv")},
            timeout=20,
        )
        assert r.status_code == 403, r.text


class TestAuditLogIter4:
    """Admin audit log + auto-write on auth/order events."""

    def test_admin_audit_log_lists(self, s, admin_token):
        # Trigger admin login first to ensure an auth.login entry exists
        s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
        r = s.get(f"{API}/admin/audit-log", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "entries" in data and "actions" in data
        assert isinstance(data["entries"], list)
        assert isinstance(data["actions"], list)
        # Should have at least one auth.login entry
        assert any(e.get("action") == "auth.login" for e in data["entries"]), "no auth.login entry found"

    def test_admin_audit_log_filter_action(self, s, admin_token):
        r = s.get(f"{API}/admin/audit-log?action=auth.login", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200
        for e in r.json()["entries"]:
            assert e["action"] == "auth.login"

    def test_audit_log_forbidden_non_admin(self, s, advocate_token):
        r = s.get(f"{API}/admin/audit-log", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 403

    def test_audit_log_auto_write_on_order_create(self, s, advocate_token, admin_token):
        # Create a fresh order
        ro = s.post(f"{API}/orders", headers=hdr(advocate_token), json=ORDER_PAYLOAD, timeout=15)
        assert ro.status_code == 200, ro.text
        order_id = ro.json()["order_id"]
        # Allow audit write to flush
        time.sleep(0.5)
        r = s.get(f"{API}/admin/audit-log?action=order.create&limit=200", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200
        entries = r.json()["entries"]
        assert any((e.get("details") or {}).get("order_id") == order_id for e in entries), \
            f"no audit entry for order {order_id}"


class TestDPDPIter4:
    """DPDP Act compliance endpoints."""

    def test_my_data_preview_shape(self, s, advocate_token):
        r = s.get(f"{API}/dpdp/my-data", headers=hdr(advocate_token), timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("profile", "orders", "files", "wallet_transactions",
                  "payment_transactions", "ai_messages", "audit_log"):
            assert k in data, f"missing key {k}"
        # password_hash MUST NOT leak
        assert "password_hash" not in (data.get("profile") or {})

    def test_my_data_download_attachment(self, s, advocate_token):
        r = s.get(f"{API}/dpdp/my-data/download", headers=hdr(advocate_token), timeout=20)
        assert r.status_code == 200
        assert "application/json" in r.headers.get("content-type", "").lower()
        assert "attachment" in r.headers.get("content-disposition", "").lower()
        body = _json.loads(r.text)
        assert "profile" in body

    def test_deletion_request_creates_record(self, s, advocate_token):
        r = s.post(f"{API}/dpdp/request-deletion", headers=hdr(advocate_token),
                   json={"reason": "TEST iter4 request"}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("status") == "pending"
        assert body.get("request_id", "").startswith("del_")

    def test_admin_dpdp_list_includes_request(self, s, admin_token):
        r = s.get(f"{API}/admin/dpdp/requests", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200
        reqs = r.json()
        assert isinstance(reqs, list)
        # At least one pending request (from previous test)
        assert any(req.get("status") == "pending" for req in reqs)

    def test_admin_execute_deletion_anonymises_user(self, s, admin_token):
        # Register a throwaway user
        email, pwd, tok, uid = _register_advocate(s, "tobedeleted")
        # User files a deletion request
        r1 = s.post(f"{API}/dpdp/request-deletion", headers=hdr(tok),
                    json={"reason": "TEST throwaway"}, timeout=15)
        assert r1.status_code == 200
        req_id = r1.json()["request_id"]
        # Admin executes
        r2 = s.post(f"{API}/admin/dpdp/requests/{req_id}/execute",
                    headers=hdr(admin_token), timeout=15)
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["ok"] is True
        assert body["status"] == "anonymized"
        assert "orders_retained" in body
        # Old session token no longer works
        r3 = s.get(f"{API}/auth/me", headers=hdr(tok), timeout=15)
        assert r3.status_code == 401, f"deleted user token should be invalid; got {r3.status_code} {r3.text}"


class TestComplianceReportIter4:
    def test_compliance_report_shape(self, s, admin_token):
        r = s.get(f"{API}/admin/compliance-report", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("audit_log_entries", "total_users", "deleted_users",
                  "pending_deletion_requests", "executed_deletions",
                  "top_actions", "dpdp_compliant", "data_retention_policy_days"):
            assert k in body, f"missing {k}"
        assert body["dpdp_compliant"] is True
        assert body["data_retention_policy_days"] == 1825
        assert isinstance(body["top_actions"], list)


class TestVendorLeaderboardIter4:
    def test_leaderboard_admin(self, s, admin_token):
        r = s.get(f"{API}/admin/leaderboard", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list) and len(rows) >= 1
        first = rows[0]
        for k in ("shop_name", "sla_score", "grade", "on_time_rate",
                  "avg_turnaround_hours", "avg_rating", "total_orders",
                  "revenue", "dispute_rate", "completion_rate"):
            assert k in first, f"missing {k}"
        assert first["grade"] in ("A+", "A", "B", "C", "D")
        assert 0 <= first["sla_score"] <= 100
        # Sorted desc by sla_score
        scores = [r_["sla_score"] for r_ in rows]
        assert scores == sorted(scores, reverse=True), f"not sorted desc: {scores}"

    def test_leaderboard_forbidden_for_non_admin(self, s, advocate_token):
        r = s.get(f"{API}/admin/leaderboard", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 403

    def test_vendor_me_sla(self, s, vendor_token):
        r = s.get(f"{API}/vendors/me/sla", headers=hdr(vendor_token), timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "grade" in body and "sla_score" in body
        assert body["grade"] in ("A+", "A", "B", "C", "D")

    def test_vendor_me_sla_forbidden_for_advocate(self, s, advocate_token):
        r = s.get(f"{API}/vendors/me/sla", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 403

    def test_vendor_sla_by_id_admin(self, s, admin_token, vendor_token):
        # Get vendor user_id via /auth/me
        rm = s.get(f"{API}/auth/me", headers=hdr(vendor_token), timeout=15)
        assert rm.status_code == 200
        vendor_user_id = rm.json()["user_id"]
        r = s.get(f"{API}/vendors/{vendor_user_id}/sla", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        assert "grade" in r.json()

    def test_vendor_sla_by_id_other_vendor_forbidden(self, s, vendor_token):
        # Vendor accessing a different vendor_id
        r = s.get(f"{API}/vendors/some_other_vendor_id/sla", headers=hdr(vendor_token), timeout=15)
        assert r.status_code == 403


class TestRegressionIter4:
    """Regression spot-checks for iter4."""

    def test_states_36plus(self, s):
        r = s.get(f"{API}/states", timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 36

    def test_services_44(self, s):
        # Iter6: now 48 services
        r = s.get(f"{API}/services", timeout=15)
        assert r.status_code == 200
        assert len(r.json()) == 48

    def test_admin_analytics_ok(self, s, admin_token):
        r = s.get(f"{API}/admin/analytics", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200

    def test_admin_reconciliation_ok(self, s, admin_token):
        r = s.get(f"{API}/admin/reconciliation", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200


# ============================================================================
# ITERATION 6 — Super Admin Command Center, Vendor Onboarding, Pricing 80/20,
#                Stenographer hourly booking, File page-count, DPDP auto-delete
# ============================================================================
class TestIter6Services:
    """Services: 48 total, stenographer category, unified 20% commission."""

    def test_services_count_48(self, s):
        r = s.get(f"{API}/services", timeout=15)
        assert r.status_code == 200
        assert len(r.json()) == 48

    def test_stenographer_services_seeded(self, s):
        r = s.get(f"{API}/services", params={"category": "Stenographer Services"}, timeout=15)
        assert r.status_code == 200
        steno = r.json()
        assert len(steno) == 4
        ids = sorted([x["service_id"] for x in steno])
        assert ids == sorted([
            "svc_steno_hearing", "svc_steno_deposition",
            "svc_steno_transcription", "svc_steno_dictation",
        ])
        for svc in steno:
            assert svc.get("booking_type") == "hourly", svc
            assert svc.get("min_hours", 0) >= 1
            assert svc.get("platform_commission_pct") == 0.20

    def test_unified_20pct_commission_all_services(self, s):
        r = s.get(f"{API}/services", timeout=15)
        assert r.status_code == 200
        for svc in r.json():
            assert svc.get("platform_commission_pct") == 0.20, \
                f"service {svc['service_id']} commission={svc.get('platform_commission_pct')}"


class TestIter6PricingEngine:
    """80/20 service split, 50/50 delivery, convenience = platform, urgent 80/20."""

    def _quote(self, s, token, services, delivery="chamber", urgent=False, court="court_tishazari"):
        r = s.post(
            f"{API}/orders/quote",
            headers=hdr(token),
            json={
                "services": services,
                "court_id": court,
                "state_id": "state_delhi",
                "delivery_option": delivery,
                "urgent": urgent,
                "file_ids": [],
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text
        return r.json()

    def test_80_20_split_bw_photocopy_100pages_chamber(self, s, advocate_token):
        q = self._quote(s, advocate_token,
                        [{"service_id": "svc_bw_photocopy", "qty": 100}],
                        delivery="chamber", urgent=False)
        sd = q["split_details"]
        # subtotal: 100 * 1 = 100
        assert q["subtotal"] == 100.0
        assert sd["service_subtotal"] == 100.0
        assert sd["vendor_service_share_80pct"] == 80.0
        assert sd["platform_commission_20pct"] == 20.0
        # chamber delivery 79 -> 50/50
        assert q["delivery_fee"] == 79
        assert sd["vendor_delivery_share_50pct"] == 39.5
        assert sd["platform_delivery_share_50pct"] == 39.5
        # convenience = platform revenue
        assert q["convenience_fee"] == 10
        assert sd["convenience_fee_platform"] == 10
        # urgent off
        assert sd["urgent_fee"] == 0
        assert sd["vendor_urgent_share_80pct"] == 0
        assert sd["platform_urgent_share_20pct"] == 0
        # totals: gst 18% on (100+79+0+10)=189 -> 34.02; total 223.02
        assert q["gst"] == 34.02
        assert q["total"] == 223.02
        # vendor_payout = 80 + 39.5 + 0 = 119.5
        assert q["vendor_payout"] == 119.5
        # platform_revenue = 20 + 39.5 + 10 + 0 = 69.5
        assert q["platform_revenue"] == 69.5

    def test_convenience_equals_platform(self, s, advocate_token):
        q = self._quote(s, advocate_token,
                        [{"service_id": "svc_bw_photocopy", "qty": 50}],
                        delivery="chamber", urgent=False)
        assert q["split_details"]["convenience_fee_platform"] == q["convenience_fee"]

    def test_urgent_80_20_split(self, s, advocate_token):
        q = self._quote(s, advocate_token,
                        [{"service_id": "svc_bw_photocopy", "qty": 100}],
                        delivery="pickup", urgent=True)
        # subtotal=100, urgent=25
        assert q["subtotal"] == 100.0
        assert q["urgent_fee"] == 25.0
        sd = q["split_details"]
        assert sd["vendor_urgent_share_80pct"] == 20.0
        assert sd["platform_urgent_share_20pct"] == 5.0


class TestIter6Stenographer:
    """Hourly booking flow + min_hours + serviceability."""

    def test_book_happy_path(self, s, advocate_token):
        r = s.post(
            f"{API}/stenographers/book",
            headers=hdr(advocate_token),
            json={
                "service_id": "svc_steno_hearing",
                "state_id": "state_delhi",
                "court_id": "court_tishazari",
                "date": "2026-03-15",
                "start_time": "10:00",
                "hours": 3,
                "delivery_option": "court",
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["order_id"].startswith("STN")
        assert data["order_type"] == "stenographer_booking"
        assert data["booking"]["date"] == "2026-03-15"
        assert data["booking"]["start_time"] == "10:00"
        assert data["booking"]["hours"] == 3
        # 3 hours * 800 = 2400
        assert data["pricing"]["subtotal"] == 2400.0

    def test_min_hours_validation(self, s, advocate_token):
        r = s.post(
            f"{API}/stenographers/book",
            headers=hdr(advocate_token),
            json={
                "service_id": "svc_steno_hearing",
                "state_id": "state_delhi",
                "court_id": "court_tishazari",
                "date": "2026-03-15",
                "start_time": "10:00",
                "hours": 1,
                "delivery_option": "court",
            },
            timeout=15,
        )
        assert r.status_code == 400
        assert "Minimum" in r.text and "hour" in r.text

    def test_non_serviceable_court_rejected(self, s, advocate_token):
        # Use Bombay HC which has serviceable=False explicitly in seed
        r = s.post(
            f"{API}/stenographers/book",
            headers=hdr(advocate_token),
            json={
                "service_id": "svc_steno_hearing",
                "state_id": "state_mh",
                "court_id": "court_bombay_hc",
                "date": "2026-03-15",
                "start_time": "10:00",
                "hours": 2,
                "delivery_option": "court",
            },
            timeout=15,
        )
        assert r.status_code == 400
        assert "not yet serviceable" in r.text.lower()

    def test_list_stenographers(self, s):
        r = s.get(f"{API}/stenographers", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_stenographers_by_court(self, s):
        r = s.get(f"{API}/stenographers", params={"court_id": "court_tishazari"}, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestIter6VendorCategories:
    def test_vendor_categories_endpoint(self, s):
        r = s.get(f"{API}/vendor-categories", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 8
        ids = sorted([x["id"] for x in data])
        assert ids == sorted([
            "photocopy", "typist", "efiling_agent", "notary",
            "stamp_vendor", "stenographer", "court_runner", "delivery_partner",
        ])
        for c in data:
            assert "name" in c and "icon" in c and "service_categories" in c


class TestIter6VendorOnboarding:
    """Vendor onboarding with optional GST + vendor_category + hourly_rate."""

    def _register(self, s, role="advocate"):
        ts = int(time.time() * 1000)
        email = f"TEST_iter6_{ts}_{uuid.uuid4().hex[:4]}@cbtest.in"
        r = s.post(
            f"{API}/auth/register",
            json={"email": email, "password": "Test@1234", "name": "Iter6 Test", "phone": f"9{ts%1000000000:09d}", "role": role},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        return r.json()["token"]

    def test_onboard_without_gst(self, s):
        tok = self._register(s)
        r = s.post(
            f"{API}/vendors/onboard",
            headers=hdr(tok),
            json={
                "shop_name": "TEST_TypistShop",
                "owner_name": "Test Typist",
                "phone": "9876500001",
                "address": "Tis Hazari, Delhi",
                "court_ids": ["court_tishazari"],
                "service_ids": ["svc_typing_petition"],
                "vendor_category": "typist",
                "has_gst": False,
                "gst": None,
                "bio": "Legal typist with 5y exp",
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["has_gst"] is False
        assert v["vendor_category"] == "typist"
        assert v.get("gst") in (None, "")

    def test_onboard_with_gst(self, s):
        tok = self._register(s)
        r = s.post(
            f"{API}/vendors/onboard",
            headers=hdr(tok),
            json={
                "shop_name": "TEST_GSTShop",
                "owner_name": "Test Owner",
                "phone": "9876500002",
                "address": "Tis Hazari, Delhi",
                "court_ids": ["court_tishazari"],
                "service_ids": ["svc_bw_photocopy"],
                "vendor_category": "photocopy",
                "has_gst": True,
                "gst": "07AAAAA0000A1Z5",
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["has_gst"] is True
        assert v["gst"] == "07AAAAA0000A1Z5"

    def test_onboard_stenographer_with_hourly_rate(self, s):
        tok = self._register(s)
        r = s.post(
            f"{API}/vendors/onboard",
            headers=hdr(tok),
            json={
                "shop_name": "TEST_StenoVendor",
                "owner_name": "Steno Pro",
                "phone": "9876500003",
                "address": "Tis Hazari, Delhi",
                "court_ids": ["court_tishazari"],
                "service_ids": ["svc_steno_hearing", "svc_steno_deposition"],
                "vendor_category": "stenographer",
                "has_gst": False,
                "hourly_rate": 800,
                "bio": "Court stenographer 10y",
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["vendor_category"] == "stenographer"
        assert v["hourly_rate"] == 800


class TestIter6FilePageCount:
    """Auto-detect page count on upload."""

    def _gen_pdf(self, pages: int) -> bytes:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        for i in range(pages):
            c.drawString(72, 720, f"TEST page {i+1}")
            c.showPage()
        c.save()
        return buf.getvalue()

    def _gen_png(self) -> bytes:
        # Minimal 1x1 PNG
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfa\xcf"
            b"\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    def test_pdf_page_count_5(self, s, advocate_token):
        pdf_bytes = self._gen_pdf(5)
        files = {"file": ("TEST_iter6_5p.pdf", pdf_bytes, "application/pdf")}
        # Use requests.post directly to avoid session's Content-Type=json header
        r = requests.post(
            f"{API}/files/upload",
            headers={"Authorization": f"Bearer {advocate_token}"},
            files=files,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["page_count"] == 5
        assert data["original_filename"].endswith(".pdf")

    def test_png_page_count_1(self, s, advocate_token):
        png_bytes = self._gen_png()
        files = {"file": ("TEST_iter6.png", png_bytes, "image/png")}
        r = requests.post(
            f"{API}/files/upload",
            headers={"Authorization": f"Bearer {advocate_token}"},
            files=files,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json()["page_count"] == 1


class TestIter6AutoDeleteOnCompletion:
    """DPDP: files purged when order status -> completed."""

    def _upload_pdf(self, s, token, pages=2):
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        for i in range(pages):
            c.drawString(72, 720, f"AUTO-DEL TEST page {i+1}")
            c.showPage()
        c.save()
        files = {"file": ("TEST_autodel.pdf", buf.getvalue(), "application/pdf")}
        r = requests.post(
            f"{API}/files/upload",
            headers={"Authorization": f"Bearer {token}"},
            files=files, timeout=30,
        )
        assert r.status_code == 200
        return r.json()["file_id"]

    def test_files_purged_on_completed(self, s, advocate_token, admin_token):
        # 1) Upload file
        fid = self._upload_pdf(s, advocate_token)

        # 2) Create order with file_ids
        r = s.post(
            f"{API}/orders",
            headers=hdr(advocate_token),
            json={
                "services": [{"service_id": "svc_bw_photocopy", "qty": 10}],
                "court_id": "court_tishazari",
                "state_id": "state_delhi",
                "delivery_option": "chamber",
                "urgent": False,
                "file_ids": [fid],
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text
        order = r.json()
        order_id = order["order_id"]
        assert fid in order["file_ids"]

        # 3) Admin transitions to completed (admin can override status)
        r = s.post(
            f"{API}/orders/{order_id}/status",
            headers=hdr(admin_token),
            json={"status": "completed", "note": "test auto-purge"},
            timeout=20,
        )
        assert r.status_code == 200, r.text

        # 4) Verify file is_deleted=true via /api/files/{file_id} (admin) or DPDP my-data
        # Use order detail to check files_purged metadata
        r = s.get(f"{API}/orders/{order_id}", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200
        odata = r.json()
        assert "files_purged" in odata, odata
        assert odata["files_purged"]["deleted"] >= 1

        # Verify file record marked deleted via DPDP /my-data (advocate sees own files)
        r = s.get(f"{API}/dpdp/my-data", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 200
        my = r.json()
        # find our file in user's file list
        my_files = my.get("files", []) or my.get("data", {}).get("files", [])
        found = next((f for f in my_files if f.get("file_id") == fid), None)
        if found is not None:
            assert found.get("is_deleted") is True
            dr = found.get("deleted_reason", "")
            assert "order_completed" in dr and order_id in dr


class TestIter6CommandCenter:
    """Super Admin Command Center."""

    def test_command_center_admin_200(self, s, admin_token):
        r = s.get(f"{API}/admin/command-center", headers=hdr(admin_token), timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # revenue block
        rev = data["revenue"]
        for k in ["platform_total", "platform_commission_20pct",
                  "platform_delivery_share_50pct", "platform_convenience_fee",
                  "platform_urgent_share_20pct", "vendor_payout_total",
                  "gst_collected", "paid_orders"]:
            assert k in rev, f"missing revenue.{k}"
        # orders block
        orders = data["orders"]
        for k in ["last_7_days", "by_status", "total"]:
            assert k in orders, f"missing orders.{k}"
        # vendors block
        vendors = data["vendors"]
        for k in ["total", "approved", "pending_kyc", "sponsored",
                  "with_gst", "without_gst", "by_category"]:
            assert k in vendors, f"missing vendors.{k}"
        # users block
        users = data["users"]
        assert "total" in users and "by_role" in users
        # compliance
        comp = data["compliance"]
        for k in ["audit_entries", "pending_deletions", "files_purged"]:
            assert k in comp, f"missing compliance.{k}"
        # revenue_model fixed config
        rm = data["revenue_model"]
        assert rm["platform_commission_pct"] == 20
        assert rm["delivery_split_vendor_pct"] == 50
        assert rm["convenience_fee_inr"] == 10
        assert rm["gst_pct"] == 18

    def test_command_center_forbidden_non_admin(self, s, advocate_token):
        r = s.get(f"{API}/admin/command-center", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 403


class TestIter6Regression:
    def test_states_36(self, s):
        r = s.get(f"{API}/states", timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 36

    def test_order_at_tishazari_works(self, s, advocate_token):
        r = s.post(
            f"{API}/orders",
            headers=hdr(advocate_token),
            json={
                "services": [{"service_id": "svc_bw_photocopy", "qty": 5}],
                "court_id": "court_tishazari",
                "state_id": "state_delhi",
                "delivery_option": "chamber",
                "urgent": False,
                "file_ids": [],
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text

    def test_admin_reconciliation_ok(self, s, admin_token):
        r = s.get(f"{API}/admin/reconciliation", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200

    def test_admin_leaderboard_ok(self, s, admin_token):
        r = s.get(f"{API}/admin/leaderboard", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200

    def test_admin_audit_log_ok(self, s, admin_token):
        r = s.get(f"{API}/admin/audit-log", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200


# ---------- Counsel Matching Agent roadmap M3: admin KYC + Bar Council verification ----------
class TestPracticeVerificationM3:
    """"proxy_counsel" isn't in ROLES (server.py) — a real proxy_counsel
    account only exists via the Lead->Professional approval pipeline, which
    is out of scope for testing two admin flag-flip endpoints. Both
    endpoints only ever look up proxy_counsel_profiles by user_id, so a
    throwaway advocate's user_id is used as the target and a profile row is
    inserted directly — same direct-DB escape hatch _otp_db() already uses
    for OTP codes."""

    def _make_target_user_and_profile(self, s):
        email = f"TEST_practice_verify_{uuid.uuid4().hex[:8]}@cbtest.in"
        reg = s.post(f"{API}/auth/register", json={
            "email": email, "password": "TestPass@123", "name": "Practice Verify Target", "role": "advocate",
        }, timeout=15)
        assert reg.status_code == 200, f"register failed: {reg.status_code} {reg.text}"
        user_id = reg.json()["user"]["user_id"]
        _otp_db().proxy_counsel_profiles.insert_one({
            "user_id": user_id, "kyc_status": "pending", "bar_council_verified": False,
        })
        return user_id

    def _cleanup(self, user_id):
        db = _otp_db()
        db.proxy_counsel_profiles.delete_many({"user_id": user_id})
        db.users.delete_many({"user_id": user_id})

    def test_approve_kyc_requires_admin(self, s, advocate_token):
        r = s.put(f"{API}/admin/practice/whoever/approve-kyc", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 403

    def test_verify_bar_council_requires_admin(self, s, advocate_token):
        r = s.put(f"{API}/admin/practice/whoever/verify-bar-council", headers=hdr(advocate_token), timeout=15)
        assert r.status_code == 403

    def test_approve_kyc_flips_only_kyc_status(self, s, admin_token):
        user_id = self._make_target_user_and_profile(s)
        try:
            r = s.put(f"{API}/admin/practice/{user_id}/approve-kyc", headers=hdr(admin_token), timeout=15)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["kyc_status"] == "approved"
            assert body["bar_council_verified"] is False  # untouched
        finally:
            self._cleanup(user_id)

    def test_verify_bar_council_flips_only_bar_council_verified(self, s, admin_token):
        user_id = self._make_target_user_and_profile(s)
        try:
            r = s.put(f"{API}/admin/practice/{user_id}/verify-bar-council", headers=hdr(admin_token), timeout=15)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["bar_council_verified"] is True
            assert body["kyc_status"] == "pending"  # untouched
        finally:
            self._cleanup(user_id)

    def test_approve_kyc_idempotent(self, s, admin_token):
        user_id = self._make_target_user_and_profile(s)
        try:
            r1 = s.put(f"{API}/admin/practice/{user_id}/approve-kyc", headers=hdr(admin_token), timeout=15)
            r2 = s.put(f"{API}/admin/practice/{user_id}/approve-kyc", headers=hdr(admin_token), timeout=15)
            assert r1.status_code == 200 and r2.status_code == 200
            assert r2.json()["kyc_status"] == "approved"
        finally:
            self._cleanup(user_id)

    def test_approve_kyc_nonexistent_user_404(self, s, admin_token):
        r = s.put(f"{API}/admin/practice/user_does_not_exist_xyz/approve-kyc", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 404

    def test_verify_bar_council_nonexistent_user_404(self, s, admin_token):
        r = s.put(f"{API}/admin/practice/user_does_not_exist_xyz/verify-bar-council", headers=hdr(admin_token), timeout=15)
        assert r.status_code == 404
