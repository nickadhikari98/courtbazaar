"""Schedules and appendices cited with their own numbering, found from each
document's own text: SIAC Schedules 1-3 ("Schedule 1, Paragraph 3"), ICC
Mediation's unnumbered Appendix, LCIA's two-column pages, running page
headers, and DIAC's bundled sets. Text comes from the approved PDFs in
backend/ai_knowledge via pdftotext (git-ignored, so skipped where absent)."""
import shutil
import subprocess
from pathlib import Path

import pytest

import llm_service
import rag_provisions

KNOWLEDGE = Path(__file__).resolve().parents[1] / "ai_knowledge"
SIAC = "SIAC-Rules-7th-Edition_260907.pdf"
LCIA = "LCIA Rules Effective 1 Oct 2020 With Schedule of Costs 1 Dec 2023.pdf"
ICC = "ICC_2026-Arbitration-Rules_2014-Mediation-Rules.pdf"
DIAC = "DIAC Rules conclusive_UsingOCR.pdf"
SCHEDULE_1 = "Schedule 1 - Emergency Arbitrator Procedure"


def _store_text(filename, *flags):
    """The PDF as the vector store hands it over (page markers, normalized),
    plus the page index. `-layout` keeps two-column pages side by side, the
    way the store's parser returns LCIA."""
    path = KNOWLEDGE / filename
    if not shutil.which("pdftotext") or not path.exists():
        pytest.skip(f"needs pdftotext and {filename}")
    out = subprocess.run(["pdftotext", "-enc", "UTF-8", *flags, str(path), "-"], capture_output=True, check=True)
    pages = out.stdout.decode("utf-8").split("\f")
    raw = "".join(f"<PARSED TEXT FOR PAGE: {i} / {len(pages)}>\n{p}\n" for i, p in enumerate(pages, 1))
    norm = llm_service._readable_excerpt
    text = norm(rag_provisions.PAGE_MARKER_RE.sub("\n", raw))
    return text, rag_provisions._index_pages(raw, text, norm)


def _label_of(blocks, phrase):
    return next(b.split("\n", 1)[0] for b in blocks if phrase in b)


def test_siac_schedule_paragraphs_keep_their_own_numbering_after_the_rule_that_brings_them_in():
    text, pages = _store_text(SIAC)
    blocks = rag_provisions.expand_chunks(SIAC, [], text, "SIAC emergency arbitrator application", pages)
    labels = [b.split("\n", 1)[0] for b in blocks]
    rule_12_1 = _label_of(blocks, "in accordance with the procedure set out in Schedule 1")
    assert rule_12_1.startswith(f"[Source: {SIAC} | Rule 12.1 | ") and "Schedule" not in rule_12_1
    assert labels.index(rule_12_1) < min(i for i, label in enumerate(labels) if SCHEDULE_1 in label)
    paragraph_1 = _label_of(blocks, "may file an application with the Registrar for the appointment of an Emergency")
    assert paragraph_1.startswith(f"[Source: {SIAC} | Paragraph 1 | ") and paragraph_1.endswith(f", {SCHEDULE_1}]")


def test_each_siac_schedule_is_its_own_set():
    text, _ = _store_text(SIAC)
    parts = {p["appendix"] for p in rag_provisions.parse_provisions(text) if p["appendix"]}
    assert {SCHEDULE_1, "Schedule 2 - Streamlined Procedure", "Schedule 3 - Expedited Procedure"} <= parts
    # "paragraph 7 of this Schedule 1": SIAC's own word for a schedule item; ICC says "Article 3 of this Appendix".
    assert rag_provisions.part_word(text, SCHEDULE_1, "Rule") == "Paragraph"
    icc, _ = _store_text(ICC)
    assert rag_provisions.part_word(icc, "Appendix IV - Emergency Arbitrator Provisions", "Article") == "Article"


def test_a_running_page_header_is_not_a_rule_heading():
    # "42 Arbitration Rules of the Singapore ... SIAC Rules" heads a page; read as
    # "Rule 42" it made Rules 38-41 look like numbering going backwards.
    text, pages = _store_text(SIAC)
    numbers = [p["number"] for p in rag_provisions.parse_provisions(text) if p["instrument"] == 1]
    assert {"38", "38.1", "39", "41", "46.1"} <= set(numbers)
    blocks = rag_provisions.expand_chunks(SIAC, [], text, "Must a party disclose third-party funding?", pages)
    assert _label_of(blocks, "shall disclose the existence of any third-party funding agreement").startswith(
        f"[Source: {SIAC} | Rule 38.1 | ")


def test_lcia_two_column_page_sub_articles_are_found_after_the_gutter():
    text, _ = _store_text(LCIA, "-layout")
    found = {p["number"]: p["text"] for p in rag_provisions.parse_provisions(text, "Article")}
    assert found["9.8"].startswith("9.8 The Emergency Arbitrator shall decide the claim for")
    assert found["16.2"].startswith("16.2 In default of any such agreement, the seat of the")
    # "... 9C, 10 and 16.2 (last sentence) shall apply" mid-sentence is not Article 16.2.
    assert not found["16.2"].startswith("16.2 (last")


def test_icc_mediation_unnumbered_appendix_is_its_own_set():
    text, _ = _store_text(ICC)
    filing_fee = next(p for p in rag_provisions.parse_provisions(text, "Article")
                      if p["text"].startswith("Article 1 Filing Fee Each Request pursuant to the Rules"))
    assert filing_fee["appendix"] == "Appendix - Fees and Costs"


def test_citations_name_schedule_paragraphs_and_main_rules_apart():
    text, pages = _store_text(SIAC)
    context = "\n\n".join(rag_provisions.expand_chunks(SIAC, [], text, "SIAC emergency arbitrator application", pages))
    answer = ("A party applies under Rule 12.1 for an Emergency Arbitrator, filing the application with the "
              "Registrar (Schedule 1, Paragraph 1).")
    citations = {c["label"]: c for c in llm_service.build_citations(answer, context, [SIAC])}
    assert citations["Rule"]["rules"] == ["12.1"]
    assert citations["Schedule 1, Paragraph"]["rules"] == ["1"]
    assert citations["Schedule 1, Paragraph"]["title"].endswith(f", {SCHEDULE_1}")


def test_diac_internal_management_rule_10_is_titled_with_its_own_set():
    # Internal Management Rules run to page 44; the Fee Rules start on page 45.
    text, pages = _store_text(DIAC)
    blocks = rag_provisions.expand_chunks(DIAC, [], text, "DIAC maintain a Panel of Arbitrators", pages)
    assert "(Internal Management) Rules" in _label_of(blocks, "The DIAC shall maintain a Panel of Arbitrators")
