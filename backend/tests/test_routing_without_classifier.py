"""Instant Legal Help — routing is deterministic again (Decisions API classifier removed).

The OpenAI Decisions API source-routing classifier was removed on 2026-10-17
to avoid the extra paid call per question. route_message alone decides the
source: named DIAC/SOP documents and SOP topics go to document RAG, general
legal questions go to web search when AI_WEB_SEARCH_ENABLED (else the plain
general-legal answer). Web search stays independently configurable.
"""
import asyncio
import os
import sys

import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from openai import AsyncOpenAI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_chat  # noqa: E402
import llm_service  # noqa: E402

DEPOSIT_Q = "What happens if a party doesn't pay the arbitration deposit on time?"
SCI = "https://www.sci.gov.in/judgements"


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _ask(message):
    return asyncio.run(ai_chat.handle_chat_message(_db(), None, message, None, client_ip="127.0.0.1"))


def _recording_openai(monkeypatch):
    """A real OpenAI client whose every HTTP request is recorded; /responses
    answers like a web search that cites one official page."""
    paths = []
    text = "Anticipatory bail is bail granted before arrest. ([sci.gov.in](https://www.sci.gov.in/judgements))"
    link = text[text.index("(["):]

    async def handler(request):
        paths.append(request.url.path)
        if request.url.path != "/v1/responses":
            return httpx.Response(404, json={"error": {"message": "unexpected endpoint"}})
        return httpx.Response(200, json={
            "id": "resp_1", "object": "response", "created_at": 0, "model": "gpt-5-mini", "status": "completed",
            "output": [{"type": "message", "id": "msg_1", "role": "assistant", "status": "completed", "content": [{
                "type": "output_text", "text": text, "annotations": [{
                    "type": "url_citation", "start_index": text.index(link), "end_index": len(text),
                    "url": SCI, "title": "Supreme Court of India"}]}]}],
        })

    client = AsyncOpenAI(api_key="test-key", max_retries=0,
                         http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(llm_service, "_get_retrieval_client", lambda: client)
    monkeypatch.setattr(llm_service, "_get_client", lambda: client)
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    return paths


def _fakes(monkeypatch, web=True):
    calls = {"plain": [], "web": []}

    async def fake_generate(messages, use_file_search=False, selected_source=None, on_status=None):
        calls["plain"].append((use_file_search, selected_source))
        return {"ok": True, "text": "Answer.", "sources": []}

    async def fake_web(messages):
        calls["web"].append(messages)
        return {"ok": False, "error_code": llm_service.ERR_TIMEOUT, "stage": "web search"}

    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "web_search_enabled", lambda: web)
    monkeypatch.setattr(llm_service, "generate_response", fake_generate)
    monkeypatch.setattr(llm_service, "generate_web_answer", fake_web)
    return calls


# ---------------------------------------------------------------------------
# No Decisions API call
# ---------------------------------------------------------------------------

def test_the_classifier_code_and_flag_are_gone():
    for name in ("classify_source_route", "decisions_routing_enabled", "AI_DECISIONS_ROUTING_ENABLED",
                 "SOURCE_ROUTE_QUESTION", "ROUTE_CHOICES"):
        assert not hasattr(llm_service, name), name
    assert not hasattr(ai_chat, "_classified_route")


def test_a_web_search_turn_calls_only_the_responses_endpoint(monkeypatch):
    paths = _recording_openai(monkeypatch)
    monkeypatch.setattr(llm_service, "web_search_enabled", lambda: True)
    result = _ask("What is anticipatory bail?")
    # The web search itself, and no classifier. The score-routing search is
    # stubbed in conftest; it is the only other call a real turn makes.
    assert paths == ["/v1/responses"]
    assert not any("decision" in p for p in paths)
    assert [c["url"] for c in result["citations"]] == [SCI]


def test_a_document_turn_makes_no_decisions_call(monkeypatch):
    paths = _recording_openai(monkeypatch)
    calls = _fakes(monkeypatch)
    _ask("What do the DIAC rules say if the claimant does not pay the arbitral fee?")
    assert not any("decision" in p for p in paths)
    assert calls["plain"] == [(True, llm_service.SOURCE_DIAC)]


# ---------------------------------------------------------------------------
# Deterministic routing, as before the classifier
# ---------------------------------------------------------------------------

def test_diac_and_sop_questions_use_document_rag(monkeypatch):
    for question, source in (
        ("What do the DIAC rules say if the claimant does not pay the arbitral fee?", llm_service.SOURCE_DIAC),
        ("What does the SOP say about refunds?", llm_service.SOURCE_SOP),
    ):
        calls = _fakes(monkeypatch)
        _ask(question)
        assert calls["web"] == [], question
        assert calls["plain"] == [(True, source)], question


def test_a_general_legal_question_goes_to_web_search_not_a_document(monkeypatch):
    # Below the score-routing threshold (stubbed in conftest), it stays a general question.
    assert ai_chat.route_message(DEPOSIT_Q)["route"] == ai_chat.ROUTE_GENERAL_LEGAL
    calls = _fakes(monkeypatch)
    _ask(DEPOSIT_Q)
    assert len(calls["web"]) == 1
    assert all(not use_rag for use_rag, _ in calls["plain"])  # the web-failure fallback, never RAG


# ---------------------------------------------------------------------------
# Web search stays independently configurable
# ---------------------------------------------------------------------------

def test_web_search_off_gives_the_plain_general_legal_answer(monkeypatch):
    calls = _fakes(monkeypatch, web=False)
    _ask(DEPOSIT_Q)
    assert calls["web"] == []
    assert calls["plain"] == [(False, None)]


def test_web_search_flag_and_key_decide_web_search_alone(monkeypatch):
    for flag, key, expected in ((True, "sk-test", True), (False, "sk-test", False), (True, None, False)):
        monkeypatch.setattr(llm_service, "AI_WEB_SEARCH_ENABLED", flag)
        monkeypatch.setattr(llm_service, "OPENAI_API_KEY", key)
        assert llm_service.web_search_enabled() is expected
