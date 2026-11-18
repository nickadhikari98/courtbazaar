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
