"""Instant Legal Help — structured answer cards. The pipeline runs end to end
with the vector store and OpenAI mocked: a card must pass the same evidence
checks as a plain answer, sources must come from retrieval metadata, and any
failure must land on the plain answer rather than an unverified card."""
import asyncio
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_rag_answer_quality import RULE_33_BODY, RULE_33_HEAD, FakeOpenAI, _ask, _db, _install, _item  # noqa: E402

import ai_chat  # noqa: E402
import answer_guard  # noqa: E402
import llm_service  # noqa: E402
import rag_provisions  # noqa: E402

REAL_DOCUMENT_ROUTE = llm_service.document_route  # conftest stubs it for every other test
GOOD_POINT = {
    "icon": "rule", "title": "Rule 33.5 — Failure to deposit", "badge": "Rule 33.5", "tone": "warning",
    "text": "If a party fails to make the deposits within thirty days from the date on which it is due, the "
            "Centre may terminate the arbitration where the Tribunal is yet to be constituted (Rule 33.5).",
    "cite": [1],
}
# Rule 33.2 says nothing about the Tribunal charging interest.
BAD_POINT = {**GOOD_POINT, "title": "Rule 33.2 — Interest", "badge": "Rule 33.2",
             "text": "The Tribunal shall charge compound interest on every unpaid amount (Rule 33.2)."}


def _card(**overrides):
    return json.dumps({
        "status": "answered", "direct": None,
        "summary": "If a party fails to make the deposits, the Centre may terminate the arbitration (Rule 33.5).",
        "points": [GOOD_POINT], "follow_up": "Do you want to know who pays the deposits?", **overrides,
    })


def _verdict(points=("SUPPORTED",), summary="SUPPORTED", main_ask=True, action_ok=True):
    return json.dumps({"analysis": "x", "direct_matches_action": action_ok, "summary": summary, "main_ask_answered": main_ask,
                       "points": [{"index": i, "verdict": v} for i, v in enumerate(points)]})


class ScriptedOpenAI(FakeOpenAI):
    """Returns `outputs` in order, then repeats the last one. `calls` holds
    answer calls; the verifier's go to `verifier_calls`, answered by `verdicts`."""

    def __init__(self, outputs, verdicts=(None,)):
        super().__init__(items=[_item(RULE_33_BODY, score=0.87), _item(RULE_33_HEAD, score=0.61)])
        self.outputs, self.calls, self.verdicts, self.verifier_calls = list(outputs), [], list(verdicts), []

    async def create(self, **kwargs):
        if kwargs.get("text", {}).get("format", {}).get("name") == "answer_verdict":
            self.verifier_calls.append(kwargs)
            verdict = self.verdicts.pop(0) if len(self.verdicts) > 1 else self.verdicts[0]
            if verdict is None:
                raise RuntimeError("verifier down")
            return SimpleNamespace(output_text=verdict)
        self.calls.append(kwargs)
        self.answer = self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        response = await super().create(**kwargs)
        if not kwargs.get("stream"):
            return response

        async def events():
            yield SimpleNamespace(type="response.created")
            for delta in (response.output_text[:5], response.output_text[5:]):
                yield SimpleNamespace(type="response.output_text.delta", delta=delta)
        return events()


@pytest.fixture
def ask(monkeypatch):
    def run(*outputs, message="What happens if a party does not pay the deposits under the DIAC rules?",
            verdicts=(None,)):
        fake = ScriptedOpenAI(outputs, verdicts)
        _install(monkeypatch, fake)
        return _ask(message), fake
    return run


def test_schema_is_valid_for_strict_structured_outputs():
    schema = llm_service.AnswerCard.model_json_schema()
    for obj in (schema, schema["$defs"]["AnswerPoint"]):
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])


def test_valid_card_is_returned_with_server_built_sources(ask):
    result, fake = ask(_card())
    answer = result["answer"]
    assert len(fake.calls) == 1 and fake.calls[0]["text"]["format"]["strict"] is True
    assert answer["status"] == "answered" and result["grounding"] == "supported"
    assert [p["title"] for p in answer["points"]] == [GOOD_POINT["title"]]
    assert result["citations"][answer["points"][0]["cite"][0] - 1]["rules"] == ["33.5"]
    assert answer["note"].startswith("Based on ") and answer["note"].endswith("verify with an advocate.")
    assert answer["note_detail"] in result["reply"] and "numbering can change" in answer["note_detail"]
    assert "## Rule 33.5" in result["reply"] and answer["summary"] in result["reply"]


def test_model_cannot_cite_a_source_that_does_not_exist(ask):
    point = {**GOOD_POINT, "title": "Failure to deposit", "badge": None, "cite": [99],
             "text": "If a party fails to make the deposits, the Centre may terminate the arbitration."}
    result, _ = ask(_card(points=[GOOD_POINT, point]))
    assert [p["title"] for p in result["answer"]["points"]] == [GOOD_POINT["title"]]
    assert result["answer"]["status"] == "answered" and result["grounding"] == "supported"


def test_unsupported_point_is_dropped_without_marking_the_card_partial(ask):
    result, _ = ask(_card(points=[GOOD_POINT, BAD_POINT]))
    assert [p["title"] for p in result["answer"]["points"]] == [GOOD_POINT["title"]]
    assert result["answer"]["status"] == "answered"
    assert "compound interest" not in result["reply"]
    assert "33.2" not in json.dumps(result["citations"])


def test_badge_with_an_invented_number_is_removed(ask):
    result, _ = ask(_card(points=[{**GOOD_POINT, "badge": "Rule 99.9"}]))
    assert result["answer"]["points"][0]["badge"] is None


def test_statement_as_follow_up_is_removed(ask):
    result, _ = ask(_card(follow_up="You will also owe 18% interest."))
    assert result["answer"]["follow_up"] is None
    assert "18%" not in result["reply"]


def test_invalid_json_retries_once_then_uses_the_plain_answer(ask):
    result, fake = ask("{not json", "still not json", "Unless the Centre directs otherwise, 50% of such deposits "
                       "shall be payable by the Claimant (Rule 33.1).")
    assert len(fake.calls) == 3
    assert "text" in fake.calls[0] and "text" in fake.calls[1] and "text" not in fake.calls[2]
    assert result["answer"] is None and "Rule 33.1" in result["reply"]


def test_retry_recovers_a_card(ask):
    result, fake = ask("{not json", _card())
    assert len(fake.calls) == 2 and result["answer"]["status"] == "answered"


def test_unsupported_summary_is_replaced_by_verified_point_text(ask):
    bad = _card(summary="The Tribunal shall charge compound interest on every unpaid amount (Rule 33.2).")
    result, fake = ask(bad, bad)
    assert len(fake.calls) == 2 and "compound interest" not in result["reply"]
    assert result["answer"]["summary"] == result["answer"]["points"][0]["text"]


def test_summary_that_loses_its_opening_is_not_shown_as_a_card(ask):
    good = "If a party fails to make the deposits, the Centre may terminate the arbitration (Rule 33.5)."
    bad = _card(summary=f"The Tribunal shall charge compound interest on every unpaid amount. {good}")
    result, fake = ask(bad, _card())
    assert len(fake.calls) == 2 and result["answer"]["summary"] == good


def test_summary_tail_inference_is_cut_without_marking_the_card_partial(ask):
    good = "If a party fails to make the deposits, the Centre may terminate the arbitration (Rule 33.5)."
    result, fake = ask(_card(summary=f"{good} This means compound interest becomes payable to the bank."))
    assert len(fake.calls) == 1
    assert result["answer"]["summary"] == good and result["answer"]["status"] == "answered"


SECOND_POINT = {**GOOD_POINT, "title": "Rule 33.1 — Advance on costs", "badge": "Rule 33.1",
                "text": "Unless the Centre directs otherwise, 50% of such deposits shall be payable by the Claimant "
                        "and the remaining 50% of such deposits shall be payable by the Respondent (Rule 33.1)."}


def test_card_generation_and_verifier_run_at_temperature_zero(ask):
    _, fake = ask(_card(), verdicts=[_verdict()])
    assert fake.calls[0]["temperature"] == 0 and fake.verifier_calls[0]["temperature"] == 0
    assert fake.verifier_calls[0]["model"] == llm_service.AI_VERIFIER_MODEL


def test_verifier_drops_contradicted_and_not_in_source_points(ask):
    third = {**SECOND_POINT, "title": "Rule 33.1 — Shares"}
    verdict = _verdict(["SUPPORTED", "CONTRADICTED", "NOT_IN_SOURCE"])
    result, _ = ask(_card(points=[GOOD_POINT, SECOND_POINT, third]), verdicts=[verdict])
    assert [p["title"] for p in result["answer"]["points"]] == [GOOD_POINT["title"]]
    assert "33.1" not in json.dumps(result["citations"]) and "50%" not in result["reply"]


def test_partial_card_keeps_its_full_note(ask):
    result, _ = ask(_card(), verdicts=[_verdict(main_ask=False)])
    assert result["answer"]["note_detail"] is None and "isn't clearly covered" in result["answer"]["note"]


def test_only_the_verifier_marks_a_card_partial(ask):
    result, _ = ask(_card(status="partial"), verdicts=[_verdict(main_ask=True)])
    assert result["answer"]["status"] == "answered" and result["grounding"] == "supported"
    result, _ = ask(_card(), verdicts=[_verdict(main_ask=False)])
    assert result["answer"]["status"] == "partial" and result["grounding"] == "partial"


def test_rejected_summary_is_regenerated_with_feedback(ask):
    fixed = "If a party fails to make the deposits, the Centre may terminate the arbitration (Rule 33.5)."
    result, fake = ask(_card(summary=f"{fixed} Any party is free to pay the whole of the deposits (Rule 33.2)."),
                       _card(summary=fixed), verdicts=[_verdict(summary="CONTRADICTED"), _verdict()])
    assert len(fake.calls) == 2 and result["answer"]["summary"] == fixed
    assert any(llm_service.SUMMARY_RETRY_NOTE == m["content"] for m in fake.calls[1]["input"])


def test_summary_rejected_twice_is_replaced_by_verified_point_text(ask):
    result, fake = ask(_card(), verdicts=[_verdict(summary="CONTRADICTED")])
    assert len(fake.calls) == 2
    assert result["answer"]["summary"] == result["answer"]["points"][0]["text"]


def test_verifier_outage_keeps_the_evidence_checked_card(ask):
    result, fake = ask(_card(), verdicts=[None])
    assert len(fake.verifier_calls) == 1 and result["answer"]["status"] == "answered"
    result, _ = ask(_card(), verdicts=["{not json"])
    assert result["answer"]["status"] == "answered"


def test_plain_fallback_rejected_by_verifier_becomes_not_covered(ask):
    plain = "Unless the Centre directs otherwise, 50% of such deposits shall be payable by the Claimant (Rule 33.1)."
    result, _ = ask("{not json", "{not json", plain, verdicts=[_verdict(summary="CONTRADICTED")])
    assert result["grounding"] == "insufficient" and "Claimant (Rule 33.1)" not in result["reply"]


def test_every_source_url_names_the_same_rules_and_year_as_its_title():
    assert set(llm_service.KB_INSTRUMENT_URLS) == {n for _, n in llm_service.KB_INSTRUMENTS[llm_service.SOURCE_DIAC]}
    for title, url in llm_service.KB_INSTRUMENT_URLS.items():
        year = title.rsplit(" ", 1)[-1]
        assert url.startswith("https://dhcdiac.nic.in/") and f"-Rules-{year}-" in url
    assert llm_service.KB_SOURCE_DISPLAY[llm_service.SOURCE_DIAC]["url"] is None


def test_citation_links_to_the_pdf_of_its_own_rule_set(ask):
    result, _ = ask(_card())
    for citation in result["citations"]:
        assert citation["url"] == llm_service.KB_INSTRUMENT_URLS.get(citation["title"])


def _search_returning(monkeypatch, score, filename=llm_service.SOURCE_DIAC, error=None):
    async def search(**kwargs):
        if error:
            raise error
        return SimpleNamespace(data=[SimpleNamespace(filename=filename, score=score)])
    monkeypatch.setattr(llm_service, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(llm_service, "OPENAI_VECTOR_STORE_ID", "vs-test")
    monkeypatch.setattr(llm_service, "_get_retrieval_client",
                        lambda: SimpleNamespace(vector_stores=SimpleNamespace(search=search)))


@pytest.mark.parametrize("score,expected", [(0.85, llm_service.SOURCE_DIAC), (0.849, None)])
def test_document_route_uses_the_score_threshold(monkeypatch, score, expected):
    _search_returning(monkeypatch, score)
    assert asyncio.run(REAL_DOCUMENT_ROUTE("Who pays?")) == expected


def test_document_route_ignores_unapproved_files_and_search_failures(monkeypatch):
    _search_returning(monkeypatch, 0.99, filename="other.pdf")
    assert asyncio.run(REAL_DOCUMENT_ROUTE("Who pays?")) is None
    _search_returning(monkeypatch, 0.99, error=RuntimeError("down"))
    assert asyncio.run(REAL_DOCUMENT_ROUTE("Who pays?")) is None


def _route_to_diac(monkeypatch):
    seen = []

    async def route(query):
        seen.append(query)
        return llm_service.SOURCE_DIAC
    monkeypatch.setattr(llm_service, "document_route", route)
    return seen


def test_high_score_sends_an_unnamed_question_to_the_document(ask, monkeypatch):
    _route_to_diac(monkeypatch)
    result, fake = ask(_card(), message="What happens if a party fails to make the deposits within thirty days?")
    assert len(fake.calls) == 1 and result["answer"] is not None


def test_casual_turns_are_not_score_routed(ask, monkeypatch):
    seen = _route_to_diac(monkeypatch)
    ask(_card(), message="hello")
    assert seen == []


def test_not_found_uses_the_existing_not_covered_reply(ask):
    result, fake = ask(_card(status="not_found", points=[]))
    assert len(fake.calls) == 2  # a second look before saying so
    assert result["grounding"] == "insufficient" and result["answer"] is None and result["citations"] == []


def _stream(message, conversation_id=None):
    async def body():
        db = _db()
        frames = [f async for f in ai_chat.stream_chat_events(db, conversation_id, message, None, client_ip="127.0.0.1")]
        return [json.loads(f.removeprefix("data: ").strip()) for f in frames]
    return asyncio.run(body())


def _stream_with(monkeypatch, output):
    fake = ScriptedOpenAI([output], [_verdict()])
    _install(monkeypatch, fake)


def test_stream_reports_each_real_step_then_the_answer(monkeypatch):
    _stream_with(monkeypatch, _card())
    events = _stream("Under the DIAC rules, what happens if a party does not pay the deposits?")
    assert [e.get("step") for e in events[:-1]] == ["understanding", "searching", "reading", "writing", "verifying"]
    assert events[1]["text"] == "Searching DIAC Rules…"
    assert events[2]["text"].startswith("Reading ") and events[-1]["type"] == "answer"
    assert events[-1]["data"]["answer"]["status"] == "answered"


def test_stream_reports_no_match_before_the_not_covered_answer(monkeypatch):
    _stream_with(monkeypatch, _card(status="not_found", points=[]))
    events = _stream("Under the DIAC rules, what happens if a party does not pay the deposits?")
    assert events[-2] == {"type": "status", "step": "no_match", "text": "No matching rule found…"}
    assert events[-1]["data"]["grounding"] == "insufficient"


def test_stream_turns_a_client_error_into_an_error_event(monkeypatch):
    _stream_with(monkeypatch, _card())
    event = _stream("hello", conversation_id="missing")[-1]
    assert event["type"] == "error" and event["status"] == 404


RULE_33_1 = {"number": "33.1", "text": "33.1 The Centre shall fix the amount of deposits to be made by the parties."}
RULE_33_5 = {"number": "33.5", "text": "33.5 If a party fails to make the deposits within thirty days the Centre may terminate."}
OTHER = {"number": "9", "text": "9. The seat of arbitration shall be Delhi unless the parties agree otherwise."}


def test_keyword_search_finds_the_rule_by_its_words():
    provisions = [OTHER, RULE_33_1, RULE_33_5]
    assert rag_provisions.keyword_matches("What if a party fails within thirty days?", provisions)[0] == 2
    assert rag_provisions.keyword_matches("the and of", provisions) == []


def test_clause_number_invented_for_a_rule_is_rejected_but_the_real_one_passes():
    evidence = ("[Source: f | Rule 4 | COSTS]\n4. Parties to share equally (i) The Administrative Costs and the "
                "Arbitrators' fees shall be initially shared equally by the parties.")
    provisions = rag_provisions.provision_map(evidence)
    text = "The Administrative Costs and the Arbitrators' fees shall be initially shared equally by the parties"
    card = {"status": "answered", "direct": None, "summary": f"{text} (Rule 4(i)).", "follow_up": None, "points": [
        {"title": "Rule 4(i) — Sharing", "badge": "Rule 4(i)", "text": f"{text} (Rule 4(i)).", "icon": "rule",
         "tone": "neutral", "cite": [1]}]}
    assert answer_guard.validate_answer_card(card, evidence, provisions)["points"]
    wrong = {**card, "points": [{**card["points"][0], "title": "Rule 4.1 — Sharing", "text": f"{text} (Rule 4.1)."}]}
    assert answer_guard.validate_answer_card(wrong, evidence, provisions) is None


def test_direct_answer_leads_the_summary_and_the_guards_check_the_rule_text(ask):
    result, _ = ask(_card(direct="no"), verdicts=[_verdict()],
                    message="Does the DIAC rule on deposits treat the parties differently?")
    assert result["answer"]["summary"].startswith("No. If a party fails to make the deposits")


def test_only_a_yes_no_question_gets_a_yes_or_no(ask):
    result, _ = ask(_card(direct="yes"), message="Under the DIAC rules, who pays the deposits?")
    assert result["answer"]["summary"].startswith("If a party")


def test_wrong_not_found_gets_a_second_look_that_can_recover(ask):
    result, fake = ask(_card(status="not_found", points=[]), _card())
    assert len(fake.calls) == 2 and result["answer"]["status"] == "answered"
    assert any(llm_service.NOT_FOUND_RETRY_NOTE == m["content"] for m in fake.calls[1]["input"])


@pytest.mark.parametrize("follow_up,kept", [
    ("Who pays what under Rule 33.1?", True),
    ("Would you like to know more about Rule 33.1?", False),
    ("Who pays what under Rule 33.5?", False),  # already answered by the card
    ("Who pays what under Rule 34?", False),    # no such rule retrieved
    ("Do you need information on the consequences?", False),
    ("Who pays what?", False),                  # names no rule
])
def test_follow_up_must_name_an_unused_retrieved_rule(follow_up, kept):
    numbers = {"33.1", "33.5", "34"}
    provisions = {"33.1": "x", "33.5": "y"}
    result = answer_guard._specific_follow_up(follow_up, [GOOD_POINT], "", numbers, provisions)
    assert result == (follow_up if kept else None)


def test_follow_up_rule_is_not_listed_as_a_source(ask):
    result, _ = ask(_card(follow_up="What happens under Rule 33.1 to the shares of the deposits?"))
    assert all("33.1" not in c["rules"] for c in result["citations"])


def test_plain_answer_is_partial_only_when_the_verifier_says_so(ask):
    plain = ("Unless the Centre directs otherwise, 50% of such deposits shall be payable by the Claimant (Rule 33.1). "
             "The Tribunal shall charge compound interest on every unpaid amount.")
    result, _ = ask("{not json", "{not json", plain, verdicts=[_verdict(points=(), main_ask=True)])
    assert result["grounding"] == "supported"
    assert answer_guard.PARTIAL_ANSWER_NOTE not in result["reply"]


@pytest.mark.parametrize("question,score,routed", [
    ("Can the tribunal suspend proceedings if the deposit is not paid?", 0.53, True),
    ("How do I file for anticipatory bail?", 0.78, False),                      # no rules vocabulary
    ("How does arbitration work in India?", 0.79, False),
    ("Can a tribunal arbitrator act under Section 11 of the Arbitration Act?", 0.6, False),  # named statute
    ("What deposit does a tribunal need?", 0.3, False),                         # below the floor
])
def test_rules_vocabulary_routes_a_mid_score_question(monkeypatch, question, score, routed):
    _search_returning(monkeypatch, score)
    assert asyncio.run(REAL_DOCUMENT_ROUTE(question)) == (llm_service.SOURCE_DIAC if routed else None)


@pytest.mark.parametrize("url", [
    "https://dhcdiac.nic.in/diac-arbitration-proceedings-rules-2018-2/",
    "https://dhcdiac.nic.in/wp-content/uploads/2020/01/DIAC-Arbitration-Proceedings-Rules-2018.pdf",
])
def test_superseded_rules_are_never_a_web_source(url):
    assert llm_service._official_url(url) is None


def test_current_rules_are_still_a_web_source():
    url = llm_service.KB_INSTRUMENT_URLS["Delhi International Arbitration Centre (Arbitration Proceedings) Rules, 2023"]
    assert llm_service._official_url(url) == url


@pytest.mark.parametrize("title,url,expected", [
    ("34.2 Where the amount of the deposit", "https://dhcdiac.nic.in/x/DIAC-Rules-2023.pdf", "DIAC Rules 2023"),
    ("Source 1:34.2 Where the amount", "https://dhcdiac.nic.in/x/DIAC-Rules-2023.pdf", "DIAC Rules 2023"),
    ("where the amount", "https://www.sci.gov.in/judgements", "www.sci.gov.in"),
    (None, "https://www.sci.gov.in/judgements", "www.sci.gov.in"),
    ("Supreme Court of India", "https://www.sci.gov.in/judgements", "Supreme Court of India"),
])
def test_web_source_title_is_never_chunk_text(title, url, expected):
    assert llm_service._web_title(title, url) == expected


def test_web_answer_built_on_superseded_rules_is_answered_from_the_documents(ask, monkeypatch):
    monkeypatch.setattr(llm_service, "web_search_enabled", lambda: True)

    async def superseded(messages):
        return {"ok": False, "error_code": llm_service.ERR_NO_CONTEXT, "superseded": True}
    monkeypatch.setattr(llm_service, "generate_web_answer", superseded)
    result, fake = ask(_card(), message="What is the procedure for arbitration fees before a tribunal in court?")
    assert result["answer"] is not None and not any(c.get("kind") == "web" for c in result["citations"])


SUSPEND_Q = "Can the tribunal suspend proceedings if the deposit is not paid?"
FULL_RULES = [
    "15.2 The Arbitral Tribunal may modify, suspend or terminate an interim measure granted by it.",
    "33.5 If a party fails to make the deposits the Centre may terminate the arbitration.",
    "21.4 Any party seeking adjournment of the arbitration proceedings shall file a written application.",
]


def test_action_the_rules_use_elsewhere_is_not_addressed_for_this_subject():
    assert answer_guard.unaddressed_action(SUSPEND_Q, FULL_RULES) == "suspension"


def test_action_the_rules_provide_on_this_subject_is_addressed():
    rules = FULL_RULES + ["33.9 The Tribunal may suspend the proceedings if deposits are unpaid."]
    assert answer_guard.unaddressed_action(SUSPEND_Q, rules) is None


def test_no_claim_about_the_rules_without_the_rules_to_search():
    assert answer_guard.unaddressed_action(SUSPEND_Q, []) is None


def test_termination_rule_never_answers_yes_to_suspension(ask, monkeypatch):
    monkeypatch.setattr(llm_service, "_action_gap", lambda q, d: "suspension")
    result, fake = ask(_card(direct="yes"), verdicts=[_verdict()], message=f"Under the DIAC rules: {SUSPEND_Q}")
    summary = result["answer"]["summary"]
    assert summary.startswith("The Rules don't mention suspension in this situation.") or "don't mention suspension" in summary
    assert not summary.startswith("Yes") and result["answer"]["status"] == "answered"
    assert "<question></question>" in fake.verifier_calls[0]["input"][0]["content"]  # judged as rule text only


def test_verifier_catching_a_wrong_action_removes_the_yes(ask):
    result, _ = ask(_card(direct="yes"), verdicts=[_verdict(action_ok=False)],
                    message="Does the DIAC rule let the Centre act on unpaid deposits?")
    assert result["answer"]["summary"].startswith("If a party")


def test_plain_fallback_cannot_say_yes_to_an_action_the_rules_lack(ask, monkeypatch):
    monkeypatch.setattr(llm_service, "_action_gap", lambda q, d: "suspension")
    plain = "Yes. If a party fails to make the deposits, the Centre may terminate the arbitration (Rule 33.5)."
    result, _ = ask("{not json", "{not json", plain, message=f"Under the DIAC rules: {SUSPEND_Q}")
    assert result["grounding"] == "insufficient" and "Yes." not in result["reply"]


def test_action_check_only_applies_to_an_answer_that_says_yes_or_no(ask):
    plain = "Unless the Centre directs otherwise, 50% of such deposits shall be payable by the Claimant (Rule 33.1)."
    result, _ = ask("{not json", "{not json", plain, verdicts=[_verdict(points=(), action_ok=False)])
    assert result["grounding"] == "supported" and "50%" in result["reply"]


def test_card_fallback_logs_its_reason(ask, caplog):
    with caplog.at_level("WARNING", logger="llm_service"):
        ask("{not json", "{not json", "Plain.", verdicts=[_verdict()])
    assert any("Card fallback" in r.message and "invalid JSON" in r.message for r in caplog.records)


def test_plain_answer_gets_the_short_note(ask):
    plain = "Unless the Centre directs otherwise, 50% of such deposits shall be payable by the Claimant (Rule 33.1)."
    result, _ = ask("{not json", "{not json", plain, verdicts=[_verdict(points=())])
    assert result["answer"] is None and result["note"].startswith("Based on ")
    assert "numbering can change" in result["note_detail"] and "numbering can change" not in result["body"]


def test_badge_and_source_use_the_clause_the_answer_cited():
    assert answer_guard.clause_labels("shared equally (Rule 4(i)) and Rule 33.1") == {"4": ["4(i)"]}
    context = "[Source: DIAC Rules conclusive_UsingOCR.pdf | Rule 4 | X]\n4. Share (i) equally."
    citation = llm_service.build_citations("Shared equally (Rule 4(i)).", context, [llm_service.SOURCE_DIAC])[0]
    assert citation["rules"] == ["4"] and citation["rule_labels"] == ["4(i)"]


def test_reading_status_names_the_asked_rule_first_and_caps_at_three():
    rules = ["31.1", "32.2", "33.1", "33.2", "33.5"]
    assert llm_service._reading_text("Under Rule 33.1, who pays?", rules, []) == "Reading Rule 33.1, Rule 31.1, Rule 32.2 +2 more…"
    assert llm_service._reading_text("Who pays?", ["5"], []) == "Reading Rule 5…"
    assert llm_service._reading_text("Who pays?", [], [llm_service.SOURCE_SOP]) == "Reading Standard Operating Procedure (SOP)…"
