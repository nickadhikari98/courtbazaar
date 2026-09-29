"""Test isolation for the backend suite — loaded by pytest before any test
module, so it runs before `server` (and its load_dotenv) is imported.

Backend tests used to run against DB_NAME from backend/.env — the shared dev
database with real accounts — and a paid broadcast hearing created by a test
starts counsel matching, which emailed real counsels through Brevo. This file
makes that impossible:

1. Throwaway database. DB_NAME is forced to a fresh courtbazaar_pytest_<id>
   (server.py's load_dotenv never overrides a variable that is already set),
   so real accounts don't exist from a test's point of view. It is dropped
   when the session ends.
2. Messaging and payments disabled. Email/SMS/WhatsApp provider keys are
   blanked, so notifications.py takes its own built-in mock path ("[MOCK
   Email ...]" log, status "mocked"); Razorpay keys are blanked, so
   razorpay_svc runs in its simulated mode. No production code is patched.
3. Network guard. Any socket connection to a non-loopback address raises
   BlockedNetworkError, so no test can reach Brevo, Razorpay, SMS/WhatsApp
   providers or anything else outside this machine, whatever keys it sets.
4. Live-server tests (test_courtbazaar_api.py, test_dpdp_token_fix.py) drive
   a separately running backend, whose database and email settings this file
   can't control, so they are not collected unless CB_LIVE_BACKEND_TESTS=1 —
   only set that against a backend itself started on a test DB with email
   disabled.
"""
import ipaddress
import os
import socket
import uuid

TEST_DB_NAME = f"courtbazaar_pytest_{uuid.uuid4().hex[:10]}"
os.environ["DB_NAME"] = TEST_DB_NAME

_MESSAGING_KEYS = (
    "BREVO_API_KEY", "RESEND_API_KEY", "SENDGRID_API_KEY", "EMAIL_FROM_ADDRESS", "ADMIN_ALERT_EMAILS",
    "FAST2SMS_API_KEY", "MSG91_AUTH_KEY",
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER", "TWILIO_WHATSAPP_FROM",
    # Razorpay: simulated mode by default. Tests used to get it only by
    # import-order accident (razorpay_svc imported before server loaded
    # .env); tests that exercise live mode set fake keys on razorpay_svc
    # themselves (see test_razorpay_live_mode.py).
    "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET",
)
for _key in _MESSAGING_KEYS:
    os.environ[_key] = ""  # set (not deleted), so load_dotenv can't fill it back in

LIVE_BACKEND_TESTS = ["test_courtbazaar_api.py", "test_dpdp_token_fix.py"]
collect_ignore = [] if os.environ.get("CB_LIVE_BACKEND_TESTS") == "1" else LIVE_BACKEND_TESTS


class BlockedNetworkError(ConnectionError):
    pass


BLOCKED_CONNECTIONS = []


def _is_loopback(address) -> bool:
    host = address[0] if isinstance(address, tuple) else address
    if not isinstance(host, str):
        return True  # AF_UNIX paths etc. never leave the machine
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False  # an unresolved hostname — treat as external


_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _guarded_connect(self, address):
    if not _is_loopback(address):
        BLOCKED_CONNECTIONS.append(address)
        raise BlockedNetworkError(f"Backend tests may not open network connections outside this machine: {address!r}")
    return _real_connect(self, address)


def _guarded_connect_ex(self, address):
    if not _is_loopback(address):
        BLOCKED_CONNECTIONS.append(address)
        raise BlockedNetworkError(f"Backend tests may not open network connections outside this machine: {address!r}")
    return _real_connect_ex(self, address)


socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex


def pytest_sessionstart(session):
    import notifications
    assert not notifications.is_email_enabled(), "email must be disabled in tests"
    assert not notifications.is_sms_enabled(), "SMS must be disabled in tests"
    assert not notifications.is_whatsapp_enabled(), "WhatsApp must be disabled in tests"
    import razorpay_svc
    assert not razorpay_svc.is_enabled(), "Razorpay must run simulated in tests"
    _seed_reference_data()


def _seed_reference_data():
    """Give the empty throwaway DB what a freshly started server has: the
    app's own startup seeding (indexes + states/courts/services from the
    code-defined datasets), nothing copied from any real database. Runs
    through its own motor client — server.client (ensure_db_ready's ping)
    and server.db are both swapped — so the app's own client isn't bound to
    this short-lived event loop."""
    import asyncio
    import unittest.mock
    from motor.motor_asyncio import AsyncIOMotorClient
    import server

    async def seed():
        client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        try:
            with unittest.mock.patch.object(server, "client", client), \
                    unittest.mock.patch.object(server, "db", client[TEST_DB_NAME]):
                await server.seed_initial_data()
        finally:
            client.close()
    asyncio.run(seed())


def pytest_sessionfinish(session, exitstatus):
    import sys
    server = sys.modules.get("server")
    if server is not None:
        # Anything that imported server must have picked up the throwaway DB.
        assert server.db.name == TEST_DB_NAME, f"server.db is {server.db.name!r}, expected {TEST_DB_NAME!r}"
    from pymongo import MongoClient
    client = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    try:
        client.drop_database(TEST_DB_NAME)
    finally:
        client.close()


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    terminalreporter.write_sep("-", "backend test isolation")
    terminalreporter.write_line(f"database: {TEST_DB_NAME} (dropped); email/SMS/WhatsApp: mocked; Razorpay: simulated")
    if collect_ignore:
        terminalreporter.write_line(f"not collected (live backend, set CB_LIVE_BACKEND_TESTS=1): {', '.join(collect_ignore)}")
    terminalreporter.write_line(f"blocked outbound connections: {len(BLOCKED_CONNECTIONS)}"
                                + (f" -> {sorted({str(a[0]) for a in BLOCKED_CONNECTIONS})}" if BLOCKED_CONNECTIONS else ""))
