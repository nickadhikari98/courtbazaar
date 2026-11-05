"""Instant Legal Help: closing notes, no-answer replies and heading numbers (2026-10-16).

- Document answers that had something removed ended in two stacked notes:
  the guard's generic "Some details couldn't be verified ..." and the verify
  caveat. They now end in one note that names the document.
- A document question with nothing to answer from names the document that
  was searched and invites the user to share the rule.
- A removed section left headings numbered 1, 3, 4; clear heading sequences
  are renumbered, nothing else is.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_chat  # noqa: E402
import answer_guard  # noqa: E402
import llm_service  # noqa: E402

PROCEEDINGS = "Delhi International Arbitration Centre (Arbitration Proceedings) Rules, 2023"
DIAC_LABEL = llm_service.KB_SOURCE_DISPLAY[llm_service.SOURCE_DIAC]["label"]
CITED = [{"title": PROCEEDINGS, "url": None, "rules": ["8.6"], "document": DIAC_LABEL}]
UNCITED = [{"title": DIAC_LABEL, "url": None, "rules": [], "document": DIAC_LABEL}]
ANSWER = "The Chairperson/ Sub-Committee shall appoint the Arbitrator (Rule 8.6)."


# --- closing notes -----------------------------------------------------------

def test_a_partial_document_answer_ends_in_one_note_naming_the_rule_set():
    reply = ai_chat._document_closing(f"{ANSWER}\n\n{answer_guard.PARTIAL_ANSWER_NOTE}", CITED)
    body, note = reply.split("\n\n")
    assert body == ANSWER
    assert answer_guard.PARTIAL_ANSWER_NOTE not in reply
    assert note.startswith(f"I've included only what is stated directly in the {PROCEEDINGS};")
    assert "share it and I'll check it" in note
    assert note.count("Rules and their numbering can change") == 1
    assert "This is based on the" not in reply  # no second, stacked caveat


def test_a_partial_answer_without_cited_rules_names_the_document_without_the_rule_caveat():
    reply = ai_chat._document_closing(f"Some text.\n\n{answer_guard.PARTIAL_ANSWER_NOTE}", UNCITED)
    assert reply.endswith(ai_chat.DOCUMENT_PARTIAL_NOTE.format(title=DIAC_LABEL))
    assert "numbering can change" not in reply


def test_a_complete_answer_with_cited_rules_keeps_the_existing_verify_note():
    assert ai_chat._document_closing(ANSWER, CITED) == f"{ANSWER}\n\n{ai_chat.DOCUMENT_VERIFY_NOTE.format(title=PROCEEDINGS)}"


def test_a_complete_answer_without_rules_gets_no_note():
    assert ai_chat._document_closing(ANSWER, UNCITED) == ANSWER


def test_internal_wording_never_appears_in_the_new_notes():
    texts = [ai_chat.DOCUMENT_PARTIAL_NOTE, ai_chat.DOCUMENT_SOURCE_NOT_FOUND_MESSAGE, answer_guard.PARTIAL_ANSWER_NOTE]
    for text in texts:
        assert not any(w in text.lower() for w in ("retriev", "knowledge base", "excerpt", "validat", "vector", "prompt"))


# --- no-answer replies ------------------------------------------------------

def test_no_answer_reply_names_the_document_and_invites_the_rule():
    reply = ai_chat.document_not_found_message(llm_service.SOURCE_DIAC)
    assert reply.startswith(f"I couldn’t find anything in the {DIAC_LABEL} that answers this.")
    assert "rule number" in reply


def test_no_answer_reply_without_a_known_document_keeps_the_generic_wording():
    assert ai_chat.document_not_found_message(None) == ai_chat.DOCUMENT_NOT_FOUND_MESSAGE
    assert ai_chat.document_not_found_message("unknown.pdf") == ai_chat.DOCUMENT_NOT_FOUND_MESSAGE


# --- end to end: a partial DIAC answer with no verified rule falls back -------

def _rag_result(text, partial, rules):
    async def fake_generate(messages, use_file_search=False, selected_source=None, on_status=None):
        citations = [{"title": DIAC_LABEL, "url": None, "rules": rules, "document": DIAC_LABEL}]
        return {"ok": True, "text": text, "sources": [llm_service.SOURCE_DIAC], "citations": citations,
                "partial": partial}
    return fake_generate


def test_a_partial_diac_answer_with_no_verified_rule_becomes_a_clear_fallback(monkeypatch):
    from tests.test_chat_formatting_and_sources import _ask
    text = ("You may want to consult the Arbitration and Conciliation Act, 1996, or seek legal advice.\n\n"
            + answer_guard.PARTIAL_ANSWER_NOTE)
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "generate_response", _rag_result(text, partial=True, rules=[]))
    result = _ask("What do the DIAC rules say about appealing an award to the Supreme Court?")
    assert result["reply"] == ai_chat.document_not_found_message(llm_service.SOURCE_DIAC)
    assert result["citations"] == [] and result["grounding"] == "insufficient" and result["degraded"] is True


def test_a_partial_diac_answer_with_a_verified_rule_is_kept(monkeypatch):
    from tests.test_chat_formatting_and_sources import _ask
    text = f"{ANSWER}\n\n{answer_guard.PARTIAL_ANSWER_NOTE}"
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "generate_response", _rag_result(text, partial=True, rules=["8.6"]))
    result = _ask("What do the DIAC rules say about appointing an arbitrator?")
    assert result["reply"].startswith(ANSWER) and result["grounding"] == "partial"
    assert result["citations"][0]["rules"] == ["8.6"]


# --- end to end: a removed section's number gap is closed --------------------

def test_a_formatted_general_answer_with_a_removed_section_is_renumbered(monkeypatch):
    from tests.test_chat_formatting_and_sources import _ask, _fake_model
    _fake_model(monkeypatch, "## 1. What it is\nAnticipatory bail is bail sought before arrest.\n\n"
                             "## 2. Leading case\nArnesh Kumar v. State of Bihar decided this.\n\n"
                             "## 3. Next step\nAsk a qualified advocate about your facts.")
    reply = _ask("What is anticipatory bail? Use numbered headings.")["reply"]
    assert "Arnesh" not in reply and "Leading case" not in reply
    headings = [ln for ln in reply.splitlines() if ln.startswith("## ")]
    assert headings == ["## 1. What it is", "## 2. Next step"]


# --- heading numbers ----------------------------------------------------------

def test_a_missing_middle_section_is_renumbered():
    text = "### 1. Sharing\nA.\n\n### 3. Expenses\nB.\n\n### 4. Accounts\nC."
    assert ai_chat.renumber_heading_sequences(text) == "### 1. Sharing\nA.\n\n### 2. Expenses\nB.\n\n### 3. Accounts\nC."


def test_already_sequential_headings_are_unchanged():
    text = "## 1. One\nx\n## 2. Two\ny\n## 3. Three"
    assert ai_chat.renumber_heading_sequences(text) == text


def test_separate_heading_groups_are_numbered_on_their_own():
    text = ("## 1. Filing\n## 3. Fees\n"
            "## Next steps\n"            # unnumbered heading of the same level ends the first group
            "## 1. Call\n## 2. Visit")
    assert ai_chat.renumber_heading_sequences(text) == "## 1. Filing\n## 2. Fees\n## Next steps\n## 1. Call\n## 2. Visit"


def test_mixed_levels_keep_each_level_and_deeper_headings_dont_break_a_sequence():
    text = ("## 1. Overview\n### 1. Who\n### 3. What\n"
            "## 3. Costs\n### 2. Later\n")
    out = ai_chat.renumber_heading_sequences(text)
    # "##" 1, 3 -> 1, 2. The first "###" run (1, 3) -> 1, 2; the "###" under
    # the next "##" starts at 2, so it's not a clear sequence and is kept.
    assert out == "## 1. Overview\n### 1. Who\n### 2. What\n## 2. Costs\n### 2. Later\n"


def test_rule_numbers_years_and_body_lists_are_never_changed():
    text = ("## 33.5 Termination\n## 33.1 Deposits\n"
            "1. First step\n3. Third step\n"
            "## 2023 Rules\n"
            "Under Rule 8.6 the Chairperson appoints.")
    assert ai_chat.renumber_heading_sequences(text) == text


def test_a_sequence_that_names_rules_is_left_alone():
    text = "### 1. Rule 4 basics\n### 3. Rule 5 expenses"
    assert ai_chat.renumber_heading_sequences(text) == text


def test_sequences_not_starting_at_one_or_not_increasing_are_left_alone():
    for text in ("## 2. A\n## 4. B", "## 1. A\n## 3. B\n## 2. C", "## 1. A\n## 1. B\n## 3. C"):
        assert ai_chat.renumber_heading_sequences(text) == text, text
