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
    # FILE names a place (Mumbai) but no institution: that omission is found by searching the file.
    assert [(p["title"], p.get("source")) for p in points] == [
        ("Section 7", None), ("Clause 18", "file"), ("Clause 18 — institution", "file")]
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
    assert [(p["title"], p["source"]) for p in answer["points"]] == [("Clause 18", "file"),
                                                                    ("Clause 18 — institution", "file")]
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
    # FILE names no institution: that found omission follows the model's point; each listed once.
    assert [p["title"] for p in result["answer"]["points"]] == ["Clause 18", "Clause 18 — institution"]
    assert [p["cite"] for p in result["answer"]["points"]] == [[1], [1]] and len(result["citations"]) == 1


CONTRACT = ("[supply.docx | 1. Scope]\nThe Supplier shall supply packaging components as described in Schedule A.\n\n"
            "[supply.docx | 2. Delivery]\nDelivery shall be completed within 30 days of each purchase order.\n\n"
            "[supply.docx | 18. Arbitration]\nAny dispute arising out of or in connection with this Agreement shall be "
            "referred to arbitration. The arbitration shall be conducted by a sole arbitrator appointed mutually by "
            "the parties.")


def test_clause_n_is_the_files_own_when_the_file_numbers_a_heading_n():
    lower = CONTRACT.lower()
    assert llm_service._file_has_clause("Clause 18", lower) and llm_service._file_has_clause("Clause 1", lower)
    assert not llm_service._file_has_clause("Clause 99", lower) and not llm_service._file_has_clause("Clause 30", lower)
    point = _point("file", "Any dispute arising out of or in connection with this Agreement shall be referred to "
                           "arbitration (Clause 18).", "Clause 18 — Arbitration")
    kept, _ = llm_service._file_backed_points([point], CONTRACT, SECTION_7, SECTION_7, [ACT])
    assert [p["_citations"][0]["title"] for p in kept] == ["supply.docx, 18. Arbitration"]


def test_the_rules_search_uses_the_files_dispute_clause_not_its_opening():
    import chat_uploads
    query = chat_uploads.search_query(CONTRACT)
    assert query.startswith("Any dispute arising out of") and "packaging" not in query and "[supply" not in query
    assert chat_uploads.search_query("[a.docx | 1. Scope]\nPackaging only.").startswith("Packaging")  # nothing relevant: start


def test_a_retried_file_check_tells_the_user_why_it_is_slower(monkeypatch):
    statuses = []

    async def record(event):
        statuses.append(event["step"])
    unsupported = _point("rules", "Section 7 forbids arbitration in Mumbai (Section 7).", "Section 7")
    monkeypatch.setattr(llm_service, "emit_status", lambda on_status, step, text: record({"step": step, "text": text}))
    _failing_rules_check(monkeypatch, [unsupported])
    assert statuses.count("retrying") == 1


def test_a_claimed_absence_is_checked_by_searching_the_file():
    no_seat = _point("file", "Clause 18 names no seat and no institution.", "Clause 18 — seat")
    kept, _ = llm_service._file_backed_points([no_seat], CONTRACT, SECTION_7, SECTION_7, [ACT])
    assert [p["text"] for p in kept] == ["Clause 18 names no seat and no institution."]
    # Wrong when the file does name one: dropped.
    with_diac = CONTRACT + " The arbitration shall be held under the rules of DIAC."
    assert llm_service._file_backed_points([no_seat], with_diac, SECTION_7, SECTION_7, [ACT])[0] == []
    with_seat = CONTRACT + " The seat of arbitration is Mumbai."
    assert llm_service._file_backed_points([no_seat], with_seat, SECTION_7, SECTION_7, [ACT])[0] == []


def test_an_absence_is_cited_to_the_clause_it_names():
    no_seat = _point("file", "Clause 18 names no seat and no institution.", "Clause 18 — seat")
    kept, _ = llm_service._file_backed_points([no_seat], CONTRACT, SECTION_7, SECTION_7, [ACT])
    assert kept[0]["_citations"][0]["title"] == "supply.docx, 18. Arbitration"


COMPARISON = ("Any dispute arising out of or in connection with this Agreement shall be referred to arbitration, which is "
              "consistent with the requirement that an arbitration agreement shall be in writing (Section 7).")


def test_a_one_sentence_comparison_is_split_at_its_connective_and_cites_both():
    """Real model output: "[clause words], which is consistent with [Section 7]"."""
    halves = []
    kept, _ = llm_service._file_backed_points([_point("both", COMPARISON, "Clause 18 — Arbitration")],
                                              CONTRACT, SECTION_7, SECTION_7, [ACT], halves)
    kept = [p for p in kept if not p.get("_omission")]  # CONTRACT also names no seat / institution
    assert len(kept) == 1 and kept[0]["source"] == "both"
    assert [c.get("kind") or c["rules"] for c in kept[0]["_citations"]] == ["upload", ["7"]]
    assert [h["text"] for h in halves if not h.get("_omission")] == [
        "Any dispute arising out of or in connection with this Agreement shall be referred to arbitration."]


def test_a_failed_comparison_still_leaves_its_clause_half_for_the_fallback():
    halves = []
    # Section 7 was not retrieved: the comparison goes, the clause half (from the file) stays.
    kept, _ = llm_service._file_backed_points([_point("both", COMPARISON, "Clause 18 — Arbitration")],
                                              CONTRACT, NO_SECTION_7, NO_SECTION_7, [ACT], halves)
    assert [p for p in kept if not p.get("_omission")] == []
    clause = [h for h in halves if not h.get("_omission")]
    assert len(clause) == 1 and clause[0]["source"] == "file"
    assert clause[0]["_citations"][0]["title"] == "supply.docx, 18. Arbitration"


def test_a_check_with_only_failing_comparisons_falls_back_to_their_clause_halves(monkeypatch):
    result, calls = _failing_rules_check_with(monkeypatch, [_point("both", COMPARISON, "Clause 18 — Arbitration")],
                                              file_evidence=CONTRACT, context=NO_SECTION_7)
    assert result["ok"] and result["file_only"]
    assert calls.count("file_check_card") == 4  # found omissions alone never skip the retry
    assert [p["title"] for p in result["answer"]["points"]] == [
        "Clause 18 — Arbitration", "Clause 18 — seat", "Clause 18 — institution"]
    assert {p["source"] for p in result["answer"]["points"]} == {"file"}
    assert result["answer"]["limitations"] == llm_service.FILE_CHECK_INCOMPLETE_NOTE


def _failing_rules_check_with(monkeypatch, points, file_evidence, context):
    card = {"status": "answered", "direct": None, "summary": "x", "points": points,
            "practical_implications": None, "limitations": None, "follow_up": None}
    calls = []

    async def create(**kw):
        calls.append(kw["text"]["format"]["name"])
        return SimpleNamespace(output_text=json.dumps(card), usage=None)

    async def retrieve(query, selected_source=None):
        return context, [ACT], 1, [], ""
    for name, value in (("AI_PROVIDER", "openai"), ("OPENAI_API_KEY", "sk-test"), ("OPENAI_VECTOR_STORE_ID", "vs-test")):
        monkeypatch.setattr(llm_service, name, value)
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "_retrieve_context", retrieve)
    monkeypatch.setattr(llm_service, "_get_client", lambda: SimpleNamespace(responses=SimpleNamespace(create=create)))
    result = asyncio.run(llm_service.generate_response(
        [{"role": "user", "content": "Check it against the rules"}], use_file_search=True,
        retrieval_query="arbitration agreement", file_evidence=file_evidence))
    return result, calls


def test_a_missing_seat_or_institution_is_found_by_searching_the_file_not_by_the_model():
    halves = []
    kept, _ = llm_service._file_backed_points([], CONTRACT, SECTION_7, SECTION_7, [ACT], halves)
    assert [(p["title"], p["text"]) for p in kept] == [
        ("Clause 18 — seat", "Clause 18 names no seat of arbitration."),
        ("Clause 18 — institution", "Clause 18 names no institution to administer the arbitration.")]
    assert {c["title"] for p in kept for c in p["_citations"]} == {"supply.docx, 18. Arbitration"}
    named = CONTRACT + " The arbitration shall be held in Delhi under the rules of the DIAC."
    assert llm_service._file_backed_points([], named, SECTION_7, SECTION_7, [ACT], [])[0] == []
    # Not a file check's top-level call: nothing added.
    assert llm_service._file_backed_points([], CONTRACT, SECTION_7, SECTION_7, [ACT])[0] == []
