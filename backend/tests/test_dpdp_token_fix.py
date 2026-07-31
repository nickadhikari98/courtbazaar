"""Iteration 5 bug fix re-verification.
Bug: After DPDP deletion, old JWT tokens still validated against /api/auth/me.
Fix: get_current_user now checks user.get('deleted') and raises 401.
"""
import os
import time
import requests
from pathlib import Path

def _load_backend_url():
    url = os.environ.get('REACT_APP_BACKEND_URL')
    if url:
        return url.rstrip('/')
    env_path = Path('/app/frontend/.env')
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith('REACT_APP_BACKEND_URL='):
                return line.split('=', 1)[1].strip().rstrip('/')
    raise RuntimeError('REACT_APP_BACKEND_URL not set')

BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


def test_deletion_invalidates_jwt_token():
    # 1) Register throwaway user
    email = f"TEST_dpdp_iter5_{int(time.time())}@cbtest.in"
    reg = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "TestPass@123", "name": "DPDP Iter5", "role": "advocate"
    }, timeout=30)
    assert reg.status_code == 200, f"register failed: {reg.status_code} {reg.text}"
    token1 = reg.json()["token"]
    h1 = {"Authorization": f"Bearer {token1}"}

    # 2) /auth/me with token1 -> 200
    me1 = requests.get(f"{API}/auth/me", headers=h1, timeout=30)
    assert me1.status_code == 200, f"pre-deletion /auth/me expected 200, got {me1.status_code} {me1.text}"
    assert me1.json().get("email") == email

    # 3) Request deletion as throwaway user
    dr = requests.post(f"{API}/dpdp/request-deletion", headers=h1, json={"reason": "iter5 retest"}, timeout=30)
    assert dr.status_code == 200, f"request-deletion failed: {dr.status_code} {dr.text}"
    request_id = dr.json().get("request_id") or dr.json().get("id")
    assert request_id, f"no request_id in response: {dr.json()}"

    # 4) Admin executes deletion
    admin_token = _login("admin@courtbazaar.com", "Admin@123")
    ah = {"Authorization": f"Bearer {admin_token}"}
    ex = requests.post(f"{API}/admin/dpdp/requests/{request_id}/execute", headers=ah, timeout=30)
    assert ex.status_code == 200, f"admin execute failed: {ex.status_code} {ex.text}"

    # 5) /auth/me with token1 -> MUST be 401 now
    me2 = requests.get(f"{API}/auth/me", headers=h1, timeout=30)
    assert me2.status_code == 401, (
        f"BUG STILL PRESENT: expected 401 after deletion, got {me2.status_code} {me2.text}"
    )
    body = me2.text.lower()
    assert "delete" in body or "unauthorized" in body or "account" in body, f"unexpected body: {me2.text}"


def test_regression_normal_user_auth_still_works():
    token = _login("advocate@demo.in", "Advocate@123")
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert r.status_code == 200, f"advocate /auth/me failed: {r.status_code} {r.text}"
    assert r.json().get("email") == "advocate@demo.in"
    assert not r.json().get("deleted")


def test_regression_admin_audit_log_works():
    token = _login("admin@courtbazaar.com", "Admin@123")
    r = requests.get(f"{API}/admin/audit-log", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert r.status_code == 200, f"admin audit-log failed: {r.status_code} {r.text}"
    data = r.json()
    # accept either list or dict with entries
    assert isinstance(data, (list, dict)), f"unexpected shape: {type(data)}"
