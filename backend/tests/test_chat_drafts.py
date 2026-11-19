"""Drafts: the three supported types with a fake model. Retrieval and the model
are faked; the evidence, attribution and citation checks in
llm_service.generate_response run for real."""
import asyncio
import io
from types import SimpleNamespace

import fitz
import pytest
from docx import Document
from fastapi import HTTPException

import ai_chat
import chat_drafts
import llm_service
from tests.test_grounding import _db

ACT = "Arbitration-And-Conciliation-Act-1996-as-on-2026-06-01.pdf"
MCIA = "MCIA-Rules-2025.pdf"
USER = {"user_id": "user_drafts_test", "email": "drafts@example.com"}
OTHER = {"user_id": "user_drafts_other", "email": "other@example.com"}

S21 = ("[Source: {f} | Section 21]\n21. Commencement of arbitral proceedings.—Unless otherwise agreed by the parties, "
       "the arbitral proceedings in respect of a particular dispute commence on the date on which a request for that "
       "dispute to be referred to arbitration is received by the respondent.").format(f=ACT)
S11 = ("[Source: {f} | Section 11]\n11. Appointment of arbitrators.—(6) Where, under an appointment procedure agreed "
       "upon by the parties, a party fails to act as required under that procedure, a party may request the Supreme "
       "Court or, as the case may be, the High Court or any person or institution designated by such Court to take "
       "the necessary measure for securing the appointment.").format(f=ACT)
MCIA_31 = ("[Source: {f} | Rule 3.1]\n3.1 A party wishing to commence an arbitration under these Rules shall file "
           "with the Registrar a Request for Arbitration which shall include the names, addresses and contact "
           "details of the parties.").format(f=MCIA)

CASES = {
    "section_21_notice": dict(
        message="Draft a notice invoking arbitration under Section 21", source=ACT, context=S21, anchor="21",
        supported="The arbitral proceedings commence on the date on which a request for that dispute to be "
                  "referred to arbitration is received by the respondent (Section 21).",
        unsupported="The respondent must reply within 15 days and pay a penalty of Rs 50,000 (Section 21)."),
    "section_11_application": dict(
        message="Draft a Section 11 application for appointment of an arbitrator", source=ACT, context=S11,
        anchor="11",
        supported="Where a party fails to act as required under the agreed appointment procedure, a party may "
                  "request the Supreme Court or the High Court to take the necessary measure (Section 11).",
        unsupported="The High Court must appoint the arbitrator within 7 days of filing (Section 11)."),
    "institution_request": dict(
        message="Draft a request for arbitration to MCIA", source=MCIA, context=MCIA_31, anchor="3.1",
        supported="A party wishing to commence an arbitration shall file with the Registrar a Request for "
                  "Arbitration which shall include the names, addresses and contact details of the parties (Rule 3.1).",
        unsupported="The Registrar must decide within 2 days whether to accept the Request (Rule 3.1)."),
}


@pytest.fixture
def fake_model(monkeypatch):
    monkeypatch.setattr(llm_service, "AI_PROVIDER", "groq")
    monkeypatch.setattr(llm_service, "AI_MODEL", "test-model")
    monkeypatch.setattr(llm_service, "GROQ_API_KEY", "gsk-test")
    monkeypatch.setattr(llm_service, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(llm_service, "OPENAI_VECTOR_STORE_ID", "vs-test")
    state = {"context": "", "source": None, "answer": "", "calls": [], "retrievals": []}

    async def retrieve(query, selected_source=None):
        state["retrievals"].append((query, selected_source))
        return state["context"], [state["source"]], 1, [], state["context"]

    async def create(**kwargs):
        state["calls"].append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=state["answer"]))])

    monkeypatch.setattr(llm_service, "_retrieve_context", retrieve)
    monkeypatch.setattr(llm_service, "_get_client",
                        lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    return state


def _run(coro_fn):
    async def body():
        db = _db()
        return await coro_fn(db)
    return asyncio.run(body())


def _ask(message, user=USER, language="auto"):
    async def go(db):
        return await ai_chat.handle_chat_message(db, None, message, user, client_ip="203.0.113.9", language=language)
    return _run(go)


def _download(draft_id, fmt, values=None, user=USER):
    async def go(db):
        return await chat_drafts.download(db, user, draft_id, fmt, values or {})
    return _run(go)


def _docx_text(data):
    return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)


def _pdf_text(data):
    with fitz.open(stream=data, filetype="pdf") as doc:
        return " ".join(" ".join(page.get_text().split()) for page in doc)


@pytest.mark.parametrize("dtype", list(CASES))
def test_each_type_keeps_placeholders_disclaimer_citations_and_drops_unsupported(fake_model, dtype):
    case = CASES[dtype]
    fake_model.update(context=case["context"], source=case["source"],
                      answer=f"{case['supported']}\n{case['unsupported']}")
    result = _ask(case["message"])
    draft = result["draft"]
    assert draft and draft["type"] == dtype
    # Placeholders survive, the disclaimer leads, citations attached, the unsupported statement is gone.
    assert "[Claimant name]" in result["reply"] or "[Applicant name]" in result["reply"]
    assert "[Clause number of the arbitration agreement]" in result["reply"]
    assert result["reply"].startswith(chat_drafts.DISCLAIMER["en"])
    assert any(case["anchor"] in c["rules"] for c in result["citations"])
    assert case["supported"].split(" (")[0][:60] in result["reply"]
    assert case["unsupported"].split(" (")[0] not in result["reply"]
    assert draft["note"] == chat_drafts.PARTIAL_NOTE
    # Ends with the provisions it relies on.
    assert draft["blocks"][-1]["text"] == chat_drafts.citation_lines(result["citations"])[-1]
    # The legal basis and provisions are never fillable.
    assert all(not b["fill"] for b in draft["blocks"] if b["text"] == case["supported"])
    # The model saw a fixed question, never the user's own words.
    assert fake_model["calls"][-1]["messages"][-1]["content"] != case["message"]

    for fmt, read in (("docx", _docx_text), ("pdf", _pdf_text)):
        data, name, _media = _download(draft["draft_id"], fmt)
        text = read(data)
        assert text.startswith(chat_drafts.DISCLAIMER["en"])
        assert "[Clause number of the arbitration agreement]" in text
        assert name.startswith(draft["file_stem"]) and name.endswith(f".{fmt}")


def test_filled_values_fill_every_position_and_empty_ones_stay(fake_model):
    case = CASES["section_21_notice"]
    fake_model.update(context=case["context"], source=case["source"], answer=case["supported"])
    draft = _ask(case["message"])["draft"]
    calls = len(fake_model["calls"])
    values = {"Claimant name": "Asha Rao", "Date of notice": "  ", "Section 21": "hijack", "Unknown": "x"}
    text = _docx_text(_download(draft["draft_id"], "docx", values)[0])
    assert text.count("Asha Rao") == 2 and "[Claimant name]" not in text  # From line and signature
    assert "[Date of notice]" in text  # blank stays a placeholder
    assert "hijack" not in text and "Section 21 of the Arbitration and Conciliation Act, 1996" in text
    assert case["supported"].split(" (")[0][:60] in text  # legal text unchanged
    assert len(fake_model["calls"]) == calls  # downloads never call the model


def test_value_cannot_change_the_legal_basis_even_if_it_matches_a_bracket():
    draft = {"blocks": [{"style": "para", "text": "[Claimant name]", "fill": True},
                        {"style": "para", "text": "Legal [Claimant name] text", "fill": False}],
             "disclaimer": "D"}
    assert chat_drafts.plain_text(draft, {"Claimant name": "X"}) == "D\n\nX\n\nLegal [Claimant name] text"


def test_guest_gets_the_sign_in_message_and_no_model_call(fake_model):
    result = _ask("Draft a notice invoking arbitration under Section 21", user=None)
    assert result["reply"] == chat_drafts.GUEST_MESSAGE
    assert result["draft"] is None and fake_model["calls"] == []


@pytest.mark.parametrize("message,closest", [
    ("Draft a rent agreement for my flat", "section_21_notice"),
    ("Draft a writ petition for the High Court", "section_11_application"),
    ("Draft a request for arbitration to SIAC", "institution_request"),
])
def test_a_fourth_kind_lists_the_three_and_offers_the_closest(fake_model, message, closest):
    result = _ask(message)
    assert result["draft"] is None and fake_model["calls"] == []
    for t in chat_drafts.TYPES.values():
        assert t["name"] in result["reply"]
    assert f"closest to what you asked for is: {chat_drafts.TYPES[closest]['name']}" in result["reply"]


def test_no_draft_when_the_anchor_provision_is_not_verified(fake_model):
    fake_model.update(context=S21.replace("Section 21", "Section 20").replace("21.", "20."), source=ACT,
                      answer="The arbitral proceedings commence on the date on which a request for that dispute to "
                             "be referred to arbitration is received by the respondent (Section 20).")
    result = _ask("Draft a notice invoking arbitration under Section 21")
    assert result["draft"] is None and "Section 21" in result["reply"]


def test_other_users_cannot_download_and_hindi_pdf_is_refused(fake_model):
    case = CASES["section_21_notice"]
    fake_model.update(context=case["context"], source=case["source"], answer=case["supported"])
    draft = _ask(case["message"], language="hi")["draft"]
    assert draft["language"] == "hi" and draft["disclaimer"] == chat_drafts.DISCLAIMER["hi"]
    assert "Section 21" in draft["blocks"][0]["text"]  # provision labels stay as written
    with pytest.raises(HTTPException) as e:
        _download(draft["draft_id"], "docx", user=OTHER)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        _download(draft["draft_id"], "pdf")
    assert e.value.status_code == 409
    assert _docx_text(_download(draft["draft_id"], "docx")[0]).startswith(chat_drafts.DISCLAIMER["hi"])


def test_history_returns_the_draft(fake_model):
    case = CASES["section_21_notice"]
    fake_model.update(context=case["context"], source=case["source"], answer=case["supported"])
    result = _ask(case["message"])

    async def go(db):
        return await ai_chat.get_conversation_history(db, result["conversation_id"], USER)
    history = _run(go)
    assert history[-1]["draft"]["draft_id"] == result["draft"]["draft_id"]


def test_long_value_is_rejected():
    draft = {"blocks": [{"style": "para", "text": "[Claimant name]", "fill": True}]}
    with pytest.raises(HTTPException):
        chat_drafts.clean_values(draft, {"Claimant name": "x" * 501})


def test_card_legal_basis_uses_the_points_not_the_summary_that_repeats_them():
    card = {"summary": "Restated points.", "points": [{"title": "A", "text": "First (Section 11)."},
                                                       {"title": "B", "text": "Second (Section 11)."}]}
    assert chat_drafts._grounds({"answer": card}) == ["First (Section 11).", "Second (Section 11)."]
    assert chat_drafts._grounds({"answer": {"summary": "Only this.", "points": []}}) == ["Only this."]
