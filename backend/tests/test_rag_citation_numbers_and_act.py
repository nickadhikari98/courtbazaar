"""Citation numbers survive whole (29A, 9B, 9.8, 33.1, 3(i)), every source of
a multi-source answer keeps its own, each file gets its share of the context,
and the 2026 Act's sections parse past its page footnotes. Act text comes from
the approved PDF in backend/ai_knowledge via pdftotext (skipped where absent)."""
import llm_service
import rag_provisions
from tests.test_rag_schedules_and_annexes import _store_text

ACT = "Arbitration-And-Conciliation-Act-1996-as-on-2026-06-01.pdf"
LCIA = "LCIA Rules Effective 1 Oct 2020 With Schedule of Costs 1 Dec 2023.pdf"
MCIA = "MCIA-Rules-2025.pdf"
DIAC = "DIAC Rules conclusive_UsingOCR.pdf"


def _block(filename, label, text):
    return f"[Source: {filename} | {label}]\n{text}"


def _rules(citations):
    return {c["document"]: c.get("rule_labels") or c["rules"] for c in citations}


def test_lettered_and_sub_numbered_provisions_are_cited_whole():
    context = "\n\n".join([
        _block(ACT, "Section 29A", "29A. Time limit for arbitral award.—(1) The award ... within twelve months."),
        _block(LCIA, "Article 9B", "Article 9B Emergency Arbitrator"),
        _block(LCIA, "Article 9.8", "9.8 The Emergency Arbitrator shall decide ... no later than 14 days."),
        _block(DIAC, "Rule 33.1", "33.1 The Centre shall fix the deposits."),
        _block(DIAC, "Rule 3", "3. Arbitrator's Fee (i) The fees payable to the Arbitrators shall be determined."),
    ])
    cases = [
        ([ACT], "The award must be made within twelve months (Section 29A(1))."),
        ([LCIA], "Article 9B lets a party apply; the decision is due within 14 days (Article 9.8)."),
        ([DIAC], "The Centre fixes the deposits (Rule 33.1) and the fee is set under Rule 3(i)."),
    ]
    got = {}
    for sources, answer in cases:
        got.update(_rules(llm_service.build_citations(answer, context, sources)))
    labels = {s: llm_service.KB_SOURCE_DISPLAY[s]["label"] for s in (ACT, LCIA, DIAC)}
    assert got[labels[ACT]] == ["29A"]
    assert set(got[labels[LCIA]]) == {"9B", "9.8"}
    assert set(got[labels[DIAC]]) == {"3(i)", "33.1"}


def test_each_source_in_a_comparison_keeps_its_own_number():
    context = "\n\n".join([
        _block(MCIA, "Rule 19.6", "19.6 The Emergency Arbitrator shall decide ... no later than 14 days."),
        _block(LCIA, "Article 9.8", "9.8 The Emergency Arbitrator shall decide ... no later than 14 days."),
    ])
    answer = "Under MCIA the deadline is 14 days (Rule 19.6); under LCIA it is also 14 days (Article 9.8)."
    got = _rules(llm_service.build_citations(answer, context, [MCIA, LCIA]))
    assert got[llm_service.KB_SOURCE_DISPLAY[MCIA]["label"]] == ["19.6"]
    assert got[llm_service.KB_SOURCE_DISPLAY[LCIA]["label"]] == ["9.8"]


def test_two_files_split_the_block_budget_so_the_second_is_not_crowded_out():
    doc = "\n".join(f"{n}. Heading {n}\n{n}.1 The Emergency Arbitrator rule {n} text." for n in range(1, 30))
    blocks = rag_provisions.expand_chunks(MCIA, [], doc, "emergency arbitrator rule", None, share=2)
    assert 0 < len(blocks) <= rag_provisions.MAX_BLOCKS // 2


def test_act_sections_parse_past_page_footnotes_and_bracketed_insertions():
    text, _ = _store_text(ACT)
    body = {}
    for p in rag_provisions.parse_provisions(text):
        if p["text"].startswith(f"{p['number']}. ") and ".—" in p["text"][:120]:
            body.setdefault(p["number"], p["text"])  # "34. Application for setting aside arbitral award.—(1) ..."
    assert {"11A", "17", "29A", "34", "36"} <= set(body)
    assert "three months have elapsed" in body["34"]
    assert not any(p["text"].startswith(("1. Subs. by", "2. Ins. by")) for p in rag_provisions.parse_provisions(text))


def test_a_long_top_ranked_section_is_not_the_one_the_character_cap_cuts():
    text, pages = _store_text(ACT)
    query = "Within what time must an application to set aside an arbitral award be made?"
    blocks = rag_provisions.expand_chunks(ACT, [], text, query, pages)
    assert any("three months have elapsed" in b for b in blocks)
    assert sum(map(len, blocks)) <= rag_provisions.MAX_CONTEXT_CHARS
