"""No citation renders with an empty number, and a number that exists in several
rule sets is cited under the set whose text supports the answer. Provision text
comes from the approved PDFs via pdftotext (git-ignored, so skipped where absent)."""
import pytest

import llm_service
import rag_provisions
from tests.test_rag_icc_appendix_and_links import APPENDIX_IV, ICC, _store_text

ICA = "ICA-Rules-of-Domestic-Commercial-Arbitration-2024.pdf"
MEDIATION = "ICC Mediation Rules 2014"


def _context(filename, query):
    text, pages = _store_text(filename)
    return "\n\n".join(rag_provisions.expand_chunks(filename, [], text, query, pages))


def test_ica_rules_that_print_the_word_are_all_parsed_including_rule_44():
    text, _ = _store_text(ICA)
    numbers = {p["number"] for p in rag_provisions.parse_for_label(text, "Rule")}
    assert {"24", "25", "43", "44", "80"} <= numbers  # the bare parse stopped at Rule 24
    context = _context(ICA, "Does the Indian Council of Arbitration allow fast track arbitration?")
    rule_44 = next(b for b in context.split("\n\n[Source:") if "| Rule 44 |" in b.split("\n", 1)[0])
    assert "Fast Track Arbitration" in rule_44


def test_an_appendix_article_is_never_cited_as_the_main_rules_article():
    context = _context(ICC, "Will the emergency arbitrator be appointed if the applicant has not paid the fees? Article 8")
    # The answer names the main rules, but its words come from Appendix IV, Article 8.
    answer = ("No. Under Article 8 of the ICC Arbitration Rules, the application shall not be notified until the "
              "Secretariat has received the payment for the emergency arbitrator proceedings.")
    citations = llm_service.build_citations(answer, context, [ICC])
    assert [(c["title"], c["rules"]) for c in citations] == [(APPENDIX_IV, ["8"])]
    assert citations[0]["label"] == "Appendix IV, Article"


def test_a_mediation_article_is_cited_under_the_mediation_rules():
    context = _context(ICC, "When do mediation proceedings terminate under the ICC Mediation Rules? Article 8")
    answer = "Under Article 8, the mediation is terminated when the parties sign a settlement agreement."
    citations = llm_service.build_citations(answer, context, [ICC])
    assert [(c["title"], c["rules"]) for c in citations] == [(MEDIATION, ["8"])]


def test_a_citation_without_a_verified_number_carries_no_provision_label():
    context = "[Source: %s | Rule 2 | ICA Rules]\n(xiv) \"Fast Track Arbitration\" means arbitration under Rule 44." % ICA
    citations = llm_service.build_citations("Rule 99 allows fast track arbitration.", context, [ICA])
    assert len(citations) == 1 and citations[0]["rules"] == [] and "label" not in citations[0]


@pytest.mark.parametrize("badge,title", [("Rule", "Fast track"), ("Rule ", "Fast track"), (None, "Article:"),
                                         (None, "Rule 44 — fast track")])
def test_a_point_with_an_empty_or_unverified_number_is_dropped(badge, title):
    citations = [{"title": "ICA Rules", "rules": ["2"]}]
    point = {"title": title, "badge": badge, "text": "Parties may opt for fast track arbitration.", "cite": [1]}
    kept = {"title": "Definitions", "badge": "Rule 2", "text": "Fast track is defined.", "cite": [1]}
    assert llm_service._points_with_sources([point, kept], citations, ["ICA Rules"]) == [{**kept, "cite": [1]}]
