"""User-facing wording of Instant Legal Help's fallback, clarification and
casual replies: natural, chosen by what was asked, and never naming the
machinery behind the answer (knowledge base, RAG, vector store, retrieval,
tools, routes, prompts, internal ids). The LLM, vector store and live tools
are faked exactly as in test_grounding.py.
"""
import asyncio
import os
import re
import sys

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_chat  # noqa: E402
import answer_guard  # noqa: E402
import court_bazaar_tools  # noqa: E402
import counsel_matching  # noqa: E402
from tests.test_grounding import (  # noqa: E402,F401  (fixtures are used by name)
    DIAC, SOP, _SOP_SLA, _TWO_COUNSELS, _chat, _chunk, _fake_llm, _search_result, fake_rag, live_search,
)

INTERNAL_TERMS = re.compile(
    r"knowledge[- ]base|\bRAG\b|vector[- ]?store|retriev|\bchunks?\b|\btools?\b|\broutes?\b|system prompt|"
    r"internal (?:source|id)|file[_ ]search|\badv_[0-9a-f]+|\buser_[0-9a-f]+",
    re.IGNORECASE,
)


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ["DB_NAME"]]


def _turns(*messages):
    """Runs one anonymous conversation turn by turn; returns every reply."""
    async def body():
        db = _db()
        replies, conv, token = [], None, None
        try:
            for message in messages:
                result = await ai_chat.handle_chat_message(db, conv, message, None, client_ip="203.0.113.60",
                                                           conversation_token=token)
                conv = result["conversation_id"]
                token = token or result.get("conversation_token")
                replies.append(result["reply"])
        finally:
            await db.ai_conversations.delete_many({"conversation_id": conv})
            await db.ai_chat_messages.delete_many({"conversation_id": conv})
        return replies
    return asyncio.run(body())


# ---------------------------------------------------------------------------
# No internal terminology
# ---------------------------------------------------------------------------

def test_no_match_reply_never_mentions_a_knowledge_base(fake_rag):
    fake_rag["items"] = []
    reply = _chat("What does the DIAC Rules say about space law?")["reply"]
    assert "knowledge base" not in reply.lower()
    assert reply == ai_chat.DOCUMENT_NOT_FOUND_MESSAGE


def test_model_wording_about_retrieval_is_rephrased(fake_rag):
    fake_rag["items"] = [_chunk(SOP, _SOP_SLA)]
    fake_rag["answer"] = ("According to the retrieved excerpts, the printing vendor must accept the order within 2 "
                          "hours and deliver within 24 hours.")
    reply = _chat("What is the SLA for Printing Service?")["reply"]
    assert not INTERNAL_TERMS.search(reply), reply
    assert "within 2 hours" in reply and "available documents" in reply


def _fallback_replies(monkeypatch, fake_rag):
    fake_rag["items"] = []
    replies = {
        "document": _chat("What does the DIAC Rules say about space law?")["reply"],
        "sop topic": _chat("What is the SLA for Printing Service?")["reply"],
        "courtbazaar info": _chat("How does proxy counsel hiring work?")["reply"],
        "courtbazaar fact": _chat("How much does CourtBazaar charge for proxy counsel?")["reply"],
    }
    _fake_llm(monkeypatch, "See Sharma v. Union of India (2021) 4 SCC 99.")
    replies["legal"] = _chat("What does the law say about adverse possession?")["reply"]
    replies["pending count"] = _chat("What is the current number of pending hearing requests on CourtBazaar?")["reply"]
    replies["no results shown"] = _chat("the second one")["reply"]
    return replies


def test_no_fallback_or_clarification_uses_internal_terms(monkeypatch, fake_rag):
    for kind, reply in _fallback_replies(monkeypatch, fake_rag).items():
        assert not INTERNAL_TERMS.search(reply), f"{kind}: {reply}"


def test_fallbacks_are_chosen_by_context_not_one_message(monkeypatch, fake_rag):
    replies = _fallback_replies(monkeypatch, fake_rag)
    assert replies["document"] == ai_chat.DOCUMENT_NOT_FOUND_MESSAGE
    assert replies["courtbazaar info"] == ai_chat.COURTBAZAAR_INFO_UNAVAILABLE_MESSAGE
    assert replies["courtbazaar fact"] == answer_guard.UNVERIFIED_COURTBAZAAR_MESSAGE
    assert replies["legal"] == answer_guard.UNVERIFIED_LEGAL_MESSAGE
    assert len({replies["document"], replies["courtbazaar info"], replies["courtbazaar fact"], replies["legal"]}) == 4


# ---------------------------------------------------------------------------
# The four fallbacks
# ---------------------------------------------------------------------------

def test_courtbazaar_no_match_fallback(fake_rag):
    fake_rag["items"] = []
    assert _chat("How does proxy counsel hiring work?")["reply"] == (
        "I don’t have verified information about that yet. Could you ask about a specific CourtBazaar service or "
        "feature?")


def test_document_no_match_fallback(fake_rag):
    fake_rag["items"] = [_chunk(DIAC, "Rule 12: The emergency arbitrator shall be appointed within one day.")]
    fake_rag["answer"] = "The DIAC Rules set a 5% fee for space-law disputes."
    assert _chat("What does the DIAC Rules say about space law?")["reply"] == (
        "I couldn’t find that information in the available documents. If you tell me what you’re looking for, I "
        "can help with a related topic.")


def test_legal_insufficient_information_fallback(monkeypatch):
    _fake_llm(monkeypatch, "In Kumar v. State of Punjab (2020) 3 SCC 1 the court held so.")
    assert _chat("What is the law on adverse possession?")["reply"] == (
        "I don’t have enough verified information to answer that reliably. If you share more details, I can help "
        "explain the general legal concept.")


def test_non_legal_general_fallback_is_unchanged(monkeypatch):
    _fake_llm(monkeypatch, "See Doe v. Roe (1999) for details.")
    assert _chat("What is the capital of France?")["reply"] == answer_guard.UNVERIFIED_GENERAL_MESSAGE


def test_unsupported_courtbazaar_fact(monkeypatch, fake_rag):
    expected = ("I don’t have verified information about that at the moment. You can ask me about CourtBazaar "
                "services, courts, or Proxy Counsel.")
    fake_rag["items"] = []
    assert _chat("How many proxy counsels has CourtBazaar onboarded?")["reply"] == expected
    _fake_llm(monkeypatch, "CourtBazaar refunds 100% of fees within 24 hours.")
    assert _chat("What is a refund?")["reply"] == expected


# ---------------------------------------------------------------------------
# Follow-ups against a shown Proxy Counsel list
# ---------------------------------------------------------------------------

@pytest.fixture
def counsel_profiles(monkeypatch, live_search):
    live_search["result"] = _search_result(_TWO_COUNSELS)
    opened = []

    async def profile(_db, advocate_id):
        opened.append(advocate_id)
        counsel = next(c for c in _TWO_COUNSELS if c["advocate_id"] == advocate_id)
        return {"status": "success", "tool": "get_proxy_counsel_profile",
                "data": {k: counsel[k] for k in ("name", "practice_areas", "experience_years", "rating",
                                                 "proposed_fee")}}

    monkeypatch.setattr(court_bazaar_tools, "get_proxy_counsel_profile", profile)
    monkeypatch.setattr(counsel_matching, "check_public_list_rate_limit", lambda _key: None)
    _fake_llm(monkeypatch, "unused")
    return opened


@pytest.mark.parametrize("followup,expected", [
    ("Tell me details of the first counsel", "Adv. Mehta"),
    ("details of the second counsel", "Adv. Rao"),
    ("Tell me more about the first one", "Adv. Mehta"),
    ("2", "Adv. Rao"),
])
def test_first_counsel_follow_up_answers_directly(counsel_profiles, followup, expected):
    replies = _turns("Find proxy counsels in Delhi", followup)
    assert expected in replies[1]
    assert "Which results do you mean" not in replies[1]
    assert not INTERNAL_TERMS.search(replies[1])


def test_bare_tell_me_more_after_several_counsels_asks_which_one(counsel_profiles):
    replies = _turns("Find proxy counsels in Delhi", "tell me more")
    assert replies[1] == ai_chat.COUNSEL_CHOICE_MESSAGE
    assert "that result" not in replies[1] and "Which results do you mean" not in replies[1]
    assert counsel_profiles == []


def test_bare_tell_me_more_after_one_counsel_opens_it(counsel_profiles, live_search):
    live_search["result"] = _search_result(_TWO_COUNSELS[:1])
    replies = _turns("Find proxy counsels in Delhi", "tell me more")
    assert "Adv. Mehta" in replies[1]
    assert counsel_profiles == ["adv_1a2b3c"]


def test_follow_up_with_no_shown_results_still_clarifies(monkeypatch):
    _fake_llm(monkeypatch, "unused")
    assert _chat("Tell me details of the first counsel")["reply"] == ai_chat.AMBIGUOUS_FOLLOWUP_MESSAGE


def test_tell_me_more_after_a_general_answer_continues_the_topic(monkeypatch):
    _fake_llm(monkeypatch, "Arbitration is private dispute resolution.")
    llm = _fake_llm(monkeypatch, "An arbitral award is binding.")
    replies = _turns("What is arbitration?", "tell me more")
    assert replies[1] == "An arbitral award is binding."
    assert len(llm.calls) == 2


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", ["services", "Services", "What services are available?", "your services"])
def test_services_query_returns_the_service_list(monkeypatch, query):
    called = []

    async def services(_db, category=None):
        called.append(category)
        return {"status": "success", "tool": "get_services", "data": [
            {"name": "Photocopy", "category": "printing", "base_price": 2, "unit": "page"},
            {"name": "Proxy Counsel Appearance", "category": "counsel", "base_price": 1500, "unit": "hearing"},
        ]}

    monkeypatch.setattr(court_bazaar_tools, "get_services", services)
    _fake_llm(monkeypatch, "OCR (optical character recognition) converts scanned images into text.")
    decision = ai_chat.route_message(query, {})
    assert (decision["route"], decision["live_intent"]) == (ai_chat.ROUTE_COURTBAZAAR_LIVE, "services")
    reply = _chat(query)["reply"]
    assert called
    assert "OCR" not in reply and "optical character" not in reply
    assert "Photocopy" in reply


def test_singular_service_and_legal_service_questions_are_not_the_service_list():
    assert ai_chat.route_message("service", {})["live_intent"] is None
    assert ai_chat.route_message("What is OCR?", {})["live_intent"] is None
    assert ai_chat.route_message("What is substituted service of summons?", {})["live_intent"] is None


# ---------------------------------------------------------------------------
# General questions and casual turns
# ---------------------------------------------------------------------------

def test_general_question_is_answered_normally(monkeypatch):
    llm = _fake_llm(monkeypatch, "Paris is the capital of France.")
    assert _chat("What is the capital of France?")["reply"] == "Paris is the capital of France."
    assert llm.calls and llm.calls[0]["use_file_search"] is False


@pytest.mark.parametrize("text", ["Hi", "hello", "Hey!"])
def test_greeting(monkeypatch, text):
    llm = _fake_llm(monkeypatch, "unused")
    reply = _chat(text)["reply"]
    assert reply.startswith("Hi!") and "help" in reply
    assert llm.calls == []


@pytest.mark.parametrize("text", ["Thanks", "thank you", "thx!"])
def test_thanks(monkeypatch, text):
    llm = _fake_llm(monkeypatch, "unused")
    assert _chat(text)["reply"] == "You're welcome! Let me know if you need anything else."
    assert llm.calls == []


@pytest.mark.parametrize("text", ["Bye", "goodbye", "Good bye!", "see you"])
def test_goodbye(monkeypatch, text):
    llm = _fake_llm(monkeypatch, "unused")
    assert _chat(text)["reply"] == "Goodbye! Take care."
    assert llm.calls == []
