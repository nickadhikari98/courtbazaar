"""Phase 7 — regressions for issues found in production-like QA.

1. The provider client was rebuilt on every call; building one builds an SSL
   context (~1s of synchronous work on the QA host), stalling the event loop
   for every user. It is now built once per event loop.
2. Exception text logged from the chat path could carry credentials (a
   connection string, "password=...") unredacted.
3. The approved knowledge-base documents were untracked but not ignored.
"""
import asyncio
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import llm_service  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def openai_config(monkeypatch):
    monkeypatch.setattr(llm_service, "AI_PROVIDER", "openai")
    monkeypatch.setattr(llm_service, "OPENAI_API_KEY", "sk-test-not-a-real-key-000000")
    llm_service._CLIENT_CACHE.clear()
    yield
    llm_service._CLIENT_CACHE.clear()


def test_provider_client_is_built_once_per_event_loop(openai_config):
    async def two_calls():
        return (llm_service._get_client(), llm_service._get_client(),
                llm_service._get_retrieval_client())

    first = asyncio.run(two_calls())
    assert first[0] is first[1] is first[2]  # one client per loop, shared by generation and retrieval
    second = asyncio.run(two_calls())
    assert second[0] is not first[0]  # never reused on a different event loop


def test_changed_key_gets_a_new_client(openai_config, monkeypatch):
    async def body():
        a = llm_service._get_client()
        monkeypatch.setattr(llm_service, "OPENAI_API_KEY", "sk-test-other-key-111111111")
        return a, llm_service._get_client()

    a, b = asyncio.run(body())
    assert a is not b


def test_client_outside_an_event_loop_is_still_available(openai_config):
    assert llm_service._get_client() is not None


@pytest.mark.parametrize("message,secret", [
    ("mongo exploded at 10.0.0.5 user=admin password=hunter2", "hunter2"),
    ("connect failed mongodb+srv://admin:s3cr3tpw@cluster0.example.net/db", "s3cr3tpw"),
    ("upstream said Bearer abcdefghijklmnopqrstuvwxyz0123", "abcdefghijklmnopqrstuvwxyz0123"),
    ("bad key sk-proj-AbCdEfGhIjKlMnOpQrStUv123456", "AbCdEfGhIjKlMnOpQrStUv123456"),
])
def test_logged_error_detail_never_carries_credentials(message, secret):
    detail = llm_service._safe_error_detail(RuntimeError(message))
    assert secret not in detail and "[REDACTED]" in detail


def test_logged_error_detail_redacts_configured_secret_values(monkeypatch):
    monkeypatch.setenv("SOME_SERVICE_API_KEY", "configured-value-987654")
    assert "configured-value-987654" not in llm_service._safe_error_detail(
        RuntimeError("failed with configured-value-987654"))


def test_harmless_error_detail_is_kept_for_diagnosis():
    assert llm_service._safe_error_detail(RuntimeError("openai generation exceeded 25.0s")) == \
        "openai generation exceeded 25.0s"


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_knowledge_documents_and_env_files_are_git_ignored():
    for path in ("backend/ai_knowledge/DIAC Rules conclusive_UsingOCR.pdf",
                 "backend/ai_knowledge/STANDARD OPERATING PROCEDURE (SOP).docx",
                 "backend/.env", "frontend/.env"):
        result = subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO_ROOT)
        assert result.returncode == 0, f"{path} is not git-ignored"
