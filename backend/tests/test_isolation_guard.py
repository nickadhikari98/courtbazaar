"""Guards for conftest.py's test isolation — if any of these fails, backend
tests could reach real accounts, real email/SMS or real payment gateways."""
import os
import socket
import sys

import pytest

# The conftest.py pytest already loaded (importing it again would re-run the
# setup with a second database name and a second socket patch).
conftest = next(m for m in list(sys.modules.values())
                if getattr(m, "__file__", "") and m.__file__.replace("\\", "/").endswith("backend/tests/conftest.py"))


def test_database_is_throwaway():
    import server
    assert os.environ["DB_NAME"] == conftest.TEST_DB_NAME
    assert server.db.name == conftest.TEST_DB_NAME
    assert server.db.name.startswith("courtbazaar_pytest_")


def test_messaging_and_payments_are_disabled():
    import notifications
    import razorpay_svc
    assert not notifications.is_email_enabled()
    assert not notifications.is_sms_enabled()
    assert not notifications.is_whatsapp_enabled()
    assert not razorpay_svc.is_enabled()
    result = notifications.send_email("someone@example.com", "subject", "<p>body</p>")
    assert result["status"] == "mocked"


def test_outbound_network_is_blocked_but_loopback_is_not():
    before = len(conftest.BLOCKED_CONNECTIONS)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(conftest.BlockedNetworkError):
            s.connect(("93.184.216.34", 443))  # any public address
    assert len(conftest.BLOCKED_CONNECTIONS) == before + 1
    conftest.BLOCKED_CONNECTIONS.pop()  # this block was deliberate; keep the session summary about real attempts
    assert conftest._is_loopback(("127.0.0.1", 27017)) and conftest._is_loopback(("::1", 27017))
    assert conftest._is_loopback(("localhost", 27017))
