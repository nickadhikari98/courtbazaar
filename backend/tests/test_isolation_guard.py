"""Guards for conftest.py's test isolation — if any of these fails, backend
tests could reach real accounts, real email/SMS or real payment gateways."""
import asyncio
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


@pytest.mark.parametrize("loop_factory", [
    asyncio.SelectorEventLoop,
    # The Windows default; it connects via ConnectEx, bypassing socket.connect.
    pytest.param(getattr(asyncio, "ProactorEventLoop", None),
                 marks=pytest.mark.skipif(sys.platform != "win32", reason="Windows-only event loop")),
])
@pytest.mark.parametrize("host", ["93.184.216.34", "api.openai.com"])
def test_asyncio_outbound_is_blocked(loop_factory, host):
    before = len(conftest.BLOCKED_CONNECTIONS)
    loop = loop_factory()
    try:
        with pytest.raises(OSError) as exc:  # BlockedNetworkError, or a DNS failure before any connect
            loop.run_until_complete(asyncio.wait_for(asyncio.open_connection(host, 443), 10))
    finally:
        loop.close()
    if host[0].isdigit():  # no DNS involved: only the guard can have refused it
        assert isinstance(exc.value, conftest.BlockedNetworkError)
        assert len(conftest.BLOCKED_CONNECTIONS) > before
    del conftest.BLOCKED_CONNECTIONS[before:]  # deliberate; keep the session summary about real attempts


def test_asyncio_loopback_still_works():
    async def roundtrip():
        server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        _, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.close()
        server.close()
        await server.wait_closed()
    asyncio.run(roundtrip())


def test_service_credentials_are_blank_and_config_kept():
    for key in ("OPENAI_API_KEY", "OPENAI_VECTOR_STORE_ID", "GROQ_API_KEY", "EMERGENT_LLM_KEY",
                "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_BUCKET", "S3_ENDPOINT_URL",
                "CAPTCHA_SECRET_KEY", "N8N_WEBHOOK_URL", "COURTBAZAAR_API_BASE"):
        assert os.environ.get(key) == "", key
    assert "AI_MAX_OUTPUT_TOKENS" not in conftest._MESSAGING_KEYS + conftest._SERVICE_KEYS


def test_mongo_is_local():
    import server
    assert os.environ["MONGO_URL"] == conftest.TEST_MONGO_URL == "mongodb://127.0.0.1:27017"
    assert server.mongo_url == conftest.TEST_MONGO_URL
