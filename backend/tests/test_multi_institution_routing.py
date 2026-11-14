"""Multi-institution retrieval: detection, per-institution filters, lettered
provisions, ICC rule sets by page_range (2026-11-14)."""
import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_chat  # noqa: E402
import kb_registry  # noqa: E402
import llm_service  # noqa: E402
import rag_provisions  # noqa: E402

ICC = "ICC_2026-Arbitration-Rules_2014-Mediation-Rules.pdf"
SIAC = "SIAC-Rules-7th-Edition_260907.pdf"
ACT = "Arbitration-And-Conciliation-Act-1996.pdf"

ICC_DOC = (
    "<PARSED TEXT FOR PAGE: 1 / 106>\nARBITRATION RULES\n"
    "Article 1 International Court of Arbitration\nThe Court administers the resolution of disputes by arbitral tribunals.\n"
    "<PARSED TEXT FOR PAGE: 20 / 106>\n"
    "Article 9B Emergency Measures\nA party needing urgent interim measures may apply to an emergency arbitrator.\n"
    "<PARSED TEXT FOR PAGE: 87 / 106>\nMEDIATION RULES\n"
    "Article 1 Introductory Provisions\nThese Mediation Rules govern mediation administered by the Centre.\n"
)
ACT_DOC = (
    "11. Appointment of arbitrators.—(1) A person of any nationality may be an arbitrator.\n"
    "11A. Qualifications and experience of arbitrator.—(1) The Central Government may amend the Eighth Schedule.\n"
    "12. Grounds for challenge.—(1) When a person is approached for appointment.\n"
)


def _item(filename, text, file_id=None):
    return SimpleNamespace(filename=filename, file_id=file_id, score=0.9,
                           attributes={"source_id": llm_service.KB_SOURCE_METADATA[filename]["source_id"],
                                       "title": filename},
                           content=[SimpleNamespace(text=text)])


class _Pages:
    def __init__(self, text):
        self.text = text

    def __aiter__(self):
        async def gen():
            yield SimpleNamespace(text=self.text)
        return gen()


def _install(monkeypatch, items, docs=None):
    searches = []

    async def search(**kwargs):
        searches.append(kwargs)
        return SimpleNamespace(data=list(items))  # ignores the filter, like a store missing tags would

    async def content(file_id, vector_store_id):
        return _Pages((docs or {})[file_id])

    client = SimpleNamespace(vector_stores=SimpleNamespace(search=search, files=SimpleNamespace(content=content)))
    monkeypatch.setattr(llm_service, "OPENAI_API_KEY", "k")
    monkeypatch.setattr(llm_service, "OPENAI_VECTOR_STORE_ID", "vs")
    monkeypatch.setattr(llm_service, "_get_retrieval_client", lambda: client)
    rag_provisions.clear_cache()
    return searches


def test_detects_every_named_institution():
    assert kb_registry.detect_institutions("Compare ICC and SIAC on emergency arbitrators") == {"ICC", "SIAC"}
    assert kb_registry.detect_institutions("Under the Arbitration Act, Section 11A?") == {"ACT"}
    assert kb_registry.detect_institutions("What do the LCIA rules say on costs?") == {"LCIA"}
    assert kb_registry.detect_institutions("Who pays the court fee?") == set()


def test_two_institutions_route_to_rag_and_search_each_with_its_own_filter(monkeypatch):
    query = "Compare ICC and SIAC rules on emergency arbitrators"
    assert ai_chat.route_message(query)["route"] == ai_chat.ROUTE_DOCUMENT_RAG
    searches = _install(monkeypatch, [])
    asyncio.run(llm_service._retrieve_context(query, None))
    filters = [s["filters"] for s in searches if "filters" in s]  # empty results also trigger unfiltered diagnostics
    assert len(filters) == 2
    assert kb_registry.search_filter("ICC") in filters and kb_registry.search_filter("SIAC") in filters
    assert kb_registry.search_filter("ICC")["filters"][0]["key"] == "institution"  # bundled PDF: never doc_id
    assert kb_registry.search_filter("ACT")["filters"][0] == {"type": "eq", "key": "doc_id", "value": "act-ac-1996"}
    assert all(f["filters"][1] == {"type": "eq", "key": "status", "value": "in_force"} for f in filters)
    assert llm_service._search_text(query, None) == "Searching ICC Rules, SIAC Rules…"


def test_unnamed_arbitration_question_searches_act_and_all_institutions(monkeypatch):
    searches = _install(monkeypatch, [])
    asyncio.run(llm_service._retrieve_context("How is an arbitral tribunal constituted?", None))
    assert {str(s["filters"]) for s in searches if "filters" in s} == {str(kb_registry.search_filter(c)) for c in kb_registry.all_codes()}


def test_section_11a_and_article_9b_parse():
    assert [p["number"] for p in rag_provisions.parse_provisions(ACT_DOC)] == ["11", "11A", "12"]
    doc = "Article 9 Joinder\nText of nine.\nArticle 9A Consolidation\nText.\nArticle 9B Emergency Measures\nText.\nArticle 10 Multiple Parties\nText."
    assert [p["number"] for p in rag_provisions.parse_provisions(doc)] == ["9", "9A", "9B", "10"]
    blocks = rag_provisions.expand_chunks(ACT, [], ACT_DOC, "What does Section 11A require?")
    assert blocks[0].startswith(f"[Source: {ACT} | Section 11A | Arbitration and Conciliation Act, 1996]")


def test_icc_question_never_gets_siac_or_mediation_context(monkeypatch):
    items = [_item(SIAC, "SIAC Rule 12 emergency arbitrator text that must never appear here."),
             _item(ICC, "A party needing urgent interim measures may apply to an emergency arbitrator.", "f-icc"),
             _item(ICC, "These Mediation Rules govern mediation administered by the Centre.", "f-icc")]
    _install(monkeypatch, items, {"f-icc": ICC_DOC})
    context, sources, *_ = asyncio.run(llm_service._retrieve_context(
        "Under the ICC rules, what does Article 9B say about emergency measures?", None))
    assert sources == [ICC]
    assert "SIAC" not in context and "Mediation Rules govern" not in context
    assert context.startswith(f"[Source: {ICC} | Article 9B | ICC Arbitration Rules 2026]")


def test_bare_section_routes_to_the_act_but_rule_and_other_statutes_do_not():
    for q in ("What does Section 11 say?", "Grounds under Sec. 34?", "Timeline in S. 29A?"):
        decision = ai_chat.route_message(q)
        assert (decision["route"], decision["source"]) == (ai_chat.ROUTE_DOCUMENT_RAG, ACT), q
    assert ai_chat.route_message("What does Section 138 of the NI Act say?")["source"] != ACT
    assert llm_service.explicit_document_sources("What does Rule 14 say about deposits?") == []


def test_citations_go_under_each_provisions_own_source_including_lettered_refs():
    context = (
        f"[Source: {ICC} | Article 9B | ICC Arbitration Rules 2026]\nArticle 9B Emergency Measures\nA party may apply.\n\n"
        f"[Source: {SIAC} | Rule 12 | SIAC Arbitration Rules, 7th Edition]\n12. Emergency Arbitrator\nA party may apply.\n\n"
        f"[Source: {ACT} | Section 11A | Arbitration and Conciliation Act, 1996]\n11A. Qualifications of arbitrator.")
    answer = ("Under Article 9B a party may seek emergency measures; Rule 12 gives SIAC's emergency arbitrator; "
              "Section 11A of the Arbitration Act sets arbitrator qualifications.")
    cites = {c["document"]: c for c in llm_service.build_citations(answer, context, [ICC, SIAC, ACT])}
    by_doc = {doc: (c["title"], c["rules"]) for doc, c in cites.items()}
    assert by_doc[llm_service.KB_SOURCE_DISPLAY[ICC]["label"]] == ("ICC Arbitration Rules 2026", ["9B"])
    assert by_doc[llm_service.KB_SOURCE_DISPLAY[SIAC]["label"]][1] == ["12"]
    assert by_doc[llm_service.KB_SOURCE_DISPLAY[ACT]["label"]][1] == ["11A"]


def test_named_section_is_read_from_the_act_when_search_returned_no_act_chunk(monkeypatch):
    _install(monkeypatch, [], {"f-act": "<PARSED TEXT FOR PAGE: 5 / 46>\n" + ACT_DOC})

    def list_files(vector_store_id):
        async def gen():
            yield SimpleNamespace(id="f-act", attributes={"title": ACT})
        return gen()

    monkeypatch.setattr(llm_service, "_store_file_ids", {})
    monkeypatch.setattr(llm_service._get_retrieval_client().vector_stores.files, "list", list_files, raising=False)
    context, sources, *_ = asyncio.run(llm_service._retrieve_context("What does Section 11A say?", ACT))
    assert sources == [ACT]
    assert context.startswith(f"[Source: {ACT} | Section 11A |") and "Section 12 |" not in context


def test_unnamed_question_merged_context_is_capped_by_score(monkeypatch):
    files = [f for f in llm_service.APPROVED_KB_FILES if f not in (ICC, llm_service.SOURCE_SOP)]
    items = [SimpleNamespace(**{**vars(_item(files[i % len(files)], f"chunk{i} " + "tribunal powers " * 200)),
                                "score": 0.3 + i / 100}) for i in range(20)]
    searches = _install(monkeypatch, items)
    context, *_ = asyncio.run(llm_service._retrieve_context("How is an arbitral tribunal constituted?", None))
    assert {s["max_num_results"] for s in searches if "filters" in s} == {2}
    blocks = context.split("\n\n[Source: ")
    assert len(context) <= rag_provisions.MAX_CONTEXT_CHARS + 2 * len(blocks)
    assert len(blocks) <= rag_provisions.MAX_BLOCKS
    assert "chunk19 " in context and "chunk0 " not in context  # best score kept, worst dropped
