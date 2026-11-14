"""Instant Legal Help — regressions from the Nov 2026 audit, with OpenAI mocked:
1. A follow-up to a document answer is retrieved and answered from that document
   again (standalone query, same rules), never from general knowledge.
2. A card that leaves out a rule the verifier says answers part of the question
   gets one completeness retry, and a retry never loses coverage.
3. "According to the SOP ... DIAC" answers from the SOP instead of asking which document.
4. A question with no subject ("What is the time limit?") gets a clarifying question.
5. The vector store id never reaches the logs."""
import asyncio
import logging
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_answer_card import GOOD_POINT, ScriptedOpenAI, _card, _verdict  # noqa: E402
from test_rag_answer_quality import RULE_33_BODY, RULE_33_HEAD, _db, _install, _item  # noqa: E402

import ai_chat  # noqa: E402
import llm_service  # noqa: E402

RULE_31 = ("31. Arbitral Award \r\n31.1 The Arbitral Tribunal shall make an award within a period of eighteen \r\n"
           "months from the completion of the pleadings or such \r\nperiod as extended by the Court. \r\n")
AWARD_POINT = {"icon": "rule", "title": "Rule 31.1 — Arbitral Award", "badge": "Rule 31.1", "tone": "neutral",
               "text": "The Arbitral Tribunal shall make an award within a period of eighteen months from the "
                       "completion of the pleadings or such period as extended by the Court (Rule 31.1).", "cite": [1]}
AWARD_CARD = _card(summary="The Tribunal shall make an award within eighteen months from the completion of the "
                           "pleadings or such period as extended by the Court (Rule 31.1).",
                   points=[AWARD_POINT], follow_up=None)
EXTEND_CARD = _card(summary="The period may be extended by the Court (Rule 31.1).", points=[
    AWARD_POINT,
    # Not in Rule 31.1: the kind of condition the audit saw added from general knowledge.
    {**AWARD_POINT, "title": "Rule 31.1 — Extension by agreement",
     "text": "The parties may also agree to extend the period without the Court, before it expires (Rule 31.1)."},
], follow_up=None)
FIRST = "Under the DIAC Rules, what is the time limit for the Tribunal to make the award?"
FOLLOW_UP = "Can that time limit be extended? By whom?"


class RecordingOpenAI(ScriptedOpenAI):
    """ScriptedOpenAI that records every search query and can switch its excerpts."""

    def __init__(self, outputs, verdicts=(None,), items=None):
        super().__init__(outputs, verdicts)
        self.items = items if items is not None else [_item(RULE_31, score=0.9)]
        self.searches = []

    async def search(self, **kwargs):
        self.searches.append(kwargs)
        return SimpleNamespace(data=self.items)


def _conversation(monkeypatch, fake, *messages):
    _install(monkeypatch, fake)

    async def body():
        db, results, conv_id, token = _db(), [], None, None
        for message in messages:
            result = await ai_chat.handle_chat_message(db, conv_id, message, None, client_ip="127.0.0.1",
                                                       conversation_token=token)
            conv_id, token = result["conversation_id"], result.get("conversation_token") or token
            results.append(result)
        convo = await db.ai_conversations.find_one({"conversation_id": conv_id}, {"_id": 0})
        await db.ai_conversations.delete_many({"conversation_id": conv_id})
        await db.ai_chat_messages.delete_many({"conversation_id": conv_id})
        return results, convo
    return asyncio.run(body())


# 1. Follow-ups stay grounded ---------------------------------------------------

def test_follow_up_is_retrieved_again_from_the_same_document_with_its_rules(monkeypatch):
    fake = RecordingOpenAI([AWARD_CARD, AWARD_CARD])
    (first, second), convo = _conversation(monkeypatch, fake, FIRST, FOLLOW_UP)
    assert first["citations"][0]["rules"] == ["31.1"]
    assert len(fake.searches) == 2
    query = fake.searches[1]["query"]
    assert query.startswith(FOLLOW_UP) and FIRST in query and "Rule 31.1" in query
    assert fake.searches[1]["filters"]["value"] == "diac_rules"  # same document, never another
    assert second["grounding"] == "supported" and second["citations"][0]["rules"] == ["31.1"]
    # The answer model gets the standalone question; the earlier answer text is not part of it.
    assert fake.calls[-1]["input"][-1]["content"] == query and "eighteen" not in query
    assert convo["doc_context"]["question"] == FIRST  # a chain of follow-ups keeps the original question


def test_follow_up_cannot_add_conditions_the_rule_does_not_state(monkeypatch):
    fake = RecordingOpenAI([AWARD_CARD, EXTEND_CARD])
    (_, second), _ = _conversation(monkeypatch, fake, FIRST, FOLLOW_UP)
    assert [p["title"] for p in second["answer"]["points"]] == [AWARD_POINT["title"]]
    assert "agree to extend" not in second["reply"] and "without the Court" not in second["reply"]


def test_follow_up_the_document_does_not_answer_says_so(monkeypatch):
    fake = RecordingOpenAI([AWARD_CARD])
    _install(monkeypatch, fake)

    async def no_hits(**kwargs):
        fake.searches.append(kwargs)
        return SimpleNamespace(data=[] if len(fake.searches) > 1 else fake.items)
    fake.search = no_hits
    (_, second), _ = _conversation(monkeypatch, fake, FIRST, "Is there a limit on that extension?")
    assert second["grounding"] == "insufficient" and second["degraded"] is True
    assert second["reply"] == ai_chat.document_not_found_message(llm_service.SOURCE_DIAC)
    assert len(fake.calls) == 1  # no general-knowledge answer was generated for the follow-up


def test_generic_question_right_after_a_document_answer_is_a_follow_up(monkeypatch):
    fake = RecordingOpenAI([AWARD_CARD, AWARD_CARD])
    (_, second), _ = _conversation(monkeypatch, fake, FIRST, "What is the time limit?")
    assert second["grounding"] == "supported" and "Rule 31.1" in fake.searches[1]["query"]


@pytest.mark.parametrize("message", [
    "What is anticipatory bail and how does it work?",
    "What about Section 34 of the Arbitration and Conciliation Act?",
    "Who is the Prime Minister of India then?",
    "Who pays the stamp duty on that?",
])
def test_new_subjects_are_not_forced_onto_the_previous_document(message):
    convo = {"doc_context": {"source": llm_service.SOURCE_DIAC, "question": FIRST, "rules": ["31.1"]}}
    assert ai_chat._document_followup(message, convo, "The Tribunal shall make an award (Rule 31.1).") is None


@pytest.mark.parametrize("message", [FOLLOW_UP, "Who can extend it?", "What happens next?", "What if it is not extended?",
                                     "What happens if the award is not made within that period?"])
def test_referring_follow_ups_are_recognised(message):
    convo = {"doc_context": {"source": llm_service.SOURCE_DIAC, "question": FIRST, "rules": ["31.1"]}}
    last = "The Tribunal shall make an award within eighteen months or such period as extended by the Court (Rule 31.1)."
    assert ai_chat._document_followup(message, convo, last)["source"] == llm_service.SOURCE_DIAC


def test_no_follow_up_without_a_previous_document_answer():
    assert ai_chat._document_followup(FOLLOW_UP, {}, "") is None


def test_answers_are_told_earlier_replies_are_not_sources():
    assert "earlier replies in this conversation are not a source" in llm_service.RAG_EVIDENCE_INSTRUCTIONS


# 2. Completeness ---------------------------------------------------------------

LIABLE_POINT = {**GOOD_POINT, "title": "Rule 33.2 — Joint liability", "badge": "Rule 33.2", "tone": "neutral",
                "text": "Parties are jointly and severally liable for the deposits as directed by the Centre. Any "
                        "party is free to pay the whole of the deposits should the other party fail to pay its share "
                        "(Rule 33.2)."}
DEPOSITS_Q = "Under the DIAC Rules, what happens if a party does not pay its share of the deposits?"


def _deposits(monkeypatch, outputs, verdicts):
    fake = RecordingOpenAI(outputs, verdicts, items=[_item(RULE_33_BODY, score=0.87), _item(RULE_33_HEAD, score=0.61)])
    (result,), _ = _conversation(monkeypatch, fake, DEPOSITS_Q)
    return result, fake


def test_missing_relevant_rule_gets_one_completeness_retry(monkeypatch):
    result, fake = _deposits(monkeypatch, [_card(), _card(points=[LIABLE_POINT, GOOD_POINT])],
                             [_verdict(uncovered=["Rule 33.2"]), _verdict(points=("SUPPORTED", "SUPPORTED"))])
    assert len(fake.calls) == 2
    retry_notes = [m["content"] for m in fake.calls[1]["input"] if m["role"] == "developer"]
    assert any("Rule 33.2" in n and "left out" in n for n in retry_notes)
    assert {r for c in result["citations"] for r in c["rules"]} == {"33.2", "33.5"}


def test_a_retry_never_loses_coverage(monkeypatch):
    lost = _card(points=[{**LIABLE_POINT, "cite": [1]}])  # retry drops 33.5 and keeps only 33.2
    result, fake = _deposits(monkeypatch, [_card(points=[GOOD_POINT, LIABLE_POINT]), lost],
                             [_verdict(points=("SUPPORTED", "SUPPORTED"), uncovered=["33.1"]), _verdict()])
    assert len(fake.calls) == 2
    assert {r for c in result["citations"] for r in c["rules"]} == {"33.2", "33.5"}


@pytest.mark.parametrize("uncovered", [["99.1"], ["33.5"], []])
def test_no_retry_for_rules_not_in_the_excerpts_or_already_used(monkeypatch, uncovered):
    _, fake = _deposits(monkeypatch, [_card()], [_verdict(uncovered=uncovered)])
    assert len(fake.calls) == 1


def test_a_listed_part_the_answer_skipped_gets_the_completeness_retry(monkeypatch):
    fake = RecordingOpenAI([_card(), _card(points=[LIABLE_POINT, GOOD_POINT])], [_verdict(), _verdict(points=("SUPPORTED",) * 2)],
                           items=[_item(RULE_33_BODY, score=0.87), _item(RULE_33_HEAD, score=0.61)])
    (result,), _ = _conversation(monkeypatch, fake, "Under the DIAC Rules, explain the deposits, including "
                                                    "termination and who is liable?")
    notes = [m["content"] for m in fake.calls[1]["input"] if m["role"] == "developer"]
    assert any('"who is liable"' in n for n in notes) and not any('"termination"' in n for n in notes)
    assert {r for c in result["citations"] for r in c["rules"]} == {"33.2", "33.5"}


def test_listed_parts_the_documents_do_not_cover_do_not_trigger_a_retry():
    assert llm_service._unanswered_parts("Explain it, including fees and interest.", "The fees are fixed.",
                                         "The fees are fixed by the Centre.") == []


@pytest.mark.parametrize("section", ["Section 11 (6)", "section 29A(3)", "Section 29A"])
def test_section_of_an_act_is_not_cited_as_a_rule(section):
    number = section.split()[1][:2]
    context = f"1. Reference\nMatters are referred under {section} of the Act.\n{number}. Other rule"
    citations = llm_service.build_citations(f"Matters are referred under {section} of the Act (Rule 1).",
                                            context, [llm_service.SOURCE_SOP])
    assert [r for c in citations for r in c["rules"]] == ["1"]


def test_verifier_schema_requires_the_completeness_field():
    schema = llm_service.AnswerVerdict.model_json_schema()
    assert "uncovered_rules" in schema["required"] and set(schema["required"]) == set(schema["properties"])


# 3. SOP vs DIAC ----------------------------------------------------------------

@pytest.mark.parametrize("message,source", [
    ("According to the SOP, how are matters referred to DIAC?", llm_service.SOURCE_SOP),
    ("As per the SOP, who prepares the note for DIAC's Chairperson?", llm_service.SOURCE_SOP),
    ("Under the DIAC Rules, what does the SOP call a reference?", llm_service.SOURCE_DIAC),
])
def test_the_document_named_as_the_source_wins(message, source):
    decision = ai_chat.route_message(message)
    assert decision["route"] == ai_chat.ROUTE_DOCUMENT_RAG and decision["source"] == source


@pytest.mark.parametrize("message", [
    "What do the SOP and the DIAC Rules say about appointing arbitrators?",
    "According to the SOP and under the DIAC Rules, who appoints the arbitrator?",
])
def test_both_documents_as_sources_still_asks_which(message):
    assert ai_chat.route_message(message)["route"] == ai_chat.ROUTE_CLARIFY


# 4. Underspecified questions ---------------------------------------------------

@pytest.mark.parametrize("message", ["What is the time limit?", "What are the fees?", "what's the deadline",
                                     "How long is the limitation period?", "What is the procedure?"])
def test_question_without_a_subject_gets_a_clarifying_question(message, monkeypatch):
    assert ai_chat.route_message(message)["reason"] == "underspecified_question"
    fake = RecordingOpenAI([AWARD_CARD])
    (result,), _ = _conversation(monkeypatch, fake, message)
    assert result["reply"] == ai_chat.UNDERSPECIFIED_QUESTION_MESSAGE and fake.calls == [] and fake.searches == []


@pytest.mark.parametrize("message", ["What is the time limit for filing an appeal against a decree?",
                                     "What are the fees for an emergency arbitrator under the DIAC Rules?",
                                     "What is arbitration?"])
def test_questions_with_a_subject_are_answered(message):
    assert ai_chat.route_message(message)["reason"] != "underspecified_question"


# 5. Logs -----------------------------------------------------------------------

def test_vector_store_id_is_redacted_from_http_logs(monkeypatch, caplog):
    monkeypatch.setattr(llm_service, "OPENAI_VECTOR_STORE_ID", "vs_secret123456")
    with caplog.at_level(logging.INFO, logger="httpx"):
        logging.getLogger("httpx").info('HTTP Request: %s %s "%s"', "POST",
                                        "https://api.openai.com/v1/vector_stores/vs_secret123456/search", "HTTP/1.1 200 OK")
    assert "vs_secret123456" not in caplog.text and "/vector_stores/<vector_store>/search" in caplog.text
