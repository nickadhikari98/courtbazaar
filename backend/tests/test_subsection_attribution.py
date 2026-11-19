"""A sentence citing a Section, Article or Paragraph is checked against that provision's own text, down
to its numbered sub-section. The known failure: Section 11(6) content labelled "(Section 11(1))" passed,
and so did the same content labelled "(Section 34)", because only "Rule" citations were checked.
Act text comes from the approved PDF in backend/ai_knowledge (skipped where absent)."""
import re
from pathlib import Path

import pytest

import answer_guard
import llm_service
import rag_provisions

ACT = "Arbitration-And-Conciliation-Act-1996-as-on-2026-06-01.pdf"
DIAC = "DIAC Rules conclusive_UsingOCR.pdf"
ACT_PATH = Path(__file__).resolve().parents[1] / "ai_knowledge" / ACT


@pytest.fixture(scope="module")
def act_text():
    if not ACT_PATH.exists():
        pytest.skip("approved Act PDF not present")
    import fitz
    with fitz.open(ACT_PATH) as doc:
        return "".join(page.get_text() for page in doc)


def _section(text, head, nxt):
    start = [m.start() for m in re.finditer(re.escape(head), text)][-1]  # the body, not the contents page
    return text[start:text.find(nxt, start + 10)]


@pytest.fixture(scope="module")
def context(act_text):
    parts = {
        "Section 9": ("9. Interim measures, etc., by Court", "10. Number of arbitrators"),
        "Section 11": ("11. Appointment of arbitrators", "11A. Power of Central Government"),
        "Section 21": ("21. Commencement of arbitral proceedings", "22. Language"),
        "Section 29A": ("29A. Time limit for arbitral award", "29B. Fast track procedure"),
        "Section 34": ("34. Application for setting aside arbitral award", "35. Finality"),
    }
    return "\n\n".join(f"[Source: {ACT} | {label}]\n{_section(act_text, *heads)}" for label, heads in parts.items())


@pytest.fixture(scope="module")
def provisions(context):
    return rag_provisions.provision_map(context)


S11_6 = ("a party may request the Supreme Court or the High Court to take the necessary measure where a party "
         "fails to act as required under the agreed appointment procedure")


def _kept(sentence, provisions):
    out, dropped = answer_guard.validate_rule_attribution(sentence, provisions)
    return dropped == 0 and out is not None


def test_sub_sections_are_split_including_amendment_brackets_and_page_breaks(provisions):
    for key in ("section 11(1)", "section 11(6)", "section 11(6A)", "section 9(2)", "section 29A(3)", "section 34(3)"):
        assert key in provisions, key
    assert provisions["section 11(1)"].startswith("(1) A person of any nationality")
    assert "take the necessary measure" in provisions["section 11(6)"]
    assert "take the necessary measure" not in provisions["section 11(1)"]
    assert "ninety days" in provisions["section 9(2)"]  # "2[(2) ..." opens with an amendment's bracket
    assert "by consent" in provisions["section 29A(3)"]  # starts after a page's footnotes
    assert "section 21(1)" not in provisions  # one paragraph, no sub-sections
    assert provisions["11"] == provisions["section 11"]  # bare numbers still work for Rule-style callers


@pytest.mark.parametrize("cited,kept", [
    ("Section 11(1)", False),  # the real-model failure: 11(6) content, 11(1) label
    ("Section 34", False),  # the wrong section entirely
    ("Section 11(4)", False),  # a neighbouring sub-section
    ("Section 11(6)", True),
    ("Section 11", True),  # the whole section covers it
])
def test_a_sentence_is_kept_only_under_the_provision_that_says_it(provisions, cited, kept):
    assert _kept(f"Under the Arbitration and Conciliation Act, 1996, {S11_6} ({cited}).", provisions) is kept


def test_consent_and_court_extensions_are_told_apart(provisions):
    consent = "The parties may, by consent, extend the period for making the award by a further period not exceeding six months"
    assert _kept(f"{consent} (Section 29A(3)).", provisions)
    assert not _kept(f"{consent} (Section 29A(4)).", provisions)


def test_amended_sub_section_and_lists_of_sub_sections(provisions):
    assert _kept("Where a Court passes an interim measure before arbitration, the arbitral proceedings shall be "
                 "commenced within ninety days from the date of such order (Section 9(2)).", provisions)
    assert not _kept("Where a Court passes an interim measure before arbitration, the arbitral proceedings shall be "
                     "commenced within ninety days from the date of such order (Section 9(3)).", provisions)
    assert answer_guard._attribution_refs("(Section 11(4) and (5))", provisions) == ["section 11(4)", "section 11(5)"]
    assert answer_guard._attribution_refs("(Sections 9 and 34(3))", provisions) == ["section 9", "section 34(3)"]
    assert answer_guard._attribution_refs("(Section 34(2)(a)(iii))", provisions) == ["section 34(2)"]  # clause -> its sub-section


def test_a_section_without_sub_sections_stands_for_any_and_a_missing_one_is_dropped(provisions):
    commence = ("The arbitral proceedings commence on the date on which the respondent receives a request for the "
                "dispute to be referred to arbitration")
    assert _kept(f"{commence} (Section 21(1)).", provisions)
    assert not _kept(f"A party may apply to the court (Section 11(15)).", provisions)  # no such sub-section retrieved


def test_another_instruments_section_and_an_unretrieved_kind_are_left_alone(provisions):
    assert answer_guard._attribution_refs("enforced as a decree under Section 36 of the Code of Civil Procedure.", provisions) == []
    rules_only = {"8.6": "x", "rule 8.6": "x"}  # a DIAC answer with no Act retrieved: "Section 29A" names another document
    assert answer_guard._attribution_refs("see Section 29A of the Act", rules_only) == []


def test_section_and_rule_with_the_same_number_are_told_apart(context):
    diac = f"[Source: {DIAC} | Rule 11]\n11.1 The Centre shall fix the administrative fees payable by the parties."
    provisions = rag_provisions.provision_map(f"{context}\n\n{diac}")
    assert not _kept("The Centre shall fix the administrative fees payable by the parties (Section 11).", provisions)
    assert _kept("The Centre shall fix the administrative fees payable by the parties (Rule 11).", provisions)


def test_rule_clauses_behave_as_before():
    provisions = rag_provisions.provision_map(
        f"[Source: {DIAC} | Rule 4]\n4. Costs (i) The deposits shall be shared equally by the parties. "
        "(ii) The Centre may direct a separate deposit.")
    assert answer_guard._attribution_refs("(Rule 4(ii))", provisions) == ["4"]
    assert _kept("The deposits shall be shared equally by the parties (Rule 4(i)).", provisions)


def test_hindi_answers_must_cite_a_sub_section_that_was_retrieved(provisions, context):
    evidence = context
    assert answer_guard._provision_grounded("धारा 11(6) के अनुसार पक्षकार न्यायालय से अनुरोध कर सकता है।", evidence, provisions)
    assert answer_guard._provision_grounded("धारा 11(1) के अनुसार पक्षकार न्यायालय से अनुरोध कर सकता है।", evidence, provisions)  # exists
    assert answer_guard._provision_grounded("धारा 11(15) के अनुसार पक्षकार न्यायालय से अनुरोध कर सकता है।", evidence, provisions) is None


def test_citations_show_the_verified_sub_section(context):
    answer = f"Under the Act, {S11_6} (Section 11(6))."
    cites = llm_service.build_citations(answer, context, [ACT])
    assert [(c["rules"], c.get("rule_labels")) for c in cites] == [(["11"], ["11(6)"])]


def test_an_inline_mention_is_content_not_the_citation(provisions):
    # Seen in the eval: "under Section 23(4)" and "under Section 33" were taken for citations, and
    # neither was retrieved, so true sentences citing 29A(1) and 34(3) were dropped.
    assert answer_guard._attribution_refs(
        "within twelve months from the completion of pleadings under Section 23(4) (Section 29A(1)).", provisions) == [
        "section 29A(1)"]
    assert answer_guard._attribution_refs("an application under Section 9 is not entertained.", provisions) == []
    assert _kept("An application for setting aside may not be made after three months have elapsed from the date on "
                 "which the party making that application had received the arbitral award or, if a request had been "
                 "made under section 33, from the date on which that request had been disposed of (Section 34(3)).",
                 provisions)


def test_a_sub_section_marker_after_page_margin_letters_is_found():
    # The retrieved Act text, as the KB returned it: margin letters run into the line before "[(2)".
    text = ("9. Interim measures.—1[(1)] A party may apply to a court. and the Court shall have the same power "
            "aC [(2) Where, before the commencement of the arbitral proceedings, a Court passes an order, the "
            "arbitral proceedings shall be commenced within a period of ninety days. In\n\n"
            "(3) Once the arbitral tribunal has been constituted, the Court shall not entertain an application.")
    assert [label for label, _ in rag_provisions.sub_sections(text)] == ["(1)", "(2)", "(3)"]


def test_a_sub_section_hidden_by_the_layout_falls_back_to_the_whole_section():
    provisions = {"section 9": "whole text with ninety days", "section 9(1)": "one", "section 9(3)": "three"}
    assert answer_guard._provision_text("section 9(2)", provisions) == "whole text with ninety days"
    assert answer_guard._provision_text("section 9(4)", provisions) is None  # past the last one found: not retrieved


def test_who_does_what_reads_past_a_comma_phrase_and_skips_an_actor_after_of():
    rule = ("A party may, during the arbitral proceedings or at any time after the making of the arbitral award but "
            "before it is enforced in accordance with section 36, apply to the arbitral tribunal for an interim measure.")
    assert ("party", "apply") in answer_guard._actor_actions(rule, coordinated=True)
    claim = ("A party that needs measures that cannot await the constitution of an arbitral tribunal may submit an "
             "application.")
    assert ("tribunal", "submi") not in answer_guard._actor_actions(claim)
