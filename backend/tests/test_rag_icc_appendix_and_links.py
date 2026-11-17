"""ICC appendix labels, Article 31 first, DIAC Rule 8.6's proviso, and
official source links. Provision text comes from the approved PDFs in
backend/ai_knowledge via pdftotext (git-ignored, so skipped where absent)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import kb_registry
import llm_service
import prompt_builder
import rag_provisions

KNOWLEDGE = Path(__file__).resolve().parents[1] / "ai_knowledge"
ICC = "ICC_2026-Arbitration-Rules_2014-Mediation-Rules.pdf"
DIAC = "DIAC Rules conclusive_UsingOCR.pdf"
APPENDIX_IV = "ICC Arbitration Rules 2026, Appendix IV - Emergency Arbitrator Provisions"


def _store_text(filename):
    """The PDF as the vector store hands it over: pages behind page markers,
    normalized like approved_document_text, plus the page index."""
    path = KNOWLEDGE / filename
    if not shutil.which("pdftotext") or not path.exists():
        pytest.skip(f"needs pdftotext and {filename}")
    out = subprocess.run(["pdftotext", "-enc", "UTF-8", str(path), "-"], capture_output=True, check=True)
    pages = out.stdout.decode("utf-8").split("\f")
    raw = "".join(f"<PARSED TEXT FOR PAGE: {i} / {len(pages)}>\n{p}\n" for i, p in enumerate(pages, 1))
    norm = llm_service._readable_excerpt
    text = norm(rag_provisions.PAGE_MARKER_RE.sub("\n", raw))
    return text, rag_provisions._index_pages(raw, text, norm)


def _labels(blocks):
    return [b.split("\n", 1)[0] for b in blocks]


def _block_with(blocks, phrase):
    return next(b.split("\n", 1)[0] for b in blocks if phrase in b)


def test_emergency_arbitrator_question_brings_article_31_first_then_appendix_iv():
    text, pages = _store_text(ICC)
    blocks = rag_provisions.expand_chunks(ICC, [], text, "ICC emergency arbitrator procedure", pages)
    labels = _labels(blocks)
    assert labels[0] == f"[Source: {ICC} | Article 31 | ICC Arbitration Rules 2026]"
    assert "submit an application pursuant to the Emergency Arbitrator Provisions in Appendix IV" in blocks[0]
    assert labels[1:] and all(label.endswith(f"| {APPENDIX_IV}]") for label in labels[1:])


def test_appendix_iv_articles_keep_their_own_numbers_and_set():
    text, pages = _store_text(ICC)
    query = "ICC emergency arbitrator preliminary order and what if the fees are not paid"
    blocks = rag_provisions.expand_chunks(ICC, [], text, query, pages)
    preliminary = _block_with(blocks, "request a preliminary order directing another party not to frustrate")
    unpaid = _block_with(blocks, "the emergency arbitrator will not be appointed, and the Application will not be notified")
    assert preliminary == f"[Source: {ICC} | Article 7 | {APPENDIX_IV}]"
    assert unpaid == f"[Source: {ICC} | Article 8 | {APPENDIX_IV}]"


def test_citations_name_appendix_articles_and_main_articles_apart():
    text, pages = _store_text(ICC)
    context = "\n\n".join(dict.fromkeys(
        rag_provisions.expand_chunks(ICC, [], text, "ICC emergency arbitrator procedure", pages)
        + rag_provisions.expand_chunks(ICC, [], text, "ICC emergency arbitrator preliminary order", pages)))
    answer = ("A party applies under Article 31 for Emergency Measures. It may ask for a Preliminary Order "
              "(Appendix IV, Article 7) and must pay the fees (Article 8 of Appendix IV).")
    citations = {c["title"]: c for c in llm_service.build_citations(answer, context, [ICC])}
    assert citations["ICC Arbitration Rules 2026"]["rules"] == ["31"]
    assert citations["ICC Arbitration Rules 2026"]["label"] == "Article"
    assert citations[APPENDIX_IV]["rules"] == ["7", "8"]
    assert citations[APPENDIX_IV]["label"] == "Appendix IV, Article"


def test_diac_rule_8_6_keeps_its_international_arbitration_proviso():
    text, pages = _store_text(DIAC)
    blocks = rag_provisions.expand_chunks(DIAC, [], text, "Rule 8.6", pages)
    block = next(b for b in blocks if b.startswith(f"[Source: {DIAC} | Rule 8.6 "))
    assert "Provided that in a case of an International Arbitration" in block
    provisions = rag_provisions.provision_map("\n\n".join(blocks))
    point = {"title": "Default appointment", "text": "The Chairperson appoints within 21 days (Rule 8.6).",
             "icon": "rule", "badge": None, "tone": "neutral", "cite": [1]}
    assert llm_service._missing_provisos([point], provisions) == ["8.6"]
    with_proviso = {**point, "text": point["text"] + " Provided that in an international arbitration the "
                    "Presiding Arbitrator may be of another nationality."}
    assert llm_service._missing_provisos([with_proviso], provisions) == []
    assert "proviso" in prompt_builder.MODE_INSTRUCTIONS["lawyer"]


def test_official_url_is_per_record_https_and_never_our_r2_copy(monkeypatch):
    recs = [{"title": "ICC Arbitration Rules", "document_version": "2026", "official_url": "https://iccwbo.org/rules.pdf"},
            {"title": "ICC Mediation Rules", "document_version": "2014",
             "official_url": "https://pub-123.r2.dev/Arbitration/ICC.pdf"}]
    monkeypatch.setattr(kb_registry, "records_for_file", lambda f: recs)
    assert kb_registry.official_url(ICC, APPENDIX_IV) == "https://iccwbo.org/rules.pdf"
    assert kb_registry.official_url(ICC, "ICC Mediation Rules 2014") is None  # R2 copy
    assert kb_registry.official_url(ICC) is None  # two sets, none named


def test_every_record_has_an_official_url_field_and_none_points_at_r2():
    path = Path(kb_registry.__file__).resolve().parent / "kb" / "arbitration_kb_metadata.json"
    for rec in json.loads(path.read_text(encoding="utf-8")):
        assert "official_url" in rec, rec["doc_id"]
        assert not kb_registry._R2_HOST_RE.match(rec["official_url"] or ""), rec["doc_id"]
