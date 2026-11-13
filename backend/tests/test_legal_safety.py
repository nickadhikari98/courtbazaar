"""Phase 4 — legal answer safety and currentness on the GENERAL /
GENERAL_LEGAL path (answer_guard.guard_general_answer and the
GENERAL_LEGAL route note in ai_chat.py).

General legal questions are still answered from model knowledge — never
forced into RAG — but an answer may not present a repealed provision as
current, tie a well-known remedy to the wrong provision, or claim that
unverifiable law has been verified. End-to-end tests fake the LLM exactly
as test_grounding.py does; the real provider is never called.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_chat  # noqa: E402
import answer_guard  # noqa: E402
import llm_service  # noqa: E402
from tests.test_grounding import _chat, _fake_llm  # noqa: E402

guard = answer_guard.guard_general_answer


# ---------------------------------------------------------------------------
# Routing and prompt: unchanged route, no RAG, current-law guidance present
# ---------------------------------------------------------------------------

def test_legal_questions_still_route_to_general_legal_without_rag():
    for query in ("Can a court grant anticipatory bail?", "What is Order 39 of CPC?", "What is Order 40 CPC?"):
        decision = ai_chat.route_message(query)
        assert decision["route"] == ai_chat.ROUTE_GENERAL_LEGAL, query
        assert decision["route"] not in ai_chat.RAG_ROUTES


def test_general_legal_note_carries_current_law_guidance():
    note = ai_chat._ROUTE_NOTES[ai_chat.ROUTE_GENERAL_LEGAL]
    assert "Section 482 of the BNSS" in note and "formerly Section 438 CrPC" in note
    assert "Order 40 CPC" in note
    assert "never present an ipc, crpc or indian evidence act section as the current provision" in note.lower()


def test_prompt_facts_are_not_mistaken_for_a_prompt_leak(monkeypatch):
    text = ("Anticipatory bail is governed by Section 482 of the BNSS (formerly Section 438 CrPC). "
            "It lets a person seek bail before an arrest.")
    _fake_llm(monkeypatch, text)
    reply = _chat("Can a court grant anticipatory bail?")["reply"]
    assert reply.startswith(text)
    assert reply != answer_guard.PROMPT_LEAK_MESSAGE


# ---------------------------------------------------------------------------
# Anticipatory bail — outdated Section 438 CrPC
# ---------------------------------------------------------------------------

def test_anticipatory_bail_under_438_crpc_is_not_presented_as_current(monkeypatch):
    llm = _fake_llm(monkeypatch, "Yes. A Sessions Court or High Court can grant anticipatory bail under "
                                 "Section 438 of the CrPC to a person who fears arrest for a non-bailable offence.")
    reply = _chat("Can a court grant anticipatory bail?")["reply"]
    assert llm.calls[0]["use_file_search"] is False
    assert "Section 438 of the CrPC (pre-July 2024 CrPC provision; now Section 482 BNSS)" in reply
    assert "can grant anticipatory bail" in reply  # the useful explanation survives
    assert answer_guard.LEGAL_VERIFY_NOTE in reply


def test_bare_section_438_in_an_anticipatory_bail_answer_is_treated_as_the_old_crpc():
    reply = guard("Anticipatory bail is granted under Section 438.", legal=True)
    assert "now Section 482 BNSS" in reply


def test_anticipatory_bail_under_the_wrong_new_section_is_removed():
    reply = guard("Anticipatory bail is a pre-arrest remedy. It is now granted under Section 438 of the BNSS.",
                  legal=True)
    assert "438 of the BNSS" not in reply
    assert "Anticipatory bail is a pre-arrest remedy." in reply
    assert answer_guard.ANTICIPATORY_BAIL_NOTE in reply


def test_anticipatory_bail_under_482_crpc_is_removed():
    reply = guard("Anticipatory bail can be sought under Section 482 CrPC.", legal=True)
    assert "482 CrPC" not in reply
    assert answer_guard.ANTICIPATORY_BAIL_NOTE in reply


def test_correct_current_anticipatory_bail_reference_is_kept_unannotated():
    text = "Anticipatory bail is governed by Section 482 of the BNSS, which replaced Section 438 CrPC."
    reply = guard(text, legal=True)
    assert reply.startswith(text)
    assert "pre-July 2024" not in reply


def test_wrong_old_to_new_mapping_is_removed():
    reply = guard("Anticipatory bail is under Section 480 BNSS (formerly Section 438 CrPC).", legal=True)
    assert "480" not in reply
    assert answer_guard.ANTICIPATORY_BAIL_NOTE in reply


def test_other_repealed_code_sections_are_flagged_as_old():
    reply = guard("Murder is punishable under Section 302 IPC.", legal=True)
    assert "Section 302 IPC (pre-July 2024 IPC provision; now Section 103 BNS)" in reply
    reply = guard("Electronic records need a certificate under Section 65B of the Indian Evidence Act.", legal=True)
    assert "now Section 63 BSA" in reply
    # Unmapped: flagged as old without guessing a new number.
    reply = guard("Section 91 CrPC lets a court summon documents.", legal=True)
    assert "Section 91 CrPC (pre-July 2024 CrPC provision, since replaced by the BNSS)" in reply


def test_historically_framed_old_section_is_left_alone():
    text = "Before 1 July 2024, anticipatory bail was granted under Section 438 CrPC."
    assert guard(text, legal=True).startswith(text)


# ---------------------------------------------------------------------------
# Order 39 / Order 40 CPC — receivers
# ---------------------------------------------------------------------------

def test_order_39_answer_cannot_place_receivers_under_order_39(monkeypatch):
    _fake_llm(monkeypatch, "Order 39 of the CPC deals with temporary injunctions and interlocutory orders. "
                           "It also empowers the court to appoint a receiver to manage the property.")
    reply = _chat("What is Order 39 of CPC?")["reply"]
    assert "Order 39 of the CPC deals with temporary injunctions and interlocutory orders." in reply
    assert "appoint a receiver to manage" not in reply
    assert answer_guard.RECEIVER_NOTE in reply
    assert "Order 40" in reply


def test_receivers_under_order_39_in_one_sentence_is_removed():
    reply = guard("Order XXXIX CPC covers temporary injunctions and the appointment of receivers.", legal=True)
    assert "appointment of receivers" not in reply.split(answer_guard.RECEIVER_NOTE)[0]
    assert answer_guard.RECEIVER_NOTE in reply


def test_order_40_answer_keeps_receivers_under_order_40(monkeypatch):
    text = ("Order 40 of the CPC deals with the appointment of receivers. A receiver manages disputed property "
            "under the court's supervision while the suit is pending.")
    _fake_llm(monkeypatch, text)
    reply = _chat("What is Order 40 CPC?")["reply"]
    assert reply.startswith(text)
    assert answer_guard.RECEIVER_NOTE not in reply


def test_order_40_answer_cannot_move_receivers_to_another_order():
    reply = guard("Receivers are appointed under Order 38 CPC. A receiver holds property for the court.",
                  legal=True)
    assert "Order 38" not in reply
    assert answer_guard.RECEIVER_NOTE in reply
    reply = guard("Order XL CPC deals with receivers.", legal=True)  # roman numeral for 40
    assert reply.startswith("Order XL CPC deals with receivers.")


def test_temporary_injunction_under_the_wrong_order_is_removed():
    reply = guard("A temporary injunction is granted under Order 40 CPC.", legal=True)
    assert "Order 40 CPC." not in reply.split(answer_guard.INJUNCTION_NOTE)[0]
    assert answer_guard.INJUNCTION_NOTE in reply


# ---------------------------------------------------------------------------
# Normal answers stay useful; unverified law is qualified
# ---------------------------------------------------------------------------

def test_normal_general_legal_question_is_answered_without_refusal_or_noise(monkeypatch):
    text = ("A public interest litigation lets a person approach a High Court or the Supreme Court about a matter "
            "affecting the public, even if they aren't personally harmed.")
    _fake_llm(monkeypatch, text)
    reply = _chat("What is a PIL?")["reply"]
    assert reply == text
    assert answer_guard.UNVERIFIED_GENERAL_MESSAGE not in reply


def test_limitation_period_in_words_is_qualified():
    reply = guard("A suit to recover money generally has a limitation period of three years.", legal=True)
    assert "three years" in reply
    assert answer_guard.LEGAL_VERIFY_NOTE in reply


def test_named_statute_is_qualified():
    reply = guard("Consumer complaints are filed under the Consumer Protection Act, 2019.", legal=True)
    assert answer_guard.LEGAL_VERIFY_NOTE in reply


def test_current_law_question_gets_a_currentness_qualification():
    reply = guard("Bail for bailable offences is a matter of right.", legal=True,
                  question="What is the current law on bail?")
    assert answer_guard.CURRENT_LAW_NOTE in reply


def test_non_legal_answer_is_not_given_a_legal_note():
    reply = guard("Python is a programming language.", legal=False, question="What is the latest Python?")
    assert reply == "Python is a programming language."


# ---------------------------------------------------------------------------
# Fabricated statutes / cases / deadlines are never presented as verified
# ---------------------------------------------------------------------------

def test_fabricated_citation_and_deadline_are_not_presented_as_verified(monkeypatch):
    _fake_llm(monkeypatch, "Under Section 12 of the Digital Tenancy Protection Act, 2021, a tenant must file "
                           "within 15 days. I have verified this against the latest official text. In Mehta v. "
                           "Union of India (2022) 5 SCC 10 the Supreme Court confirmed it.")
    reply = _chat("What is the deadline for a tenant complaint?")["reply"]
    assert "verified this" not in reply
    assert "Mehta" not in reply and "SCC" not in reply
    assert answer_guard.LEGAL_VERIFY_NOTE in reply


def test_claims_of_verification_or_currency_are_removed():
    for claim in ("This is the current, verified position of law.",
                  "This has been confirmed as up to date.",
                  "I've checked the latest amendments and this is accurate."):
        reply = guard("The limitation period is 30 days. " + claim, legal=True)
        assert claim not in reply
        assert "The limitation period is 30 days." in reply
        assert answer_guard.LEGAL_VERIFY_NOTE in reply


def test_everything_removed_falls_back_to_the_correction_not_a_bare_refusal():
    reply = guard("Anticipatory bail is under Section 438 BNSS.", legal=True)
    assert answer_guard.ANTICIPATORY_BAIL_NOTE in reply
    assert "438 BNSS" not in reply


# ---------------------------------------------------------------------------
# Phase 3 behavior preserved on the document path
# ---------------------------------------------------------------------------

def test_document_path_is_not_touched_by_the_general_legal_guard(monkeypatch):
    evidence = "The SOP says Section 438 CrPC applications are handled by the legal desk."
    assert answer_guard.validate_grounded_answer(
        "Section 438 CrPC applications are handled by the legal desk.", evidence, document_evidence=True,
    ) == "Section 438 CrPC applications are handled by the legal desk."
    assert ai_chat.route_message("What does the SOP say about refunds?")["route"] in ai_chat.RAG_ROUTES
    assert llm_service.SOURCE_SOP != llm_service.SOURCE_DIAC
