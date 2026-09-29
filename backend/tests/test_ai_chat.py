"""Instant Legal Help — conversation layer (ai_chat.py) and LLM abstraction
(llm_service.py). Same rationale as test_counsel_matching_foundation.py:
these modules have no dependency on pytest-asyncio (not a project
dependency), so each test wraps its body in asyncio.run() and talks to
Motor directly against the real dev database, using throwaway
conversation_ids cleaned up in a finally block.

The actual LLM provider is never called here — every test either exercises
pure logic (llm_service's error classification / is_configured) or
monkeypatches llm_service.generate_response so ai_chat.py's orchestration
is tested in isolation from any real network call or API key.
"""
import asyncio
import os
import sys
import uuid

import httpx
import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_chat  # noqa: E402
import llm_service  # noqa: E402


@pytest.mark.parametrize("query", [
    "What are the SLA or turnaround times mentioned in the SOP?",
    "What is the refund process mentioned in the SOP?",
    "What does the DIAC Rules say about fees and costs?",
    "What does the DIAC Rules say about the appointment of arbitrators?",
    "What does the DIAC Rules say about confidentiality?",
    "What are the procedures for arbitration under the DIAC Rules?",
])
def test_attached_document_questions_route_to_rag(query):
    assert ai_chat._needs_product_rag(query) is True


@pytest.mark.parametrize("query", [
    "What is the SLA for Printing Service?",
    "What is the SLA for E-Filing Service?",
    "What are the responsibilities of an E-Filing Partner?",
    "What are the responsibilities of a Proxy Counsel?",
    "What documents are required for KYC?",
    "What is the turnaround time for vendor acceptance?",
    "What are vendor acceptance requirements?",
    "How are complaints handled?",
    "How does emergency escalation work?",
    "How are documents handled?",
    "How long are documents retained?",
    "How does partner onboarding work?",
    "How are disputes resolved?",
    "How is the order assigned?",
    "What does the printing vendor do?",
    "What does the E-Filing Partner do?",
    "What does the delivery partner do?",
])
def test_sop_topics_are_routed_to_sop_rag_before_live_tools(query):
    assert llm_service.is_sop_knowledge_question(query) is True
    assert ai_chat._needs_product_rag(query) is True
    assert llm_service._select_knowledge_source(query) == "STANDARD OPERATING PROCEDURE (SOP).docx"
    # None means the live-tool router deliberately leaves this request for RAG.
    assert asyncio.run(ai_chat._route_tool_call(None, query, {}, None)) is None


def test_explicitly_named_document_takes_precedence_over_sop_topic():
    # Unified-router source priority: a document the user names explicitly
    # is the one searched, even when the topic is also an SOP topic. If the
    # DIAC Rules don't cover it, the grounded "not in the knowledge base"
    # fallback applies — the SOP is never silently substituted.
    query = "What are the responsibilities of a Proxy Counsel under the DIAC rules?"
    assert ai_chat._needs_product_rag(query) is True
    assert ai_chat.route_message(query)["source"] == "DIAC Rules conclusive_UsingOCR.pdf"
    assert llm_service._select_knowledge_source(query) == "DIAC Rules conclusive_UsingOCR.pdf"


@pytest.mark.parametrize("query,expected_tool", [
    ("Which services are currently available?", "get_services"),
    ("Which proxy counsels are currently available?", "search_proxy_counsels"),
])
def test_current_availability_questions_remain_live_tool_requests(monkeypatch, query, expected_tool):
    import counsel_matching
    import court_bazaar_tools

    calls = []

    async def get_services(db):
        calls.append(("get_services", {}))
        return {"status": "success", "tool": "get_services", "data": []}

    async def search_proxy_counsels(db, **kwargs):
        calls.append(("search_proxy_counsels", kwargs))
        return {"status": "success", "tool": "search_proxy_counsels", "data": []}

    async def no_lookup(*_args, **_kwargs):
        return None

    monkeypatch.setattr(court_bazaar_tools, "get_services", get_services)
    monkeypatch.setattr(court_bazaar_tools, "search_proxy_counsels", search_proxy_counsels)
    monkeypatch.setattr(counsel_matching, "check_public_list_rate_limit", lambda _ip: None)
    monkeypatch.setattr(ai_chat, "_extract_state_id", no_lookup)
    monkeypatch.setattr(ai_chat, "_extract_district", no_lookup)
    monkeypatch.setattr(ai_chat, "_resolve_court_id", no_lookup)

    assert llm_service.is_sop_knowledge_question(query) is False
    assert ai_chat._needs_product_rag(query) is False
    result = asyncio.run(ai_chat._route_tool_call(None, query, {}, "127.0.0.1"))
    assert result["tool"] == expected_tool
    assert len(calls) == 1


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


async def _db_with_indexes():
    db = _db()
    await ai_chat.ensure_indexes(db)
    return db


async def _cleanup(db, conversation_ids=()):
    if conversation_ids:
        await db.ai_conversations.delete_many({"conversation_id": {"$in": list(conversation_ids)}})
        await db.ai_chat_messages.delete_many({"conversation_id": {"$in": list(conversation_ids)}})


def _mock_ok(text="Here's some general information."):
    async def fake(messages, **kwargs):
        fake.last_messages = messages
        fake.last_kwargs = kwargs
        return {"ok": True, "text": text}
    fake.last_messages = None
    fake.last_kwargs = None
    return fake


def _mock_fail(error_code, detail="raw internal detail with sk-secret-abc123"):
    async def fake(messages, **kwargs):
        return {"ok": False, "error_code": error_code, "detail": detail}
    return fake


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT content — response length/structure/safety rules
#
# The prompt's actual effect on a live model's prose is inherently
# non-deterministic and depends on a real provider call, so it isn't
# something a unit test can assert on reliably (or without hitting a real,
# billed API). What IS deterministic and worth locking down here: that the
# specific instructions we're relying on are actually present in the prompt
# text, so a future edit can't silently drop one. The corresponding live
# behavior (short 2-5 line answers, no forced Short-answer/Key-points/
# Next-step structure, longer detail only on explicit request, jurisdiction
# follow-up questions, refusing a fabricated citation, multi-turn
# continuity) was verified by hand against the real configured Groq
# provider — see the task report, not this file, for those transcripts.
#
# UX-polish pass (post-3C-B): the prompt was rewritten to fix over-long,
# rigidly-structured answers — these tests were rewritten to match, since
# the OLD assertions (checking for "Short answer"/"Key points" substrings)
# would have kept passing even now, because the new prompt still mentions
# those phrases, just as examples of what NOT to do — a substring check
# alone can't tell prescribed from forbidden, so the new tests check the
# actual prohibition language instead.
# ---------------------------------------------------------------------------

def test_system_prompt_sets_default_length_targets():
    assert "2-5 short lines" in ai_chat.SYSTEM_PROMPT
    assert "1-3 lines" in ai_chat.SYSTEM_PROMPT


def test_system_prompt_forbids_forced_structure_and_markdown():
    assert "Do NOT force every answer into labeled sections" in ai_chat.SYSTEM_PROMPT
    assert "Do NOT default to a numbered list" in ai_chat.SYSTEM_PROMPT
    assert "PLAIN TEXT ONLY" in ai_chat.SYSTEM_PROMPT
    assert "**bold**" in ai_chat.SYSTEM_PROMPT  # cited as a forbidden example, not prescribed


def test_system_prompt_forbids_backslash_escaping_and_html_entities():
    # Response-cleanup fix: models sometimes backslash-escape Markdown
    # punctuation ("\-", "1\.") even when told not to use Markdown at all,
    # and html.unescape() never touches that — it isn't an HTML entity. The
    # prompt now explicitly forbids the escaping itself, not just Markdown.
    assert "\\-" in ai_chat.SYSTEM_PROMPT  # the literal two characters backslash + hyphen
    assert "&#x20;" in ai_chat.SYSTEM_PROMPT
    assert "escap" in ai_chat.SYSTEM_PROMPT.lower()


def test_system_prompt_allows_more_detail_on_explicit_request():
    assert "explicitly asks for more" in ai_chat.SYSTEM_PROMPT
    assert "explain in detail" in ai_chat.SYSTEM_PROMPT
    assert "tell me more" in ai_chat.SYSTEM_PROMPT


def test_system_prompt_asks_for_jurisdiction_before_generic_explanation():
    assert "jurisdiction" in ai_chat.SYSTEM_PROMPT
    assert "FIRST" in ai_chat.SYSTEM_PROMPT


def test_system_prompt_answers_harmless_general_questions():
    # Product decision (unified router): harmless general questions get a
    # normal useful answer — the old fixed "I'm designed for legal and
    # CourtBazaar-related help" refusal is gone. Harmful requests are still
    # declined, and a general answer is never presented as a CourtBazaar fact.
    assert "I'm designed for legal and CourtBazaar-related help" not in ai_chat.SYSTEM_PROMPT
    assert "never refuse a question merely because it isn't about law or CourtBazaar" in ai_chat.SYSTEM_PROMPT
    assert "Decline only requests that are harmful" in ai_chat.SYSTEM_PROMPT
    assert "Never present a general-knowledge answer as a CourtBazaar fact" in ai_chat.SYSTEM_PROMPT


def test_system_prompt_still_forbids_fabrication_and_boilerplate_disclaimers():
    # Brevity must never be allowed to relax the no-fabrication rules already
    # established in earlier phases — this re-asserts they weren't
    # accidentally weakened or removed while tightening for length/structure.
    assert "Never fabricate" in ai_chat.SYSTEM_PROMPT
    assert "worse than a longer honest one" in ai_chat.SYSTEM_PROMPT
    assert "I don't have enough verified information" in ai_chat.SYSTEM_PROMPT
    # The disclaimer itself must still exist (not a lawyer)...
    assert "not a lawyer" in ai_chat.SYSTEM_PROMPT.lower()
    # ...but no longer as a repeated boilerplate block on every single turn.
    assert "boilerplate" in ai_chat.SYSTEM_PROMPT.lower()


# ---------------------------------------------------------------------------
# ai_chat.handle_chat_message
# ---------------------------------------------------------------------------

def test_new_conversation_created_when_none_given(monkeypatch):
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "generate_response", _mock_ok("Hello there."))

    async def body():
        db = await _db_with_indexes()
        conv_ids = []
        try:
            result = await ai_chat.handle_chat_message(db, None, "What is a vakalatnama?", None)
            conv_ids.append(result["conversation_id"])
            assert result["conversation_id"].startswith("conv_")
            assert result["reply"] == "Hello there."
            assert result["degraded"] is False

            convo = await db.ai_conversations.find_one({"conversation_id": result["conversation_id"]}, {"_id": 0})
            assert convo is not None
            assert convo["user_id"] is None

            msgs = await db.ai_chat_messages.find(
                {"conversation_id": result["conversation_id"]}, {"_id": 0},
            ).sort("created_at", 1).to_list(10)
            assert [m["role"] for m in msgs] == ["user", "assistant"]
            assert msgs[0]["content"] == "What is a vakalatnama?"
            assert msgs[1]["content"] == "Hello there."
        finally:
            await _cleanup(db, conv_ids)
    asyncio.run(body())


def test_chat_reply_keeps_citation_in_metadata_only(monkeypatch):
    async def fake_generate(messages, **kwargs):
        return {
            "ok": True,
            "text": "The Rules require confidentiality.\n\nSource: DIAC Rules conclusive_UsingOCR.pdf\nSources: DIAC Rules conclusive_UsingOCR.pdf",
            "sources": ["DIAC Rules conclusive_UsingOCR.pdf"],
        }

    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "generate_response", fake_generate)

    async def body():
        db = await _db_with_indexes()
        conv_ids = []
        try:
            result = await ai_chat.handle_chat_message(
                db, None, "What does the DIAC Rules say about confidentiality?", None,
            )
            conv_ids.append(result["conversation_id"])
            assert result["reply"] == "The Rules require confidentiality."
            assert result["sources"] == ["DIAC Rules conclusive_UsingOCR.pdf"]
            assert "Source:" not in result["reply"]
            assert "Sources:" not in result["reply"]
        finally:
            await _cleanup(db, conv_ids)
    asyncio.run(body())


def test_multi_turn_conversation_accumulates_history(monkeypatch):
    mock = _mock_ok("First reply.")
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "generate_response", mock)

    async def body():
        db = await _db_with_indexes()
        conv_ids = []
        try:
            first = await ai_chat.handle_chat_message(db, None, "First question", None)
            conv_id = first["conversation_id"]
            conv_ids.append(conv_id)

            second_mock = _mock_ok("Second reply.")
            monkeypatch.setattr(llm_service, "generate_response", second_mock)
            second = await ai_chat.handle_chat_message(db, conv_id, "Second question", None)
            assert second["conversation_id"] == conv_id

            sent = second_mock.last_messages
            assert sent[0] == {"role": "system", "content": ai_chat.SYSTEM_PROMPT}
            contents = [m["content"] for m in sent]
            assert "First question" in contents
            assert "First reply." in contents
            assert "Second question" in contents
        finally:
            await _cleanup(db, conv_ids)
    asyncio.run(body())


def test_history_window_caps_messages_sent_to_llm(monkeypatch):
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(ai_chat, "HISTORY_WINDOW", 4)

    async def body():
        db = await _db_with_indexes()
        conv_ids = []
        try:
            convo = await ai_chat._get_or_create_conversation(db, None, None)
            conv_id = convo["conversation_id"]
            conv_ids.append(conv_id)
            for i in range(10):
                await ai_chat._append_message(db, conv_id, "user" if i % 2 == 0 else "assistant", f"turn {i}")

            capture = _mock_ok("latest reply")
            monkeypatch.setattr(llm_service, "generate_response", capture)
            await ai_chat.handle_chat_message(db, conv_id, "final question", None)

            # HISTORY_WINDOW total conversation turns (3 prior + the
            # just-sent "final question" itself = 4 = HISTORY_WINDOW); the
            # rest are system messages (the prompt plus this turn's route note).
            turns = [m for m in capture.last_messages if m["role"] != "system"]
            assert len(turns) == 4
            assert capture.last_messages[0]["content"] == ai_chat.SYSTEM_PROMPT
            assert capture.last_messages[-1] == {"role": "user", "content": "final question"}
        finally:
            await _cleanup(db, conv_ids)
    asyncio.run(body())


def test_conversation_ownership_blocks_a_different_user(monkeypatch):
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "generate_response", _mock_ok())

    async def body():
        db = await _db_with_indexes()
        conv_ids = []
        try:
            user_a = {"user_id": f"test_user_a_{uuid.uuid4().hex[:8]}"}
            user_b = {"user_id": f"test_user_b_{uuid.uuid4().hex[:8]}"}
            started = await ai_chat.handle_chat_message(db, None, "hello", user_a)
            conv_id = started["conversation_id"]
            conv_ids.append(conv_id)

            with pytest.raises(HTTPException) as exc:
                await ai_chat.handle_chat_message(db, conv_id, "hi from someone else", user_b)
            assert exc.value.status_code == 403

            with pytest.raises(HTTPException) as exc_anon:
                await ai_chat.handle_chat_message(db, conv_id, "hi anonymously", None)
            assert exc_anon.value.status_code == 403
        finally:
            await _cleanup(db, conv_ids)
    asyncio.run(body())


def test_anonymous_conversation_has_no_ownership_wall(monkeypatch):
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "generate_response", _mock_ok())

    async def body():
        db = await _db_with_indexes()
        conv_ids = []
        try:
            started = await ai_chat.handle_chat_message(db, None, "hello", None)
            conv_id = started["conversation_id"]
            conv_ids.append(conv_id)
            # No exception continuing anonymously, and no exception if a
            # logged-in user later happens to reuse the same id.
            again = await ai_chat.handle_chat_message(db, conv_id, "still here", None)
            assert again["conversation_id"] == conv_id
        finally:
            await _cleanup(db, conv_ids)
    asyncio.run(body())


def test_empty_message_is_rejected():
    async def body():
        db = await _db_with_indexes()
        with pytest.raises(HTTPException) as exc:
            await ai_chat.handle_chat_message(db, None, "    ", None)
        assert exc.value.status_code == 400
    asyncio.run(body())


def test_overlong_message_is_rejected():
    async def body():
        db = await _db_with_indexes()
        with pytest.raises(HTTPException) as exc:
            await ai_chat.handle_chat_message(db, None, "x" * (ai_chat.MAX_MESSAGE_LENGTH + 1), None)
        assert exc.value.status_code == 400
    asyncio.run(body())


def test_not_configured_returns_503_and_writes_nothing(monkeypatch):
    monkeypatch.setattr(llm_service, "is_configured", lambda: False)

    async def body():
        db = await _db_with_indexes()
        before = await db.ai_conversations.count_documents({})
        with pytest.raises(HTTPException) as exc:
            await ai_chat.handle_chat_message(db, None, "anything", None)
        assert exc.value.status_code == 503
        after = await db.ai_conversations.count_documents({})
        assert after == before  # fails fast, before any conversation is created
    asyncio.run(body())


def test_provider_error_degrades_to_safe_fallback_never_leaks_detail(monkeypatch):
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(
        llm_service, "generate_response",
        _mock_fail(llm_service.ERR_PROVIDER_ERROR, detail="sk-should-never-leak-12345"),
    )

    async def body():
        db = await _db_with_indexes()
        conv_ids = []
        try:
            # Greetings are answered directly without a provider call, so use
            # a grounded product question to exercise the provider fallback.
            result = await ai_chat.handle_chat_message(db, None, "What is Proxy Counsel?", None)
            conv_ids.append(result["conversation_id"])
            assert result["degraded"] is True
            assert "sk-should-never-leak" not in result["reply"]
            assert result["reply"] == ai_chat._FALLBACK_TEXT[llm_service.ERR_PROVIDER_ERROR]

            # The safe fallback — not the raw provider detail — is what got
            # persisted as the assistant's turn too.
            msgs = await db.ai_chat_messages.find(
                {"conversation_id": result["conversation_id"], "role": "assistant"}, {"_id": 0},
            ).to_list(10)
            assert all("sk-should-never-leak" not in m["content"] for m in msgs)
        finally:
            await _cleanup(db, conv_ids)
    asyncio.run(body())


def test_llm_reporting_not_configured_mid_call_still_returns_503(monkeypatch):
    """Defense in depth: even if is_configured() said True but the actual
    call comes back with ERR_NOT_CONFIGURED (e.g. a bad key rejected at call
    time), the caller still gets the hard 503, never an in-conversation
    'safe fallback' message pretending the assistant tried to answer — and,
    just as important, the failed turn is never left half-written: no user
    message sitting in the transcript with no reply next to it."""
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "generate_response", _mock_fail(llm_service.ERR_NOT_CONFIGURED))

    async def body():
        db = await _db_with_indexes()
        conv_ids = []
        try:
            convo = await ai_chat._get_or_create_conversation(db, None, None)
            conv_id = convo["conversation_id"]
            conv_ids.append(conv_id)

            # A greeting is answered deterministically without a provider
            # call, so use a legal question that actually reaches the LLM.
            with pytest.raises(HTTPException) as exc:
                await ai_chat.handle_chat_message(db, conv_id, "What is anticipatory bail?", None)
            assert exc.value.status_code == 503

            count = await db.ai_chat_messages.count_documents({"conversation_id": conv_id})
            assert count == 0
        finally:
            await _cleanup(db, conv_ids)
    asyncio.run(body())


def test_get_conversation_history_empty_for_unknown_id():
    async def body():
        db = await _db_with_indexes()
        history = await ai_chat.get_conversation_history(db, f"conv_{uuid.uuid4().hex[:12]}", None)
        assert history == []
    asyncio.run(body())


def test_get_conversation_history_ownership_enforced(monkeypatch):
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "generate_response", _mock_ok())

    async def body():
        db = await _db_with_indexes()
        conv_ids = []
        try:
            owner = {"user_id": f"test_owner_{uuid.uuid4().hex[:8]}"}
            started = await ai_chat.handle_chat_message(db, None, "hello", owner)
            conv_id = started["conversation_id"]
            conv_ids.append(conv_id)

            own_history = await ai_chat.get_conversation_history(db, conv_id, owner)
            assert len(own_history) == 2

            with pytest.raises(HTTPException) as exc:
                await ai_chat.get_conversation_history(db, conv_id, {"user_id": "someone_else"})
            assert exc.value.status_code == 403
        finally:
            await _cleanup(db, conv_ids)
    asyncio.run(body())


# ---------------------------------------------------------------------------
# llm_service — pure logic, no DB, no network
# ---------------------------------------------------------------------------

def test_is_configured_requires_both_model_and_key(monkeypatch):
    monkeypatch.setattr(llm_service, "AI_PROVIDER", "openai")
    monkeypatch.setattr(llm_service, "AI_MODEL", None)
    monkeypatch.setattr(llm_service, "OPENAI_API_KEY", "sk-test")
    assert llm_service.is_configured() is False

    monkeypatch.setattr(llm_service, "AI_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(llm_service, "OPENAI_API_KEY", None)
    assert llm_service.is_configured() is False

    monkeypatch.setattr(llm_service, "OPENAI_API_KEY", "sk-test")
    assert llm_service.is_configured() is True


def test_is_configured_false_for_unsupported_provider(monkeypatch):
    monkeypatch.setattr(llm_service, "AI_PROVIDER", "some_future_provider")
    monkeypatch.setattr(llm_service, "AI_MODEL", "whatever")
    monkeypatch.setattr(llm_service, "OPENAI_API_KEY", "sk-test")
    assert llm_service.is_configured() is False


def test_is_configured_accepts_groq_with_groq_key(monkeypatch):
    monkeypatch.setattr(llm_service, "AI_PROVIDER", "groq")
    monkeypatch.setattr(llm_service, "AI_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setattr(llm_service, "GROQ_API_KEY", "gsk-test")
    assert llm_service.is_configured() is True

def test_get_client_uses_groq_sdk_for_groq_provider(monkeypatch):
    monkeypatch.setattr(llm_service, "AI_PROVIDER", "groq")
    monkeypatch.setattr(llm_service, "GROQ_API_KEY", "gsk-test")
    client = llm_service._get_client()
    assert "api.groq.com" in str(client.base_url)
    assert client.api_key == "gsk-test"


def test_get_client_uses_default_base_url_when_provider_is_openai(monkeypatch):
    monkeypatch.setattr(llm_service, "AI_PROVIDER", "openai")
    monkeypatch.setattr(llm_service, "OPENAI_API_KEY", "sk-test")
    client = llm_service._get_client()
    assert "groq" not in str(client.base_url)
    assert client.api_key == "sk-test"


def test_generate_response_short_circuits_when_not_configured(monkeypatch):
    monkeypatch.setattr(llm_service, "is_configured", lambda: False)

    async def body():
        result = await llm_service.generate_response([{"role": "user", "content": "hi"}])
        assert result["ok"] is False
        assert result["error_code"] == llm_service.ERR_NOT_CONFIGURED
    asyncio.run(body())


def test_file_search_uses_configured_model_and_returns_document_source(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(llm_service, "AI_PROVIDER", "openai")
    monkeypatch.setattr(llm_service, "AI_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(llm_service, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(llm_service, "OPENAI_VECTOR_STORE_ID", "vs-test")

    class Search:
        async def search(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(data=[SimpleNamespace(
                filename="DIAC Rules conclusive_UsingOCR.pdf",
                file_id="file-diac",
                attributes={"source_id": "diac_rules", "title": "DIAC Rules conclusive_UsingOCR.pdf"},
                score=0.91,
                # Evidence must actually support the answer below — Phase 3
                # validates generated answers against the retrieved text.
                content=[SimpleNamespace(text="Court rules excerpt. Ordering: choose a service, upload documents, "
                                              "then review the order.")],
            )])

    search = Search()
    monkeypatch.setattr(llm_service, "_get_retrieval_client", lambda: SimpleNamespace(
        vector_stores=SimpleNamespace(search=search.search),
    ))

    class Responses:
        async def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                output_text="Choose a service, upload documents, then review the order.",
                output=[],
            )

    responses = Responses()
    monkeypatch.setattr(llm_service, "_get_client", lambda: SimpleNamespace(responses=responses))

    async def body():
        result = await llm_service.generate_response([
            {"role": "system", "content": "Follow application rules."},
            {"role": "user", "content": "How does ordering work?"},
        ], use_file_search=True)
        assert result["ok"] is True
        assert result["sources"] == ["DIAC Rules conclusive_UsingOCR.pdf"]
        assert responses.kwargs["model"] == "gpt-4o-mini"
        assert responses.kwargs["instructions"] == "Follow application rules."
        assert search.kwargs["vector_store_id"] == "vs-test"
        assert search.kwargs["query"] == "How does ordering work?"
        assert "Court rules excerpt" in str(responses.kwargs["input"])
    asyncio.run(body())


def test_file_search_without_a_cited_result_returns_no_context(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(llm_service, "OPENAI_VECTOR_STORE_ID", "vs-test")

    class Search:
        async def search(self, **kwargs):
            return SimpleNamespace(data=[])

    monkeypatch.setattr(llm_service, "_get_retrieval_client", lambda: SimpleNamespace(
        vector_stores=SimpleNamespace(search=Search().search),
    ))

    async def body():
        result = await llm_service.generate_response([{"role": "user", "content": "policy?"}], use_file_search=True)
        assert result["ok"] is False
        assert result["error_code"] == llm_service.ERR_NO_CONTEXT
    asyncio.run(body())


def test_groq_generates_answer_with_openai_vector_store_context(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(llm_service, "AI_PROVIDER", "groq")
    monkeypatch.setattr(llm_service, "AI_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setattr(llm_service, "GROQ_API_KEY", "gsk-test")
    monkeypatch.setattr(llm_service, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(llm_service, "OPENAI_VECTOR_STORE_ID", "vs-test")

    class Search:
        async def search(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(data=[SimpleNamespace(
                filename="STANDARD OPERATING PROCEDURE (SOP).docx",
                file_id="file-sop",
                attributes={"source_id": "court_bazaar_sop", "title": "STANDARD OPERATING PROCEDURE (SOP).docx"},
                score=0.88,
                content=[SimpleNamespace(text="Approved SOP excerpt: the refund process starts after the "
                                              "cancellation is approved.")],
            )])

    class Completions:
        async def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content="The refund process starts after the cancellation is approved."))])

    search = Search()
    completions = Completions()
    monkeypatch.setattr(llm_service, "_get_retrieval_client", lambda: SimpleNamespace(
        vector_stores=SimpleNamespace(search=search.search),
    ))
    monkeypatch.setattr(llm_service, "_get_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
    ))

    async def body():
        result = await llm_service.generate_response([
            {"role": "system", "content": "Use approved sources only."},
            {"role": "user", "content": "What is the refund process mentioned in the SOP?"},
        ], use_file_search=True)
        assert result == {
            "ok": True, "text": "The refund process starts after the cancellation is approved.",
            "sources": ["STANDARD OPERATING PROCEDURE (SOP).docx"],
        }
        assert search.kwargs["vector_store_id"] == "vs-test"
        assert search.kwargs["filters"] == {
            "type": "eq", "key": "source_id", "value": "court_bazaar_sop",
        }
        assert completions.kwargs["model"] == "openai/gpt-oss-120b"
        assert "Approved SOP excerpt" in str(completions.kwargs["messages"])
    asyncio.run(body())


def test_missing_vector_store_is_rag_unavailable_not_provider_unavailable(monkeypatch):
    monkeypatch.setattr(llm_service, "AI_PROVIDER", "groq")
    monkeypatch.setattr(llm_service, "AI_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setattr(llm_service, "GROQ_API_KEY", "gsk-test")
    monkeypatch.setattr(llm_service, "OPENAI_API_KEY", None)
    monkeypatch.setattr(llm_service, "OPENAI_VECTOR_STORE_ID", None)

    async def body():
        result = await llm_service.generate_response(
            [{"role": "user", "content": "What is CourtBazaar?"}], use_file_search=True,
        )
        assert result["ok"] is False
        assert result["error_code"] == llm_service.ERR_RAG_UNAVAILABLE
        assert result["stage"] == "rag"
    asyncio.run(body())


def test_classify_provider_error_maps_known_openai_exceptions():
    from openai import RateLimitError, AuthenticationError, APITimeoutError

    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(429, request=request)
    assert llm_service._classify_provider_error(
        RateLimitError("rate limited", response=response, body=None)
    ) == llm_service.ERR_RATE_LIMITED

    auth_response = httpx.Response(401, request=request)
    assert llm_service._classify_provider_error(
        AuthenticationError("bad key", response=auth_response, body=None)
    ) == llm_service.ERR_PROVIDER_ERROR

    assert llm_service._classify_provider_error(APITimeoutError(request=request)) == llm_service.ERR_TIMEOUT


def test_classify_provider_error_unknown_exception_is_unexpected():
    assert llm_service._classify_provider_error(ValueError("something else entirely")) == llm_service.ERR_UNEXPECTED
