"""rag_provisions.parse_provisions: OCR page-break artifacts (2026-10-16).

"According to the DIAC Arbitration Proceedings Rules, 2023, how is an
arbitrator appointed when the parties fail to agree?" came back as an empty
"Appointment Procedure" heading. The PDF's OCR text has, at a page break:

    8.5 ... the Claimant shall appoint its Arbitrator at the time of filing the request and the 9.
    9 Respondent shall appoint its Arbitrator ...
    8.6 Where the parties fail to appoint their respective Arbitrators ...

"9 Respondent" (a page number at a line start) was taken as the start of
Rule 9, so 8.6 (not under parent 9) was skipped and its text filed under the
false "Rule 9". The model's "(Rule 8.6)" then cited a rule absent from the
context, rule attribution dropped every such sentence, and only the heading
was left. Rule 9's own heading line is missing in the OCR text; its sub-rules
start straight at 9.1.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import answer_guard  # noqa: E402
import llm_service  # noqa: E402
import rag_provisions  # noqa: E402

FILE = llm_service.SOURCE_DIAC
TITLE = "DELHI INTERNATIONAL ARBITRATION CENTRE (ARBITRATION PROCEEDINGS) RULES. 2023"

DOC = llm_service._readable_excerpt(
    f"{TITLE}\n"
    "8. Appointment and Confirmation of Arbitrators\n"
    "8.3 The Arbitrator shall be appointed from the list of Arbitrators who is common in the request for "
    "arbitration and the response thereto.\n"
    "8.4 In case there is no such common name, the Arbitrator shall be appointed by the Chairperson/Sub-committee.\n"
    "8.5 Where the agreement provides for the appointment of three Arbitrators, the Claimant shall appoint its "
    "Arbitrator at the time of filing the request and the 9.\n"
    "9 Respondent shall appoint its Arbitrator at the time of filing of its response to the Request for "
    "Arbitration, and the two Arbitrators shall within 21 days, appoint the Presiding Arbitrator.\n"
    "8.6 Where the parties fail to appoint their respective Arbitrators or where the Arbitrators appointed by "
    "the parties fail to appoint the Presiding Arbitrator, in terms of Rule 8.5, then within 21 days thereof, "
    "the Chairperson/ Sub-Committee shall appoint the Arbitrator/ Presiding Arbitrator as the case may be. "
    "Appointment in case of Multiparty Arbitration\n"
    "9.1 The parties to a multi party dispute are free to determine whether the Arbitral Tribunal shall be "
    "constituted by a Sole Arbitrator or by three Arbitrators.\n"
    "9.2 Failing a joint nomination by all the parties to the arbitration the Sole Arbitrator shall be "
    "appointed by the Chairperson.\n"
    "10. Challenge of Arbitrators\n"
    "10.1 An Arbitrator may be challenged.\n"
)


def _numbers():
    return [p["number"] for p in rag_provisions.parse_provisions(DOC)]


def test_a_page_number_at_a_line_start_is_not_a_new_rule():
    numbers = _numbers()
    assert "8.6" in numbers
    assert numbers.index("8.5") < numbers.index("8.6") < numbers.index("9.1")
    by_number = {p["number"]: p for p in rag_provisions.parse_provisions(DOC)}
    # 8.5's second half, after the page break, stays with 8.5.
    assert "Respondent shall appoint its Arbitrator" in by_number["8.5"]["text"]
    assert by_number["8.6"]["text"].startswith("8.6 Where the parties fail to appoint")


def test_a_rule_whose_heading_line_is_missing_still_opens_at_its_first_sub_rule():
    numbers = _numbers()
    assert ["9.1", "9.2"] == [n for n in numbers if n.startswith("9.")]
    assert "9" not in numbers  # no heading line for 9 in the text, none invented
    assert numbers[-2:] == ["10", "10.1"]


def test_an_out_of_order_number_is_still_not_a_rule():
    doc = llm_service._readable_excerpt(
        "8. Heading\n8.1 First.\n3 Weeks are counted.\n8.2 Second.\n")
    assert [p["number"] for p in rag_provisions.parse_provisions(doc)] == ["8", "8.1", "8.2"]


def test_appointment_answer_cites_rule_8_6_and_keeps_it_through_attribution():
    chunk = DOC[DOC.index("8.6 Where"):DOC.index("9.1")]
    context = "\n\n".join(rag_provisions.expand_chunks(FILE, [chunk], DOC))
    assert f"[Source: {FILE} | Rule 8.6 | {TITLE}]" in context
    answer = ("## Appointment Procedure\n"
              "Where the parties fail to appoint their respective Arbitrators, within 21 days thereof, the "
              "Chairperson/ Sub-Committee shall appoint the Arbitrator (Rule 8.6).")
    validated = answer_guard.validate_grounded_answer(answer, context, document_evidence=True)
    assert validated is not None
    attributed, dropped = answer_guard.validate_rule_attribution(validated, rag_provisions.provision_map(context))
    assert dropped == 0
    assert "Chairperson/ Sub-Committee shall appoint the Arbitrator (Rule 8.6)" in attributed
    citations = llm_service.build_citations(attributed, context, [FILE])
    assert citations == [{
        "title": "Delhi International Arbitration Centre (Arbitration Proceedings) Rules, 2023",
        "url": llm_service.KB_INSTRUMENT_URLS["Delhi International Arbitration Centre (Arbitration Proceedings) Rules, 2023"], "rules": ["8.6"], "document": llm_service.KB_SOURCE_DISPLAY[FILE]["label"],
    }]
