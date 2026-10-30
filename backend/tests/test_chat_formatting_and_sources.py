"""Instant Legal Help — manual-testing fixes (2026-10-16).

1. A harmless request to lay an answer out with headings, numbered steps,
   nested bullets and separators drew "I can't use that format" and then a
   similar answer anyway: SYSTEM_PROMPT says PLAIN TEXT ONLY / no headings,
   and _sanitize_reply stripped headings from every non-document answer. An
   explicit layout request now gets FORMATTING_REQUEST_NOTE and keeps the
   same safe Markdown subset document answers use.
2. Sources showed only "DIAC Rules": KB_SOURCE_DISPLAY abbreviated the label,
   and the PDF bundles three separately numbered sets of rules, so "Rule 4"
   alone didn't say which set it was from. Verified rules are now listed
   under the set the retrieved text labels them with, never guessed.

The model is mocked; every check is on what the pipeline does with its output.
"""
import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_chat  # noqa: E402
import answer_guard  # noqa: E402
import llm_service  # noqa: E402

DIAC = llm_service.SOURCE_DIAC
DIAC_LABEL = llm_service.KB_SOURCE_DISPLAY[DIAC]["label"]
PROCEEDINGS_2023 = "Delhi International Arbitration Centre (Arbitration Proceedings) Rules, 2023"
COSTS_2018 = "Delhi International Arbitration Centre (Administrative Costs & Arbitrators' Fees) Rules, 2018"

FORMATTED_ANSWER = """## Applying for a passport

1. Register on the official portal
  - Create an account
  - Choose the application type
2. Book an appointment

---

## On the day
- Carry your original documents."""


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _ask(message):
    async def body():
        db = _db()
        result = await ai_chat.handle_chat_message(db, None, message, None, client_ip="127.0.0.1")
        await db.ai_conversations.delete_many({"conversation_id": result["conversation_id"]})
        await db.ai_chat_messages.delete_many({"conversation_id": result["conversation_id"]})
        return result
    return asyncio.run(body())


def _fake_model(monkeypatch, text):
    seen = {}

    async def fake_generate(messages, use_file_search=False, selected_source=None, on_status=None):
        seen["messages"] = messages
        seen["use_file_search"] = use_file_search
        return {"ok": True, "text": text, "sources": []}

    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "generate_response", fake_generate)
    return seen


def _system_notes(seen):
    return [m["content"] for m in seen["messages"] if m["role"] == "system"]


# ---------------------------------------------------------------------------
# 1. Harmless formatting requests
# ---------------------------------------------------------------------------

def test_system_prompt_forbids_refusing_a_requested_layout():
    assert "never a reason to refuse or to say you can't format" in ai_chat.SYSTEM_PROMPT


def test_explicit_layout_request_sends_the_formatting_note_and_keeps_the_structure(monkeypatch):
    seen = _fake_model(monkeypatch, FORMATTED_ANSWER)
    result = _ask("Explain how to apply for a passport in India. Please format it with headings, "
                  "numbered steps, nested bullets and separators.")
    assert ai_chat.FORMAT_REQUEST_NOTE in _system_notes(seen)
    assert seen["use_file_search"] is False  # still a general answer, no documents implied
    reply = result["reply"]
    assert [ln for ln in reply.splitlines() if ln.startswith("## ")] == ["## Applying for a passport", "## On the day"]
    assert "1. Register on the official portal" in reply and "2. Book an appointment" in reply
    assert " - Create an account" in reply  # sub-bullet stays indented under its step
    assert "\n---\n" in reply
    assert "- Carry your original documents." in reply
    assert result["citations"] == [] and result["grounding"] is None


def test_requested_layout_still_strips_links_html_and_code(monkeypatch):
    _fake_model(monkeypatch, "## Steps\n1. Visit [the site](https://evil.example)\n<script>x</script>\n```\ncode\n```")
    reply = _ask("Give me the steps as a numbered list with headings.")["reply"]
    assert "## Steps" in reply and "1. Visit the site" in reply
    assert "https://evil.example" not in reply and "<script>" not in reply and "```" not in reply


def test_requested_layout_keeps_the_general_legal_safeguards(monkeypatch):
    seen = _fake_model(monkeypatch, "## Bail\n- Anticipatory bail is sought before arrest under Section 482 of the BNSS.")
    result = _ask("What is anticipatory bail? Use headings and bullet points.")
    notes = _system_notes(seen)
    assert ai_chat.FORMAT_REQUEST_NOTE in notes
    assert ai_chat._ROUTE_NOTES[ai_chat.ROUTE_GENERAL_LEGAL] in notes  # legal route rules still sent
    assert "## Bail" in result["reply"]
    assert answer_guard.LEGAL_VERIFY_NOTE in result["reply"] or answer_guard.CURRENT_LAW_NOTE in result["reply"]


def test_no_layout_request_keeps_the_plain_text_path(monkeypatch):
    seen = _fake_model(monkeypatch, "## Bail\n**Anticipatory bail** is bail sought before arrest.")
    result = _ask("What is anticipatory bail? Explain step by step.")  # detail, not a layout
    assert ai_chat.FORMAT_REQUEST_NOTE not in _system_notes(seen)
    assert "##" not in result["reply"] and "**" not in result["reply"]


def test_formatting_note_is_protected_from_disclosure():
    assert ai_chat.FORMAT_REQUEST_NOTE in ai_chat._protected_texts()
    leaked = "Sure. " + ai_chat.FORMAT_REQUEST_NOTE
    cleaned, flags = answer_guard.check_output(leaked, ai_chat._protected_texts())
    assert flags and ai_chat.FORMAT_REQUEST_NOTE not in cleaned


# ---------------------------------------------------------------------------
# 2. Source attribution
# ---------------------------------------------------------------------------

def _label(rule, title=""):
    return f"[Source: {DIAC} | Rule {rule}{' | ' + title if title else ''}]"


CONTEXT = "\n\n".join([
    _label("33", "DELHI INTERNATIONAL ARBITRATION CENTRE (ARBITRATION PROCEEDINGS) RULES. 2023 PART-A: INTRODUCTION")
    + "\n33. Advance on Costs",
    _label("33.5", "DELHI INTERNATIONAL ARBITRATION CENTRE (ARBITRATION PROCEEDINGS) RULES. 2023 PART-A: INTRODUCTION")
    + "\n33.5 If a party fails to make the deposits as directed within thirty days, the Centre may terminate.",
    _label("5", "DELHI INTERNATIONAL ARBITRATION CENTRE (ADMINISTRATIVE COSTS & ARBITRATORS' FEES) RULES, 2018")
    + "\n5. Miscellaneous expenses shall be paid equally by the parties.",
    # Rule 4 is retrieved from two different sets: ambiguous.
    _label("4", "DELHI INTERNATIONAL ARBITRATION CENTRE (ARBITRATION PROCEEDINGS) RULES. 2023")
    + "\n4. Request for Arbitration",
    _label("4", "DELHI INTERNATIONAL ARBITRATION CENTRE (ADMINISTRATIVE COSTS & ARBITRATORS' FEES) RULES, 2018")
    + "\n4. Payment of fees in advance.",
    # The cover/index page lists all three sets: names none.
    _label("2", "DIXC ♦ DELHI INTERNATIONAL ARBITRATION CENTRE (ARBITRATION PROCEEDINGS) RULES, 2023 ♦ DELHI "
                "INTERNATIONAL ARBITRATION CENTRE (INTERNAL MANAGEMENT) RULES, 2012 ♦ DELHI INTERNATIONAL "
                "ARBITRATION CENTRE (ADMINISTRATIVE COSTS & ARBITRATORS'FEES) RULES, 2018")
    + "\n2. Definitions",
    # Untitled block and a block from another file.
    _label("7", "PRELIMINARY") + "\n7. Arbitrators' fees are payable on termination.",
    f"[Source: other.pdf | Rule 9 | DELHI INTERNATIONAL ARBITRATION CENTRE (INTERNAL MANAGEMENT) RULES]\n9. Other.",
])


def _cite(answer):
    return llm_service.build_citations(answer, CONTEXT, [DIAC])


def test_a_verified_rule_is_shown_under_the_full_name_of_its_own_set():
    assert _cite("The Centre may terminate (Rule 33.5).") == [
        {"title": PROCEEDINGS_2023, "url": llm_service.KB_INSTRUMENT_URLS[PROCEEDINGS_2023], "rules": ["33.5"],
         "document": DIAC_LABEL},
    ]


def test_rules_from_different_sets_become_separate_sources():
    citations = _cite("Termination (Rule 33.5). Expenses are shared (Rule 5).")
    # Ordered by rule number, as the rules list always has been.
    assert [(c["title"], c["rules"]) for c in citations] == [(COSTS_2018, ["5"]), (PROCEEDINGS_2023, ["33.5"])]
    assert all(c["document"] == DIAC_LABEL for c in citations)


def test_a_bare_parent_rule_takes_the_set_of_its_labelled_sub_rules():
    citations = _cite("Rule 33 applies.")
    assert citations == [{"title": PROCEEDINGS_2023, "url": llm_service.KB_INSTRUMENT_URLS[PROCEEDINGS_2023],
                          "rules": ["33"], "document": DIAC_LABEL}]


def test_a_number_found_in_two_sets_is_never_pinned_on_either():
    citations = _cite("Fees are paid in advance (Rule 4).")
    assert citations == [{"title": DIAC_LABEL, "url": None, "rules": ["4"], "document": DIAC_LABEL}]


def test_cover_page_untitled_and_other_file_labels_name_no_set():
    citations = _cite("Definitions (Rule 2). Fees on termination (Rule 7). Other (Rule 9).")
    # 9 only appears in another file's block, which never counts as evidence of a set;
    # it is a provision number in the context text, so it stays with the document.
    assert [c["title"] for c in citations] == [DIAC_LABEL]
    assert citations[0]["rules"] == ["2", "7", "9"]


def test_invented_rules_and_page_numbers_are_still_never_cited():
    citations = _cite("See Rule 99 and Rule 33.9 (page 28).")
    assert citations == [{"title": DIAC_LABEL, "url": None, "rules": [], "document": DIAC_LABEL}]


def test_no_document_url_is_invented():
    assert all(entry["url"] is None for entry in llm_service.KB_SOURCE_DISPLAY.values())
    citations = _cite("Termination (Rule 33.5). Expenses (Rule 5).")
    assert all(c["url"] == llm_service.KB_INSTRUMENT_URLS[c["title"]] for c in citations)


def test_document_label_is_the_full_name_not_the_file_name():
    assert DIAC_LABEL == "Delhi International Arbitration Centre (DIAC) Rules"
    assert "conclusive_UsingOCR" not in DIAC_LABEL
