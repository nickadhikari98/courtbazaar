"""Instant Legal Help — web-search citations for general legal questions.

A general legal question can be answered with OpenAI web search limited to
official sites (llm_service.generate_web_answer). Its citations come only from
the response's url_citation annotations: each becomes a "[n]" marker in the
reply and a {"kind": "web", ...} entry in `citations`. Nothing is taken from
text the model wrote. Document (DIAC/SOP) answers never use web search.

The OpenAI client and the model are mocked; the annotation shape below is
the one a live gpt-5-mini web_search response returned (2026-10-17).
"""
import asyncio
import os
import sys
from types import SimpleNamespace

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_chat  # noqa: E402
import llm_service  # noqa: E402

INDIA_CODE = "https://www.indiacode.nic.in/handle/123456789/20099"
SCI = "https://www.sci.gov.in/judgements"


def _ann(text, span, url, title="Page title", kind="url_citation"):
    start = text.index(span)
    return {"type": kind, "start_index": start, "end_index": start + len(span), "url": url, "title": title}


def _link(url, label="indiacode.nic.in"):
    return f"([{label}]({url}?utm_source=openai))"


def _apply(text, annotations):
    numbers = {}
    out = llm_service._apply_url_citations(text, annotations, numbers)
    return out, sorted(numbers.values(), key=lambda c: c["index"])


# ---------------------------------------------------------------------------
# Annotation -> marker + source
# ---------------------------------------------------------------------------

def test_an_inline_link_annotation_becomes_a_marker_and_a_verified_source():
    link = _link(INDIA_CODE)
    text = f"Anticipatory bail is covered by Section 482 of the BNSS. {link}\n\nAsk an advocate."
    out, cites = _apply(text, [_ann(text, link, INDIA_CODE + "?utm_source=openai", "Bharatiya Nagarik Suraksha Sanhita")])
    assert out == "Anticipatory bail is covered by Section 482 of the BNSS [1].\n\nAsk an advocate."
    assert cites == [{"kind": "web", "index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita",
                      "url": INDIA_CODE, "domain": "www.indiacode.nic.in"}]


def test_repeated_and_multiple_sources_share_numbers_by_url():
    a, b, c = _link(INDIA_CODE), _link(SCI, "sci.gov.in"), _link(INDIA_CODE + "#x", "again")
    text = f"First claim. {a} Second claim. {b} Third claim. {c}"
    anns = [_ann(text, a, INDIA_CODE), _ann(text, b, SCI), _ann(text, c, INDIA_CODE)]
    out, cites = _apply(text, anns)
    assert out == "First claim [1]. Second claim [2]. Third claim [1]."
    assert [(x["index"], x["url"]) for x in cites] == [(1, INDIA_CODE), (2, SCI)]


def test_a_span_that_is_answer_text_is_kept_with_the_marker_after_it():
    text = "Bail is a right in bailable offences and the rest stays."
    out, cites = _apply(text, [_ann(text, "Bail is a right in bailable offences", INDIA_CODE)])
    assert out == "Bail is a right in bailable offences [1] and the rest stays."
    assert len(cites) == 1


def test_missing_title_falls_back_to_the_domain():
    link = _link(SCI)
    text = f"Claim. {link}"
    _, cites = _apply(text, [_ann(text, link, SCI, title="   ")])
    assert cites[0]["title"] == "www.sci.gov.in"


def test_unofficial_insecure_or_malformed_annotations_never_become_citations():
    link = _link("https://lawblog.example.com/bail", "lawblog")
    text = f"Claim one. {link} Claim two. Claim three."
    bad = [
        _ann(text, link, "https://lawblog.example.com/bail"),                       # not an official domain
        _ann(text, "Claim two", "http://www.sci.gov.in/x"),                          # not https
        _ann(text, "Claim two", "https://sci.gov.in.evil.com/x"),                    # lookalike host
        _ann(text, "Claim two", "javascript:alert(1)"),
        _ann(text, "Claim two", None),
        _ann(text, "Claim two", SCI, kind="file_citation"),                          # wrong type
        {"type": "url_citation", "start_index": 5, "end_index": 999, "url": SCI},    # out of range
        {"type": "url_citation", "start_index": True, "end_index": 3, "url": SCI},   # bool index
        {"type": "url_citation", "start_index": "1", "end_index": "3", "url": SCI},  # string index
        "not an annotation",
    ]
    out, cites = _apply(text, bad)
    assert cites == []
    assert "[" not in out and "lawblog" not in out  # the unapproved link is dropped, not shown as text
    assert "Claim one." in out and "Claim three." in out


def test_numbers_the_model_typed_itself_can_never_pose_as_citations():
    link = _link(INDIA_CODE)
    text = f"See [1] and [2] in the text. Real claim. {link}"
    out, cites = _apply(text, [_ann(text, link, INDIA_CODE)])
    assert out == "See (1) and (2) in the text. Real claim [1]."
    assert len(cites) == 1


def test_overlapping_annotations_keep_only_the_first():
    link = _link(INDIA_CODE)
    text = f"Claim. {link}"
    start = text.index(link)
    out, cites = _apply(text, [_ann(text, link, INDIA_CODE),
                               {"type": "url_citation", "start_index": start + 2, "end_index": len(text), "url": SCI}])
    assert out == "Claim [1]."
    assert [c["url"] for c in cites] == [INDIA_CODE]


def test_finalize_drops_sources_whose_marker_was_removed_and_renumbers():
    cites = [{"kind": "web", "index": i, "title": f"T{i}", "url": f"https://x{i}.gov.in/", "domain": f"x{i}.gov.in"}
             for i in (1, 2, 3)]
    reply, kept = llm_service.finalize_web_citations("Kept claim [3]. Another [1]. Again [3]. Stray [9].", cites)
    assert reply == "Kept claim [1]. Another [2]. Again [1]. Stray [9]."
    assert [(c["index"], c["title"]) for c in kept] == [(1, "T3"), (2, "T1")]


# ---------------------------------------------------------------------------
# generate_web_answer against a mocked OpenAI client
# ---------------------------------------------------------------------------

def _response(text, annotations):
    part = SimpleNamespace(type="output_text", text=text,
                           annotations=[SimpleNamespace(**a) for a in annotations])
    return SimpleNamespace(output=[SimpleNamespace(type="web_search_call"),
                                   SimpleNamespace(type="message", content=[part])])


def _fake_client(monkeypatch, response=None, error=None):
    seen = {}

    async def create(**kwargs):
        seen.update(kwargs)
        if error:
            raise error
        return response

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr(llm_service, "_get_retrieval_client", lambda: client)
    return seen


def test_web_answer_searches_only_official_domains_and_returns_annotated_citations(monkeypatch):
    link = _link(INDIA_CODE)
    text = f"Section 482 of the BNSS covers anticipatory bail. {link}"
    seen = _fake_client(monkeypatch, _response(text, [_ann(text, link, INDIA_CODE, "BNSS 2023")]))
    result = asyncio.run(llm_service.generate_web_answer(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}]))
    assert seen["tools"] == [{"type": "web_search", "filters": {"allowed_domains": ["gov.in", "nic.in"]}}]
    assert seen["instructions"] == "sys"
    assert result["ok"] and result["text"] == "Section 482 of the BNSS covers anticipatory bail [1]."
    assert result["web_citations"][0]["url"] == INDIA_CODE


def test_web_answer_failure_is_reported_not_raised(monkeypatch):
    _fake_client(monkeypatch, error=RuntimeError("boom"))
    result = asyncio.run(llm_service.generate_web_answer([{"role": "user", "content": "q"}]))
    assert not result["ok"] and result["stage"] == "web search"


def test_web_answer_with_no_text_is_a_failure(monkeypatch):
    _fake_client(monkeypatch, SimpleNamespace(output=[]))
    result = asyncio.run(llm_service.generate_web_answer([{"role": "user", "content": "q"}]))
    assert not result["ok"]


# ---------------------------------------------------------------------------
# ai_chat orchestration
# ---------------------------------------------------------------------------

def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _ask(message):
    async def body():
        db = _db()
        return await ai_chat.handle_chat_message(db, None, message, None, client_ip="127.0.0.1")
    return asyncio.run(body())


def _models(monkeypatch, web_result, enabled=True):
    calls = {"web": [], "plain": []}

    results = list(web_result) if isinstance(web_result, list) else None

    async def fake_web(messages):
        calls["web"].append(messages)
        return results.pop(0) if results is not None else web_result

    async def fake_generate(messages, use_file_search=False, selected_source=None, on_status=None):
        calls["plain"].append((messages, use_file_search))
        return {"ok": True, "text": "Bail lets an accused person be released while the case continues.", "sources": []}

    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "web_search_enabled", lambda: enabled)
    monkeypatch.setattr(llm_service, "generate_web_answer", fake_web)
    monkeypatch.setattr(llm_service, "generate_response", fake_generate)
    return calls


def _web_ok(text, citations):
    return {"ok": True, "text": text, "sources": [], "web_citations": citations}


WEB_CITE = {"kind": "web", "index": 1, "title": "BNSS 2023", "url": INDIA_CODE, "domain": "www.indiacode.nic.in"}


def test_general_legal_question_gets_web_citations_and_the_web_route_note(monkeypatch):
    calls = _models(monkeypatch, _web_ok("Anticipatory bail is bail granted before an arrest [1].", [WEB_CITE]))
    result = _ask("What is anticipatory bail?")
    assert calls["plain"] == []
    notes = [m["content"] for m in calls["web"][0] if m["role"] == "system"]
    assert ai_chat.WEB_SEARCH_LEGAL_NOTE in notes
    assert ai_chat._ROUTE_NOTES[ai_chat.ROUTE_GENERAL_LEGAL] not in notes
    assert "[1]" in result["reply"]
    assert result["citations"] == [WEB_CITE]


def test_a_sentence_removed_by_the_guards_takes_its_citation_with_it(monkeypatch):
    sci = {**WEB_CITE, "index": 2, "url": SCI, "title": "Judgment", "domain": "www.sci.gov.in"}
    _models(monkeypatch, _web_ok(
        "Anticipatory bail is bail granted before an arrest [1]. "
        'The court said "liberty is the most precious of all the rights a person can have under law" [2].',
        [WEB_CITE, sci]))
    result = _ask("What is anticipatory bail?")
    assert "precious" not in result["reply"] and "[2]" not in result["reply"]
    assert [c["url"] for c in result["citations"]] == [INDIA_CODE]


def test_a_case_name_is_kept_only_with_a_verified_official_citation(monkeypatch):
    sci = {**WEB_CITE, "index": 1, "url": SCI, "title": "Judgment", "domain": "www.sci.gov.in"}
    _models(monkeypatch, _web_ok(
        "The Supreme Court set out the principles in Gurbaksh Singh Sibbia v. State of Punjab [1]. "
        "It was later applied in Siddharam Satlingappa Mhetre v. State of Maharashtra.", [sci]))
    result = _ask("Which Supreme Court judgment explains anticipatory bail?")
    assert "Sibbia" in result["reply"] and "[1]" in result["reply"]
    assert "Mhetre" not in result["reply"]  # named without an official source: removed
    assert [c["url"] for c in result["citations"]] == [SCI]


def test_web_search_failure_falls_back_to_the_plain_answer_without_citations(monkeypatch):
    calls = _models(monkeypatch, {"ok": False, "error_code": llm_service.ERR_TIMEOUT, "stage": "web search"})
    result = _ask("What is anticipatory bail?")
    assert len(calls["plain"]) == 1
    assert ai_chat._ROUTE_NOTES[ai_chat.ROUTE_GENERAL_LEGAL] in [m["content"] for m in calls["plain"][0][0]]
    assert "Bail lets" in result["reply"] and result["citations"] == []


def test_web_answer_without_annotations_shows_no_sources(monkeypatch):
    _models(monkeypatch, _web_ok("Anticipatory bail is bail granted before an arrest.", []))
    result = _ask("What is anticipatory bail?")
    assert result["citations"] == [] and "[" not in result["reply"]


def test_disabled_web_search_is_never_called(monkeypatch):
    calls = _models(monkeypatch, _web_ok("x [1].", [WEB_CITE]), enabled=False)
    _ask("What is anticipatory bail?")
    assert calls["web"] == [] and len(calls["plain"]) == 1


def test_document_questions_never_use_web_search(monkeypatch):
    calls = _models(monkeypatch, _web_ok("x [1].", [WEB_CITE]))
    _ask("What do the DIAC rules say about appointment of arbitrators?")
    assert calls["web"] == []
    assert calls["plain"][0][1] is True  # answered from the document


def test_web_search_is_off_by_default():
    assert llm_service.AI_WEB_SEARCH_ENABLED is (os.environ.get("AI_WEB_SEARCH_ENABLED", "").lower() in ("1", "true", "yes"))


# ---------------------------------------------------------------------------
# Bounded retry and the no-judgment fallback
# ---------------------------------------------------------------------------

SEARCH_META_ANSWER = (
    "I couldn't verify an official Supreme Court judgment on this point from the government/court domains "
    "(gov.in or nic.in) with the search tool just now. I can:\n"
    "- try another search restricted to official domains and return the judgment, summary and official link; or\n"
    "- search more broadly (including leading law-reporting sites) if you want faster results.\n"
    "Which do you prefer?"
)
JUDGMENT_Q = "Which Supreme Court judgment explains the conditions for granting anticipatory bail?"
SCI_CITE = {"kind": "web", "index": 1, "title": "Gurbaksh Singh Sibbia v. State of Punjab", "url": SCI,
            "domain": "www.sci.gov.in"}


def test_a_first_search_with_no_official_source_is_retried_once_with_new_terms(monkeypatch):
    calls = _models(monkeypatch, [
        _web_ok("Anticipatory bail protects a person from arrest.", []),
        _web_ok("The principles were laid down in Gurbaksh Singh Sibbia v. State of Punjab, decided on "
                "9 April 1980 [1]. Courts weigh the nature of the accusation and the risk of the applicant "
                "fleeing [1].", [SCI_CITE]),
    ])
    result = _ask(JUDGMENT_Q)
    assert len(calls["web"]) == 2 and calls["plain"] == []
    first = [m["content"] for m in calls["web"][0]]
    retry = [m["content"] for m in calls["web"][1]]
    assert ai_chat.WEB_SEARCH_RETRY_NOTE not in first and ai_chat.WEB_SEARCH_RETRY_NOTE in retry
    assert retry[-1] == JUDGMENT_Q  # the question stays last
    assert "Sibbia" in result["reply"] and "9 April 1980" in result["reply"]
    assert result["citations"] == [SCI_CITE]


def test_both_searches_without_an_official_source_give_the_concise_fallback(monkeypatch):
    calls = _models(monkeypatch, [_web_ok("Bail is granted in some cases.", []),
                                  _web_ok("Courts consider several factors.", [])])
    result = _ask(JUDGMENT_Q)
    assert len(calls["web"]) == 2 and calls["plain"] == []
    assert result["reply"] == ai_chat.WEB_NO_JUDGMENT_MESSAGE.format(court="Supreme Court")
    assert result["citations"] == []


def test_a_search_error_is_not_retried_and_a_judgment_request_gets_the_fallback(monkeypatch):
    calls = _models(monkeypatch, {"ok": False, "error_code": llm_service.ERR_TIMEOUT, "stage": "web search"})
    result = _ask("Is there a High Court ruling on this?")
    assert len(calls["web"]) == 1 and calls["plain"] == []
    assert result["reply"] == ai_chat.WEB_NO_JUDGMENT_MESSAGE.format(court="court")
    assert result["citations"] == []


def test_search_strategy_options_never_reach_the_user():
    stripped = ai_chat.answer_guard.strip_search_meta(SEARCH_META_ANSWER)
    assert stripped == ""


def test_an_answer_that_was_only_search_options_is_retried_then_falls_back(monkeypatch):
    seen = _fake_client(monkeypatch, _response(SEARCH_META_ANSWER, []))
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "web_search_enabled", lambda: True)

    async def no_plain(*a, **k):
        raise AssertionError("a judgment request must not fall back to an unsourced answer")
    monkeypatch.setattr(llm_service, "generate_response", no_plain)
    result = _ask(JUDGMENT_Q)
    for phrase in ("I can", "search more broadly", "Which do you prefer", "gov.in or nic.in", "search tool"):
        assert phrase not in result["reply"]
    assert result["reply"] == ai_chat.WEB_NO_JUDGMENT_MESSAGE.format(court="Supreme Court")
    assert seen["tools"][0]["filters"]["allowed_domains"] == ["gov.in", "nic.in"]  # never widened


def test_search_options_are_removed_but_the_real_answer_and_official_sites_stay():
    text = ("Anticipatory bail is sought before arrest [1]. The Act is on India Code at indiacode.nic.in [1].\n\n"
            "Would you like me to fetch the full judgment?")
    out = ai_chat.answer_guard.strip_search_meta(text)
    assert out == "Anticipatory bail is sought before arrest [1]. The Act is on India Code at indiacode.nic.in [1]."


def test_a_retry_that_cites_an_unofficial_site_still_counts_as_no_source(monkeypatch):
    link = "([lawblog](https://lawblog.example.com/sibbia))"
    text = f"The principles were laid down in Gurbaksh Singh Sibbia v. State of Punjab. {link}"
    _fake_client(monkeypatch, _response(text, [_ann(text, link, "https://lawblog.example.com/sibbia")]))
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "web_search_enabled", lambda: True)
    result = _ask(JUDGMENT_Q)
    assert "lawblog" not in result["reply"] and "Sibbia" not in result["reply"]
    assert result["citations"] == []
    assert result["reply"] == ai_chat.WEB_NO_JUDGMENT_MESSAGE.format(court="Supreme Court")
