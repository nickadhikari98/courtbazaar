"""Storage error handling — closes the exact gap that caused a real
production incident: botocore.exceptions.SSLError (and other transport-level
failures) is a BotoCoreError, not a ClientError, so storage.py's original
`except ClientError` never caught it. That let a broken-TLS-trust-store
environment's SSLError propagate as a genuinely unhandled exception, which
FastAPI's default handling turns into a 500 that skips CORSMiddleware's
header attachment — the browser then (correctly, if misleadingly) reports
that as "blocked by CORS policy".

Uses botocore.exceptions.EndpointConnectionError (a real BotoCoreError
subclass, easy to construct without needing actual network access) as the
stand-in for the SSLError actually seen in production — same hierarchy,
same fix, deterministic without depending on this machine's TLS trust store
or live connectivity to R2.
"""
import os
import sys

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import storage  # noqa: E402


class _FakeClient:
    def __init__(self, exc):
        self._exc = exc

    def put_object(self, **kwargs):
        raise self._exc

    def get_object(self, **kwargs):
        raise self._exc

    def delete_object(self, **kwargs):
        raise self._exc


def test_put_object_converts_botocore_connection_error_to_http_exception(monkeypatch):
    monkeypatch.setattr(storage, "_get_client", lambda: _FakeClient(EndpointConnectionError(endpoint_url="https://example.test")))
    with pytest.raises(HTTPException) as exc_info:
        storage.put_object("some/path.png", b"data", "image/png")
    assert exc_info.value.status_code == 500


def test_put_object_still_converts_client_error_too():
    """Regression guard: the original ClientError handling must keep working
    alongside the new BotoCoreError branch, not get replaced by it."""
    import storage as storage_module

    def _raise_client_error(**kwargs):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "PutObject")

    class _Client:
        put_object = staticmethod(_raise_client_error)

    original = storage_module._get_client
    storage_module._get_client = lambda: _Client()
    try:
        with pytest.raises(HTTPException) as exc_info:
            storage.put_object("some/path.png", b"data", "image/png")
        assert exc_info.value.status_code == 500
    finally:
        storage_module._get_client = original


def test_get_object_distinguishes_missing_file_from_connection_failure(monkeypatch):
    # A real "not found" (ClientError) still reports 404.
    class _NotFoundClient:
        def get_object(self, **kwargs):
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")

    monkeypatch.setattr(storage, "_get_client", lambda: _NotFoundClient())
    with pytest.raises(HTTPException) as exc_info:
        storage.get_object("missing/path.png")
    assert exc_info.value.status_code == 404

    # A connection failure must NOT be reported as "file not found" — that
    # would be misleading (the file may well exist; storage was just
    # unreachable).
    monkeypatch.setattr(storage, "_get_client", lambda: _FakeClient(EndpointConnectionError(endpoint_url="https://example.test")))
    with pytest.raises(HTTPException) as exc_info:
        storage.get_object("some/path.png")
    assert exc_info.value.status_code == 500
    assert "not found" not in exc_info.value.detail.lower()


def test_delete_object_returns_false_on_connection_failure_not_raise(monkeypatch):
    monkeypatch.setattr(storage, "_get_client", lambda: _FakeClient(EndpointConnectionError(endpoint_url="https://example.test")))
    assert storage.delete_object("some/path.png") is False
