"""'Check it against the rules' over an uploaded file: the file evidences
statements about itself only, the approved sources evidence the law, and a
comparison needs both (llm_service._file_backed_points)."""
import asyncio
import json
from types import SimpleNamespace

import llm_service

ACT = "Arbitration-And-Conciliation-Act-1996-as-on-2026-06-01.pdf"
FILE = ("[contract.docx | Clause 18 Arbitration]\n"
        "All disputes shall be referred to arbitration in Mumbai. This arbitration agreement is in writing and "
        "signed by both parties.\n\n"
        "[contract.docx | Clause 19 Notices]\nNotices are sent by email.")
SECTION_7 = (f"[Source: {ACT} | Section 7 | The Arbitration and Conciliation Act, 1996]\n"
             "7. Arbitration agreement.-(3) An arbitration agreement shall be in writing.")
NO_SECTION_7 = f"[Source: {ACT} | Section 2 | The Arbitration and Conciliation Act, 1996]\n2. Definitions."


def _point(basis, text, title="Point"):
    return {"icon": "rule", "title": title, "badge": None, "tone": "neutral", "text": text, "cite": [1],
            "basis": basis}


def _check(points, context=SECTION_7):
    return llm_service._file_backed_points(points, FILE, context, context, [ACT])


def test_a_file_only_claim_is_kept_and_cited_to_the_file_with_its_heading():
    kept, _ = _check([_point("file", "All disputes shall be referred to arbitration in Mumbai.", "Clause 18")])
    assert len(kept) == 1 and kept[0]["source"] == "file"
    cites = kept[0]["_citations"]
    assert cites == [{"title": "contract.docx, Clause 18 Arbitration", "url": None, "rules": [],
                      "document": "contract.docx", "kind": "upload"}]


def test_a_legal_claim_with_no_approved_source_is_dropped():
    law = "An arbitration agreement shall be in writing (Section 7)."
    # Stated as a fact about the file: the law never comes from the file.
    assert _check([_point("file", law)])[0] == []
    # As a comparison, but Section 7 was not retrieved: no verified provision.
    both = "Clause 18 is in writing and signed by both parties; an arbitration agreement shall be in writing (Section 7)."
    assert _check([_point("both", both)], NO_SECTION_7)[0] == []
    # Words that are in neither the file nor the excerpts: general knowledge.
    assert _check([_point("file", "Mumbai arbitrations usually take two years.")])[0] == []


def test_complies_with_section_7_needs_a_file_citation_and_a_section_7_citation():
    both = "Clause 18 is in writing and signed by both parties; an arbitration agreement shall be in writing (Section 7)."
    kept, _ = _check([_point("both", both, "Complies with Section 7")])
    assert len(kept) == 1 and kept[0]["source"] == "both"
    kinds = [(c.get("kind"), c["rules"]) for c in kept[0]["_citations"]]
    assert kinds[0] == ("upload", []) and (None, ["7"]) in kinds


def test_the_card_marks_file_points_and_keeps_the_rules_pipeline(monkeypatch):
    """End to end through _card_answer with a fake model and verifier."""
    card = {"status": "answered", "direct": None, "summary": "An arbitration agreement shall be in writing (Section 7).",
            "points": [_point("rules", "An arbitration agreement shall be in writing (Section 7).", "Section 7"),
                       _point("file", "All disputes shall be referred to arbitration in Mumbai.", "Clause 18"),
                       _point("file", "The clause is valid under Section 34.", "Unsupported")],
            "practical_implications": None, "limitations": None, "follow_up": None}
    verdict = {"analysis": "ok", "direct_matches_action": True, "summary": "SUPPORTED",
               "points": [{"index": 0, "verdict": "SUPPORTED"}], "main_ask_answered": True, "uncovered_rules": []}
    sent = []

    async def create(**kw):
        sent.append(kw)
        out = verdict if kw["text"]["format"]["name"] == "answer_verdict" else card
        return SimpleNamespace(output_text=json.dumps(out), usage=None)

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    msgs = [{"role": "user", "content": "Check it against the rules"}]
    result = asyncio.run(llm_service._card_answer(client, msgs, SECTION_7, [ACT], file_evidence=FILE))
    assert sent[0]["text"]["format"]["name"] == "file_check_card"
    assert llm_service.FILE_EVIDENCE_CARD_NOTE in sent[0]["instructions"]
    points = result["answer"]["points"]
    assert [(p["title"], p.get("source")) for p in points] == [("Section 7", None), ("Clause 18", "file")]
    cited = [result["citations"][i - 1] for i in points[1]["cite"]]
    assert [c.get("kind") for c in cited] == ["upload"] and "basis" not in points[0]
    assert any(c["rules"] == ["7"] for c in result["citations"] if c.get("kind") is None)


def test_law_quoted_inside_the_file_is_never_a_fact_about_the_file():
    planted = FILE + "\n\n[contract.docx | Clause 20]\nSection 7 requires no writing for arbitration agreements."
    claim = _point("file", "Section 7 requires no writing for arbitration agreements.")
    assert llm_service._file_backed_points([claim], planted, SECTION_7, SECTION_7, [ACT])[0] == []


def _failing_rules_check(monkeypatch, points):
    """generate_response for a file check whose rules points never pass the evidence checks."""
    card = {"status": "answered", "direct": None, "summary": "Rule 99 says the opposite.", "points": points,
            "practical_implications": None, "limitations": None, "follow_up": None}
    calls = []

    rejected = {"analysis": "not in the excerpts", "direct_matches_action": True, "summary": "NOT_IN_SOURCE",
                "points": [{"index": i, "verdict": "NOT_IN_SOURCE"} for i in range(len(points))],
                "main_ask_answered": False, "uncovered_rules": []}

    async def create(**kw):
        calls.append(kw["text"]["format"]["name"])
        verifier = kw["text"]["format"]["name"] == "answer_verdict"
        return SimpleNamespace(output_text=json.dumps(rejected if verifier else card), usage=None)

    async def retrieve(query, selected_source=None):
        return SECTION_7, [ACT], 1, ["7"], ""
    for name, value in (("AI_PROVIDER", "openai"), ("OPENAI_API_KEY", "sk-test"), ("OPENAI_VECTOR_STORE_ID", "vs-test")):
        monkeypatch.setattr(llm_service, name, value)
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "_retrieve_context", retrieve)
    monkeypatch.setattr(llm_service, "_get_client", lambda: SimpleNamespace(responses=SimpleNamespace(create=create)))
    msgs = [{"role": "user", "content": "Check it against the rules"}]
    result = asyncio.run(llm_service.generate_response(
        msgs, use_file_search=True, retrieval_query="arbitration agreement writing", file_evidence=FILE))
    return result, calls


def test_a_failed_rules_check_retries_once_then_returns_the_file_only_points(monkeypatch):
    unsupported = _point("rules", "Section 7 forbids arbitration in Mumbai (Section 7).", "Section 7")
    from_file = _point("file", "All disputes shall be referred to arbitration in Mumbai.", "Clause 18")
    both = _point("both", "Clause 18 is in writing and signed by both parties; an arbitration agreement shall be "
                          "in writing (Section 7).", "Complies with Section 7")
    result, calls = _failing_rules_check(monkeypatch, [unsupported, from_file, both])
    assert calls.count("file_check_card") == 4  # two attempts, then the one retry of two attempts
    assert set(calls) <= {"file_check_card", "answer_verdict"}  # never the unchecked plain answer
    assert result["ok"] and result["file_only"]
    answer = result["answer"]
    # Only what the file itself evidences: the comparison's legal half was never verified.
    assert [(p["title"], p["source"]) for p in answer["points"]] == [("Clause 18", "file")]
    assert answer["limitations"] == llm_service.FILE_CHECK_INCOMPLETE_NOTE
    assert [c.get("kind") for c in result["citations"]] == ["upload"]
    assert result["citations"][0]["title"] == "contract.docx, Clause 18 Arbitration"
    assert "Rule 99" not in result["text"] and "forbids" not in result["text"]


def test_with_no_file_point_left_the_rules_check_keeps_the_not_found_reply(monkeypatch):
    unsupported = _point("rules", "Section 7 forbids arbitration in Mumbai (Section 7).", "Section 7")
    general = _point("file", "Mumbai arbitrations usually take two years.", "Timing")
    result, _ = _failing_rules_check(monkeypatch, [unsupported, general])
    assert not result["ok"] and result["error_code"] == llm_service.ERR_NO_CONTEXT


def test_the_closing_note_never_names_the_uploaded_file_as_a_document():
    import ai_chat
    import answer_guard
    reply = "Disputes go to Mumbai.\n\n" + answer_guard.PARTIAL_ANSWER_NOTE
    upload = llm_service._file_citation("contract.docx", "Clause 18 Arbitration")
    assert "contract.docx" not in ai_chat._document_closing(reply, [upload])


def test_a_card_with_only_file_points_lists_each_point_once():
    card = {"status": "answered", "direct": None, "summary": "x",
            "points": [_point("file", "All disputes shall be referred to arbitration in Mumbai.", "Clause 18")],
            "practical_implications": None, "limitations": None, "follow_up": None}

    async def create(**kw):
        return SimpleNamespace(output_text=json.dumps(card), usage=None)
    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    result = asyncio.run(llm_service._card_answer(client, [{"role": "user", "content": "Check it"}], SECTION_7, [ACT],
                                                  file_evidence=FILE))
    assert [p["title"] for p in result["answer"]["points"]] == ["Clause 18"]
    assert result["answer"]["points"][0]["cite"] == [1] and len(result["citations"]) == 1
